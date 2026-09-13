# frozen_string_literal: true

# sketchup-harness bridge loader.
#
# Installed into SketchUp's Plugins folder by bin/install-bridge, next to a
# sketchup_harness_bridge.root file holding the harness repo's path; remove
# both with `bin/install-bridge --uninstall`. It starts the supex bridge from
# that repo however SketchUp is opened, so Claude Code can drive this
# SketchUp. The bridge starts once a model window is open (not while the
# Welcome window is showing).
#
# Security: the bridge listens on localhost only, but while SketchUp is open
# any program running on this Mac can send it Ruby to execute. The REPL
# server supex would also start is switched off here.

module SketchupHarnessBridge
  ROOT_FILE = File.join(__dir__, 'sketchup_harness_bridge.root')

  def self.load_bridge
    return if defined?(SupexRuntime::Main) # already loaded, e.g. via bin/sketchup's -RubyStartup

    root = File.exist?(ROOT_FILE) ? File.read(ROOT_FILE).strip : ''
    injector = File.join(root, 'vendor', 'supex', 'runtime', 'src', 'injector.rb')
    unless File.exist?(injector)
      UI.messagebox("sketchup-harness: no bridge at #{injector}.\nRun bin/install-bridge from the harness " \
                    "repo again (it may have moved), or delete #{__FILE__} and #{ROOT_FILE}.")
      return
    end
    # The runtime refuses file operations outside this root (error -32002).
    # Set unconditionally: a value bin/sketchup registered with launchd before
    # the repo moved must not win.
    ENV['SUPEX_PROJECT_ROOT'] = root
    ENV['SUPEX_REPL_DISABLED'] = '1'
    load injector
  end
end

SketchupHarnessBridge.load_bridge
