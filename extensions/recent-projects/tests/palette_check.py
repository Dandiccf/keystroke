#!/usr/bin/env python3
"""Real palette offscreen, isolated HOME, a synthetic Cursor history.

Keystroke comes from $KEYSTROKE_ROOT, else the checkout this folder sits in,
else the installed plugin (for a copy under ~/.local/share/keystroke/extensions).
This extension is copied into the fake HOME's local extensions folder.
"""
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile

here = Path(__file__).resolve().parents[1]
checkout = Path(__file__).resolve().parents[3]
root = Path(os.environ.get("KEYSTROKE_ROOT") or (checkout if (checkout / "Keystroke.qml").is_file()
            else Path.home() / ".config/omarchy/plugins/evindor.keystroke"))
with tempfile.TemporaryDirectory(prefix="keystroke-projects-") as temp:
    work = Path(temp)
    project = work / "project"
    shutil.copytree(root, project, ignore=shutil.ignore_patterns(".git", ".claude", ".agents", ".codex", "tests", "__pycache__", "experiments"))
    (work / "qs").symlink_to("/usr/share/omarchy/shell")
    source = project / "Keystroke.qml"
    qml = source.read_text().replace("  PanelWindow {", "  Window {\n    transientParent: null\n    width: 1000; height: 800")
    qml = qml.replace("    anchors { top: true; bottom: true; left: true; right: true }\n", "")
    source.write_text("\n".join(line for line in qml.splitlines() if "exclusionMode:" not in line and "WlrLayershell." not in line))
    shutil.copytree(here, work / ".local/share/keystroke/extensions/recent-projects", ignore=shutil.ignore_patterns("__pycache__"))
    config = work / ".config"
    (config / "omarchy").mkdir(parents=True)
    (config / "omarchy/keystroke.json").write_text(json.dumps({"version": 1, "matching": {"mode": "off"}}))
    folders = [work / "git/fixture-api", work / "git/fixture-web"]
    for d in folders:
        d.mkdir(parents=True)
    (config / "Cursor/User/globalStorage").mkdir(parents=True)
    con = sqlite3.connect(config / "Cursor/User/globalStorage/state.vscdb")
    con.execute("CREATE TABLE ItemTable (key TEXT UNIQUE ON CONFLICT REPLACE, value BLOB)")
    con.execute("INSERT INTO ItemTable VALUES (?, ?)", ("history.recentlyOpenedPathsList",
                json.dumps({"entries": [{"folderUri": d.as_uri()} for d in folders]})))
    con.commit()
    con.close()
    fake = work / "bin"
    fake.mkdir()
    for name in ("cursor", "uwsm-app", "xdg-terminal-exec"):
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
  function service() { var s = palette.registry.services["recent-projects"]; return s ? s.instance : null }
  function check(ok, msg) { if (!ok) { failures++; console.log("FAIL", msg) } }
  function items() { return palette.rows.filter(function(r) { return r.providerKey === "recent-projects" && !r.disabled }) }
  function configure(on, rootSearch) {
    palette.applyConfigText(JSON.stringify({ version: 1, matching: { mode: "off" }, providers: {
      "recent-projects": { enabled: on, root: rootSearch }
    } }))
  }
  Timer { interval: 120; running: true; repeat: true; onTriggered: {
    if (palette.pending || (service() && service().worker.running)) return
    switch (test.stage) {
    case 0:
      if (!palette.registry.manifests["recent-projects"]) return
      check(!service(), "disabled extension is not loaded")
      configure(true, true)
      test.stage++; return
    case 1:
      if (!service()) return
      palette.open(JSON.stringify({ scope: "recent-projects", title: "Recent projects" }))
      test.stage++; return
    case 2:
      check(items().length === 2, "screen lists both projects: " + items().length)
      check(items()[0] && items()[0].title === "fixture-api", "the editor's order before any use")
      palette.setQuery("")
      palette.open(JSON.stringify({ query: "proj fixture-web" }))
      test.stage++; return
    case 3:
      var row = items()[0]
      check(items().length === 1 && row.title === "fixture-web", "command filters: " + items().length)
      check(row && row.subtitle === "~/git/fixture-web · Cursor", "subtitle names path and editor: " + (row && row.subtitle))
      var argv = row ? row.action.argv : []
      check(argv[0] === "uwsm-app" && argv[1] === "--" && /cursor$/.test(argv[2]), "launch through uwsm-app: " + JSON.stringify(argv))
      check(argv[3] === "--folder-uri" && /^file:.*fixture-web$/.test(argv[4]), "folder uri: " + JSON.stringify(argv))
      check(row && row.altVerb === "Open terminal" && /^--dir=.*fixture-web$/.test(row.altAction.argv[3]), "terminal")
      check(row && row.remember, "frecency on")
      palette.open(JSON.stringify({ query: "fixture-api" }))
      test.stage++; return
    case 4:
      check(items().length === 1 && items()[0].title === "fixture-api", "root search finds a project")
      palette.open(JSON.stringify({ query: "f" }))
      test.stage++; return
    case 5:
      check(items().length === 0, "one character is not enough at the root")
      palette.open(JSON.stringify({ query: "cursor" }))
      test.stage++; return
    case 6:
      check(items().length === 0, "the editor name does not list every project at the root: " + items().length)
      palette.open(JSON.stringify({ query: "proj cursor" }))
      test.stage++; return
    case 7:
      check(items().length === 2, "the command searches by editor name: " + items().length)
      configure(true, false)
      palette.open(JSON.stringify({ query: "fixture-api" }))
      test.stage++; return
    case 8:
      check(items().length === 0, "root search can be turned off")
      palette.open(JSON.stringify({ query: "proj api" }))
      test.stage++; return
    case 9:
      check(items().length === 1, "command still works with root search off")
      configure(false, true)
      test.stage++; return
    case 10:
      check(!service(), "disabling destroys service")
      console.log(test.failures ? "FAIL projects palette" : "PASS projects palette")
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
    assert "PASS projects palette" in output and "FAIL" not in output, output
    assert "TypeError" not in output and "ReferenceError" not in output, output
    print("PASS projects palette: load/unload, screen listing, command, root search and its switch, launch and terminal argv")
