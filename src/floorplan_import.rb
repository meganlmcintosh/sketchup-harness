# frozen_string_literal: true

# Floor plan import: brings a `bin/plan build` output into SketchUp.
#
# Run it with `./bin/plan sketchup projects/<name>`. That command builds the
# project, writes a job file, and evaluates a stub through the supex bridge
# that loads this file and calls FloorplanImport.run(job_path). Evaluating
# this file on its own only defines the module.
#
# It:
# 1. removes the previous import of the same project, so re-running replaces
#    the geometry instead of doubling it;
# 2. imports model.dxf (3D) and one plan DXF per storey (2D);
# 3. repairs what the DXF importer loses: tag names, material names, glass
#    transparency, and block contents stranded on a stray tag;
# 4. recreates room labels and dimensions, which the importer drops;
# 5. rebuilds the project's scenes and writes a PNG of each for checking.
#
# Undo: SketchUp's native importer closes any Ruby operation that is open
# when it runs (verified: an abort_operation after model.import rolls nothing
# back). So the run is three undo steps, not one: the removal, the imports
# (one native step each), and the repairs. If anything fails after the
# imports, this run's entities are erased by hand and the error reported.
#
# Units: manifest coordinates are millimetres. SketchUp works in inches
# internally, so every length is converted with Numeric#mm.

require 'json'
require 'fileutils'

Object.send(:remove_const, :FloorplanImport) if defined?(FloorplanImport)

module FloorplanImport
  DICT = 'floorplan'
  MANIFEST_VERSION = 1
  IMPORT_OPTIONS = {
    import_materials: true, merge_coplanar_faces: true, orient_faces: true,
    preserve_origin: true, show_summary: false
  }.freeze
  PLAN_LIFT_MM = 5 # plans float just above the floor so they don't z-fight with it
  IMAGE_SIZE = { width: 1600, height: 1000 }.freeze
  UNNAMED_MATERIAL = /\A(Material\d*|<auto>\d*)\z/

  module_function

  def run(job_path)
    started = Time.now
    job = JSON.parse(File.read(job_path))
    manifest = JSON.parse(File.read(job.fetch('manifest')))
    unless manifest['version'] == MANIFEST_VERSION
      raise "#{job['manifest']} is manifest version #{manifest['version']}; this importer reads #{MANIFEST_VERSION}"
    end

    project_id = manifest.fetch('project_id')
    model = checked_model(job.fetch('skp'))
    report = { nonce: job['nonce'], project: manifest['project'], skp: job['skp'], warnings: [] }

    model.active_path = nil # our definitions can't be removed while one is open for editing
    model.selection.clear
    model.active_layer = model.layers[0] # new entities go to Untagged, whatever tag the user had active
    layers_before = model.layers.to_a
    materials_before = model.materials.to_a

    model.start_operation("Floor plan: remove #{manifest['project']}", true)
    begin
      use_millimetres(model)
      clear_template_figure(model)
      report[:removed] = remove_previous(model, project_id, manifest)
      model.commit_operation
    rescue StandardError
      model.abort_operation
      raise
    end

    # The imports close any open operation, so they run on their own.
    structure = import_dxf(model, manifest['model']['dxf'], project_id, 'model')
    plans = manifest['plans'].map { |plan| import_dxf(model, plan['dxf'], project_id, 'plan') }

    model.start_operation("Floor plan: #{manifest['project']}", true)
    begin
      structure.definition.name = "Floor plan - #{manifest['project']}"
      structure.layer = model.layers[0]
      name_model_tags(model, structure, manifest, layers_before)
      plans.zip(manifest['plans']).each { |instance, plan| arrange_plan(model, instance, plan) }
      name_definitions(model, manifest['model']['definitions'], project_id)
      report[:materials] = name_materials(model, manifest, materials_before, [structure, *plans])
      report[:stray_tags_removed] = remove_stray_tags(model, manifest, layers_before)

      model.set_attribute(DICT, 'project', project_id)
      model.set_attribute(DICT, "tags:#{project_id}", JSON.generate(project_tags(manifest)))
      report[:scenes] = build_scenes(model, manifest, project_id, job)
      model.commit_operation
    rescue StandardError
      model.abort_operation
      model.start_operation('Floor plan: undo failed import', true)
      remove_previous(model, project_id, manifest)
      model.commit_operation
      raise
    end

    if job['save']
      raise "SketchUp could not save #{job['skp']}" unless model.save(job['skp'])

      report[:saved] = true
    end
    report[:faces] = count_faces(structure.definition)
    report[:seconds] = (Time.now - started).round(1)
    JSON.generate(report)
  end

  # Only ever import into the project's own model, or an untouched new one
  # while the project has no .skp yet. src/floorplan_target.rb gets the right
  # model active before this runs.
  def checked_model(skp)
    model = Sketchup.active_model
    raise 'SketchUp has no model window open' if model.nil?
    return model if FloorplanTarget.acceptable?(model, skp)

    if File.exist?(skp) && FloorplanTarget.untouched?(model)
      raise "#{File.basename(skp)} already exists but the active model is a blank one; bring the project's " \
            'window to the front (or delete the .skp to start over), then run bin/plan sketchup again'
    end
    raise "The active SketchUp model (#{model.title}) is not #{File.basename(skp)} or a new " \
          'empty model, so nothing was imported. Run bin/plan sketchup again.'
  end

  def use_millimetres(model)
    units = model.options['UnitsOptions']
    units['LengthUnit'] = 2 # millimetres
    units['LengthFormat'] = 0 # decimal
    units['LengthPrecision'] = 0
    units['SuppressUnitsDisplay'] = true # dimensions read "3600", as Australian plans do
    model.options['PageOptions']['ShowTransition'] = false
  end

  # A new model (bin/sketchup's blank template copy, or an untitled one)
  # comes with the template's scale figure; it would be saved into the
  # project and stand in every plan view.
  def clear_template_figure(model)
    return unless FloorplanTarget.untouched?(model)

    figures = model.entities.grep(Sketchup::ComponentInstance).reject { |e| e.get_attribute(DICT, 'project') }
    model.entities.erase_entities(figures) unless figures.empty?
  end

  def ours?(entity, project_id)
    entity.get_attribute(DICT, 'project') == project_id
  end

  def project_tags(manifest)
    manifest['model']['tags'] + manifest['plans'].map { |p| p['tag'] }
  end

  def remove_previous(model, project_id, manifest)
    instances = model.entities.select { |e| e.respond_to?(:definition) && ours?(e, project_id) }
    model.entities.erase_entities(instances) unless instances.empty?

    # Ours, plus unused definitions carrying the names this import is about
    # to use: orphans of an import that was undone or interrupted, which would
    # otherwise make SketchUp mangle the new names ("Robe 1800" -> "Robe #1").
    names = [*manifest['model']['definitions'].values, *project_tags(manifest), "Floor plan - #{manifest['project']}"]
    removed_definitions = 0
    loop do
      unused = model.definitions.select { |d| d.instances.empty? && (ours?(d, project_id) || names.include?(d.name)) }
      break if unused.empty?

      unused.each { |d| model.definitions.remove(d) }
      removed_definitions += unused.size
    end

    # Scenes carry the project attribute; earlier imports only recorded their
    # names. Scenes this run is about to make are kept and refreshed in place
    # (build_scenes); the rest of ours are erased where SketchUp allows it
    # (Pages#erase answers false, and does nothing, in some contexts).
    legacy = JSON.parse(model.get_attribute(DICT, "scenes:#{project_id}", '[]'))
    keep = scene_names_for(manifest)
    stale = model.pages.to_a.select { |p| (ours?(p, project_id) || legacy.include?(p.name)) && !keep.include?(p.name) }
    erased = stale.count { |p| model.pages.erase(p) }
    model.delete_attribute(DICT, "scenes:#{project_id}") unless legacy.empty?

    # Tags from an earlier import that the plan no longer uses (a renamed storey).
    stale = JSON.parse(model.get_attribute(DICT, "tags:#{project_id}", '[]')) - project_tags(manifest)
    removed_tags = stale.count do |name|
      layer = model.layers[name]
      next false unless layer && model.entities.none? { |e| e.layer == layer } && layer_unused?(model, layer)

      model.layers.remove(layer)
      true
    end
    {
      instances: instances.size, definitions: removed_definitions, tags: removed_tags,
      scenes: erased, scenes_left: stale.size - erased
    }
  end

  def layer_unused?(model, layer)
    model.definitions.none? { |d| d.entities.any? { |e| e.layer == layer } }
  end

  def scene_names_for(manifest)
    storeys = manifest['storeys'].map { |s| s['name'] }
    ['3D', *storeys.map { |s| "#{s} - 3D" }, *manifest['plans'].map { |p| "#{p['storey']} - Plan" }]
  end

  def import_dxf(model, path, project_id, role)
    entities_before = model.entities.to_a
    definitions_before = model.definitions.to_a
    raise "SketchUp could not import #{path}" unless model.import(path, IMPORT_OPTIONS)

    instance = (model.entities.to_a - entities_before).grep(Sketchup::ComponentInstance).first
    raise "Importing #{File.basename(path)} produced no component" unless instance

    (model.definitions.to_a - definitions_before).each { |d| d.set_attribute(DICT, 'project', project_id) }
    instance.set_attribute(DICT, 'project', project_id)
    instance.set_attribute(DICT, 'role', role)
    instance
  end

  # DXF block names ("WINDOW_1810x1210_S890_T250") become readable component names.
  def name_definitions(model, names, project_id)
    model.definitions.each do |definition|
      next unless ours?(definition, project_id) && names.key?(definition.name)

      definition.name = names[definition.name]
    end
  end

  # Every entity inside an imported component, recursively (each definition once).
  def each_entity(definition, seen = {}, &block)
    return if seen[definition]

    seen[definition] = true
    definition.entities.each do |entity|
      yield entity
      each_entity(entity.definition, seen, &block) if entity.respond_to?(:definition)
    end
  end

  # DXF layers arrive as tags named like "S1-STRUCTURE"; give them the
  # manifest's names, reusing tags left from a previous import.
  def name_model_tags(model, structure, manifest, layers_before)
    manifest['model']['layers'].each do |entry|
      imported = model.layers[entry['layer']]
      next unless imported

      existing = model.layers[entry['tag']]
      if existing && existing != imported
        each_entity(structure.definition) { |e| e.layer = existing if e.layer == imported }
        model.layers.remove(imported) unless layers_before.include?(imported)
      else
        imported.name = entry['tag']
      end
    end
  end

  # Plan linework goes to Untagged inside one component on the storey's plan
  # tag; the drafting layers it arrived on are removed with the other strays.
  # The DXF's blocks (wall-fill hatches, furniture symbols) are exploded into
  # plain edges and faces: as components they would need one definition per
  # storey with clashing names, and nobody edits a plan symbol in SketchUp.
  def arrange_plan(model, instance, plan)
    instance.definition.name = plan['tag']
    untagged = model.layers[0]
    each_entity(instance.definition) { |e| e.layer = untagged unless e.layer == untagged }
    nested = instance.definition.entities.grep(Sketchup::ComponentInstance)
    nested_definitions = nested.map(&:definition).uniq
    nested.each(&:explode)
    nested_definitions.each { |d| model.definitions.remove(d) if d.instances.empty? }
    instance.layer = model.layers[plan['tag']] || model.layers.add(plan['tag'])
    lift = plan['level'].to_f + PLAN_LIFT_MM
    instance.transform!(Geom::Transformation.translation([0, 0, lift.mm]))
    add_annotations(instance.definition.entities, plan)
    instance
  end

  def add_annotations(entities, plan)
    plan['labels'].each do |label|
      x, y = label['at']
      entities.add_text(label['text'], Geom::Point3d.new(x.mm, y.mm, 0))
    end
    plan['dimensions'].each do |dim|
      start = Geom::Point3d.new(dim['start'][0].mm, dim['start'][1].mm, 0)
      finish = Geom::Point3d.new(dim['end'][0].mm, dim['end'][1].mm, 0)
      offset = Geom::Vector3d.new(dim['offset'][0].mm, dim['offset'][1].mm, 0)
      entities.add_dimension_linear(start, finish, offset)
    end
  end

  # Materials painted on anything that isn't ours (the user's own geometry).
  def materials_used_elsewhere(model, instances)
    used = {}
    seen = instances.to_h { |i| [i.definition, true] }
    collect = lambda do |e|
      used[e.material] = true if e.respond_to?(:material) && e.material
      used[e.back_material] = true if e.is_a?(Sketchup::Face) && e.back_material
    end
    model.entities.each do |e|
      next if instances.include?(e)

      collect.call(e)
      each_entity(e.definition, seen, &collect) if e.respond_to?(:definition)
    end
    used
  end

  # The importer names materials "<auto>N" by colour, and SketchUp names the
  # one it makes for text and dimensions "Material". Rename each to its
  # finish, or fold it into the same-named material a previous import left.
  # Pre-existing unnamed materials are only touched if nothing else uses them.
  def name_materials(model, manifest, materials_before, instances)
    by_rgb = manifest['materials'].to_h { |m| [m['rgb'], m] }
    elsewhere = materials_used_elsewhere(model, instances)
    unnamed = materials_before.select { |m| m.name =~ UNNAMED_MATERIAL && !elsewhere[m] }
    replacements = {}
    renamed = 0
    ((model.materials.to_a - materials_before) + unnamed).each do |material|
      entry = by_rgb[material.color.to_a[0, 3]]
      next unless entry

      existing = model.materials[entry['name']]
      if existing && existing != material
        replacements[material] = existing
      else
        material.name = entry['name']
        material.alpha = entry['alpha'].to_f
        renamed += 1
      end
    end
    replace_materials(instances, replacements) unless replacements.empty?
    replacements.each_key { |m| model.materials.remove(m) unless elsewhere[m] }
    { renamed: renamed, reused: replacements.size }
  end

  def replace_materials(instances, replacements)
    seen = {}
    instances.each do |instance|
      each_entity(instance.definition, seen) do |e|
        e.material = replacements[e.material] if e.respond_to?(:material) && replacements.key?(e.material)
        e.back_material = replacements[e.back_material] if e.is_a?(Sketchup::Face) && replacements.key?(e.back_material)
      end
    end
  end

  # Tags the importer created that aren't ours (DXF layer "0" and the plan
  # drafting layers). Removing a tag moves its entities to Untagged.
  def remove_stray_tags(model, manifest, layers_before)
    keep = project_tags(manifest)
    strays = (model.layers.to_a - layers_before).reject { |layer| keep.include?(layer.name) }
    strays.each { |layer| model.layers.remove(layer) }
    strays.size
  end

  # Scenes: the whole model; a cutaway per storey (everything above it hidden,
  # roof included); and each storey's flat plan seen from above. Pages carry
  # the project attribute so a re-run finds them however they were renamed.
  def build_scenes(model, manifest, project_id, job)
    views_dir = job['views_dir']
    if views_dir && job['views']
      FileUtils.mkdir_p(views_dir)
      Dir.children(views_dir).grep(/\.png\z/).each { |stale| File.delete(File.join(views_dir, stale)) }
    end
    model_tags = manifest['model']['tags']
    plan_tags = manifest['plans'].map { |p| p['tag'] }
    scenes = []

    # A scene of that name is refreshed in place (an earlier import's, or one
    # an undone run left behind); otherwise it is added.
    add_scene = lambda do |name, visible_tags, view|
      (model_tags + plan_tags).each do |tag|
        layer = model.layers[tag]
        layer.visible = visible_tags.include?(tag) if layer
      end
      frame_camera(model, view)
      page = model.pages[name]
      if page
        page.update(PAGE_USE_ALL)
      else
        page = model.pages.add(name)
      end
      page.set_attribute(DICT, 'project', project_id)
      scenes << page
      write_view(model, views_dir, scenes.size, page.name) if views_dir && job['views']
    end

    add_scene.call('3D', model_tags, :iso)
    storeys = manifest['storeys']
    storey_tags = storeys.flat_map { |s| s['tags'] }
    storeys.each_with_index do |storey, i|
      next if i == storeys.size - 1 && (model_tags - storey_tags).empty? # top storey, nothing above it

      below = storeys[0..i].flat_map { |s| s['tags'] }
      add_scene.call("#{storey['name']} - 3D", below, :cutaway)
    end
    manifest['plans'].each { |plan| add_scene.call("#{plan['storey']} - Plan", [plan['tag']], :top) }

    model.pages.selected_page = scenes.first
    scenes.map(&:name)
  end

  def frame_camera(model, view)
    active = model.active_view
    target = Geom::Point3d.new(0, 0, 0)
    eye, up = case view
              when :top then [[0, 0, 1000], [0, 1, 0]]
              when :cutaway then [[700, -900, 1100], [0, 0, 1]]
              else [[800, -1000, 600], [0, 0, 1]]
              end
    camera = Sketchup::Camera.new(Geom::Point3d.new(*eye), target, Geom::Vector3d.new(*up))
    camera.perspective = view != :top
    active.camera = camera
    active.zoom_extents
  end

  def write_view(model, views_dir, index, name)
    file = format('%<i>02d-%<name>s.png', i: index, name: name.downcase.gsub(/[^a-z0-9]+/, '-'))
    model.active_view.write_image(IMAGE_SIZE.merge(filename: File.join(views_dir, file), antialias: true))
  end

  def count_faces(definition)
    count = 0
    each_entity(definition) { |e| count += 1 if e.is_a?(Sketchup::Face) }
    count
  end
end
