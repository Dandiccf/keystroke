#!/usr/bin/env python3
"""Real palette offscreen, isolated HOME, synthetic Edge profiles.

Keystroke comes from $KEYSTROKE_ROOT, else the checkout this folder sits in,
else the installed plugin (for a copy under ~/.local/share/keystroke/extensions).
This extension is copied into the fake HOME's local extensions folder.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

here = Path(__file__).resolve().parents[1]
checkout = Path(__file__).resolve().parents[3]
root = Path(os.environ.get("KEYSTROKE_ROOT") or (checkout if (checkout / "Keystroke.qml").is_file()
            else Path.home() / ".config/omarchy/plugins/evindor.keystroke"))
with tempfile.TemporaryDirectory(prefix="keystroke-profiles-") as temp:
    work = Path(temp)
    project = work / "project"
    shutil.copytree(root, project, ignore=shutil.ignore_patterns(".git", ".claude", ".agents", ".codex", "tests", "__pycache__", "experiments"))
    (work / "qs").symlink_to("/usr/share/omarchy/shell")
    source = project / "Keystroke.qml"
    qml = source.read_text().replace("  PanelWindow {", "  Window {\n    transientParent: null\n    width: 1000; height: 800")
    qml = qml.replace("    anchors { top: true; bottom: true; left: true; right: true }\n", "")
    source.write_text("\n".join(line for line in qml.splitlines() if "exclusionMode:" not in line and "WlrLayershell." not in line))
    shutil.copytree(here, work / ".local/share/keystroke/extensions/browser-profiles", ignore=shutil.ignore_patterns("__pycache__"))
    config = work / ".config"
    (config / "omarchy").mkdir(parents=True)
    (config / "omarchy/keystroke.json").write_text(json.dumps({"version": 1, "matching": {"mode": "off"}}))
    edge = config / "microsoft-edge"
    for d in ("Default", "Profile 1"):
        (edge / d).mkdir(parents=True)
    (edge / "Local State").write_text(json.dumps({"profile": {"info_cache": {
        "Default": {"name": "Fixture Work", "user_name": "me@example.org"}, "Profile 1": {"name": "Fixture Home"}}}}))
    fake = work / "bin"
    fake.mkdir()
    for name in ("microsoft-edge-stable", "uwsm-app"):
        (fake / name).write_text("#!/bin/sh\nexit 0\n")
        (fake / name).chmod(0o755)
    (work / "shell.qml").write_text('''import QtQuick
import Quickshell
import "project"
ShellRoot {
  id: test
  property int stage: 0
  property int failures: 0
  Keystroke { id: palette; omarchyPath: "/usr/share/omarchy" }
  function service() { var s = palette.registry.services["browser-profiles"]; return s ? s.instance : null }
  function check(ok, msg) { if (!ok) { failures++; console.log("FAIL", msg) } }
  function items() { return palette.rows.filter(function(r) { return r.providerKey === "browser-profiles" && !r.disabled }) }
  function configure(on, rootSearch) {
    palette.applyConfigText(JSON.stringify({ version: 1, matching: { mode: "off" }, providers: {
      "browser-profiles": { enabled: on, root: rootSearch }
    } }))
  }
  Timer { interval: 120; running: true; repeat: true; onTriggered: {
    if (palette.pending || (service() && service().worker.running)) return
    switch (test.stage) {
    case 0:
      if (!palette.registry.manifests["browser-profiles"]) return
      check(!service(), "disabled extension is not loaded")
      configure(true, true)
      test.stage++; return
    case 1:
      if (!service()) return
      palette.open(JSON.stringify({ scope: "browser-profiles", title: "Browser profiles" }))
      test.stage++; return
    case 2:
      check(items().length === 2, "screen lists both profiles: " + items().length)
      check(items()[0] && items()[0].title === "Fixture Home", "alphabetical before any use")
      palette.setQuery("")
      palette.open(JSON.stringify({ query: "profile fixture work" }))
      test.stage++; return
    case 3:
      var row = items()[0]
      check(items().length === 1 && row.title === "Fixture Work", "command filters: " + items().length)
      check(row && row.subtitle === "Microsoft Edge · me@example.org", "subtitle names browser and account")
      var argv = row ? row.action.argv : []
      check(argv[0] === "uwsm-app" && argv[1] === "--" && /microsoft-edge-stable$/.test(argv[2]), "launch through uwsm-app: " + JSON.stringify(argv))
      check(argv[3] === "--profile-directory=Default" && argv[4] === "--new-window", "profile flags: " + JSON.stringify(argv))
      check(row && row.altAction.argv[4] === "--inprivate" && row.altVerb === "InPrivate window", "private window")
      check(row && row.remember, "frecency on")
      palette.open(JSON.stringify({ query: "fixture home" }))
      test.stage++; return
    case 4:
      check(items().length === 1 && items()[0].title === "Fixture Home", "root search finds a profile")
      palette.open(JSON.stringify({ query: "f" }))
      test.stage++; return
    case 5:
      check(items().length === 0, "one character is not enough at the root")
      palette.open(JSON.stringify({ query: "microsoft" }))
      test.stage++; return
    case 6:
      check(items().length === 0, "the browser name does not list every profile at the root: " + items().length)
      palette.open(JSON.stringify({ query: "profile microsoft" }))
      test.stage++; return
    case 7:
      check(items().length === 2, "the command searches by browser name: " + items().length)
      configure(true, false)
      palette.open(JSON.stringify({ query: "fixture home" }))
      test.stage++; return
    case 8:
      check(items().length === 0, "root search can be turned off")
      palette.open(JSON.stringify({ query: "profile home" }))
      test.stage++; return
    case 9:
      check(items().length === 1, "command still works with root search off")
      configure(false, true)
      test.stage++; return
    case 10:
      check(!service(), "disabling destroys service")
      console.log(test.failures ? "FAIL profiles palette" : "PASS profiles palette")
      Qt.quit(); stop(); return
    }
  } }
  Timer { interval: 15000; running: true; onTriggered: {
    console.log("FAIL timeout", test.stage, JSON.stringify(palette.registry.problems)); Qt.quit()
  } }
}
''')
    env = dict(os.environ, HOME=str(work), XDG_CONFIG_HOME=str(config), XDG_RUNTIME_DIR=str(work),
               PATH=f"{fake}:/usr/bin:/bin", QT_QPA_PLATFORM="offscreen", QT_QPA_PLATFORMTHEME="generic",
               QT_QUICK_BACKEND="software", QML_IMPORT_PATH=str(work))
    for key in ("DISPLAY", "WAYLAND_DISPLAY", "CHROME_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME"):
        env.pop(key, None)
    result = subprocess.run(["quickshell", "-p", str(work / "shell.qml")], env=env, capture_output=True, text=True, timeout=25)
    output = result.stdout + result.stderr
    assert "PASS profiles palette" in output and "FAIL" not in output, output
    assert "TypeError" not in output and "ReferenceError" not in output, output
    print("PASS profiles palette: load/unload, screen listing, command, root search and its switch, launch argv")
