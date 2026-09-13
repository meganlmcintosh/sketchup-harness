# frozen_string_literal: true

# Quit SketchUp from the bridge without losing anyone's work.
#
# Run by `bin/sketchup --quit` (and --restart). Changes to the blank template
# copy bin/sketchup opened are discarded: that copy is scratch. Any other
# model with unsaved changes stops the quit, and the reason is reported, so
# a "Save changes?" dialog never blocks SketchUp with the bridge unable to
# answer. SketchUp can't list its other windows from Ruby; if another
# document is open with changes, SketchUp itself will ask about it.

require 'json'

load File.join(__dir__, 'floorplan_target.rb')

Object.send(:remove_const, :FloorplanQuit) if defined?(FloorplanQuit)

module FloorplanQuit
  module_function

  def run
    model = Sketchup.active_model
    state = { active: model&.title, path: model&.path, modified: model ? model.modified? : false }
    if model&.modified?
      if FloorplanTarget.same_file?(model.path, FloorplanTarget::BLANK)
        model.close(true) # the scratch copy: drop its changes
        state[:discarded] = 'blank copy'
      else
        state[:refused] = "#{model.title} has unsaved changes; save or close it in SketchUp first"
        return JSON.generate(state)
      end
    end
    state[:quitting] = true
    UI.start_timer(0.2, false) { Sketchup.send_action('terminate:') } # after this reply has gone out
    JSON.generate(state)
  end
end

FloorplanQuit.run
