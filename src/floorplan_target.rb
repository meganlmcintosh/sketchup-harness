# frozen_string_literal: true

# Floor plan target: makes the project's model the active SketchUp model.
#
# Sketchup.open_file and Sketchup.file_new only take effect on macOS after the
# current Ruby call returns: until then Sketchup.active_model is still the old
# window. So `bin/plan sketchup` runs this with mode "prepare" (open or create
# once), polls it with mode "status" until the right model is active, and only
# then runs src/floorplan_import.rb. Both are driven by a job file whose path
# bin/plan passes in; this file on its own only defines the module.

require 'json'

Object.send(:remove_const, :FloorplanTarget) if defined?(FloorplanTarget)

module FloorplanTarget
  BLANK = File.expand_path('../.tmp/sketchup/blank.skp', __dir__)

  module_function

  # Paths compared the way the file system does: resolved, Unicode-normalised, case-insensitive.
  def same_file?(a, b)
    return false if a.nil? || b.nil? || a.empty? || b.empty?

    norm = ->(p) { (File.exist?(p) ? File.realpath(p) : File.expand_path(p)).unicode_normalize(:nfc) }
    norm.call(a).casecmp?(norm.call(b))
  end

  # A new model nobody has drawn in, or the blank template copy bin/sketchup opens.
  def untouched?(model)
    (model.path.empty? || same_file?(model.path, BLANK)) && !model.modified?
  end

  # Safe to import into: the project's own file; or, while that file doesn't
  # exist yet, an untouched new model. Never a blank when the project's .skp
  # exists: saving would overwrite whatever was drawn in it by hand.
  def acceptable?(model, skp)
    return false if model.nil?
    return true if same_file?(model.path, skp)

    untouched?(model) && !File.exist?(skp)
  end

  def run(job_path)
    spec = JSON.parse(File.read(job_path))
    skp = spec.fetch('skp')
    model = Sketchup.active_model
    state = {
      nonce: spec['nonce'], ready: acceptable?(model, skp), exists: File.exist?(skp),
      active: model&.title, path: model&.path
    }
    if !state[:ready] && spec['mode'] == 'prepare'
      if File.exist?(skp)
        state[:action] = 'opening'
        state[:opened] = Sketchup.open_file(skp)
      else
        state[:action] = 'creating'
        Sketchup.file_new
      end
    end
    JSON.generate(state)
  end
end
