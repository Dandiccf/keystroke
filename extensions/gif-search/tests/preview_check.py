#!/usr/bin/env python3
"""Exercise real GIF previews with a sequential stream, no network or clipboard."""
import base64
import ctypes
import json
import os
from pathlib import Path
import resource
import subprocess
import tempfile

extension = Path(__file__).resolve().parents[1]
# Two 100 ms frames, no GIF loop extension: Qt must restart the sequential stream.
gif = bytes.fromhex(
    "47494638396101000100800000000000ffffff"
    "21f904000a0000002c0000000001000100000202440100"
    "21f904000a0000002c00000000010001000002024c01003b"
)
url = "data:image/gif;base64," + base64.b64encode(gif).decode()
libc = ctypes.CDLL(None)


def no_core():
    # The unfixed Qt 6.12 path overflows its stack; never collect a core in tests.
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    if libc.prctl(4, 0, 0, 0, 0) != 0:  # Linux PR_SET_DUMPABLE
        os._exit(2)


with tempfile.TemporaryDirectory(prefix="keystroke-gif-preview-") as temp:
    work = Path(temp)
    shell = Path(os.environ.get("OMARCHY_PATH", "/usr/share/omarchy")) / "shell"
    (work / "qs").symlink_to(shell)
    view = (extension / "GifView.qml").read_text()
    # Observe the actual preview without replacing its source or playback logic.
    assert view.count("id: preview") == 1
    view = view.replace("id: preview", """id: preview
              objectName: "testGifPreview"
              property int testFrameChanges: 0
              onCurrentFrameChanged: testFrameChanges++""", 1)
    (work / "GifView.qml").write_text(view)
    (work / "shell.qml").write_text('''import QtQuick
import Quickshell
ShellRoot {
  id: test
  property int stage: 0
  property int ticks: 0
  property var firstPreview: null
  function check(ok, message) { if (!ok) { console.log("FAIL", message); Qt.exit(1) } }
  function find(node, name, list) {
    if (node.objectName === name) list.push(node)
    var children = node.children || []
    for (var i = 0; i < children.length; i++) find(children[i], name, list)
    return list
  }
  function advance() { stage++; ticks = 0 }
  QtObject {
    id: service
    property bool active: true
    property string term: "fixture"
    property var settings: ({defaultAction: "image", closeAfterCopy: false})
    property var items: Array.from({length: 24}, function(_, i) {
      return {title: "GIF " + i, preview: __URL__}
    })
    property bool loading: false
    property int page: 0
    property bool more: false
    property string message: ""
    signal copySucceeded()
    function search(text) {}
    function dismiss() { active = false; items = [] }
    function copy(item, link) {}
    function turnPage(delta) {}
    function refresh() {}
  }
  Window {
    width: 640; height: 480; visible: true
    GifView { id: view; anchors.fill: parent; service: service }
  }
  Timer {
    interval: 100; running: true; repeat: true
    onTriggered: {
      test.ticks++
      var previews = test.find(view, "testGifPreview", [])
      var loaded = previews.filter(function(p) { return String(p.source).length > 0 })
      switch (test.stage) {
      case 0:
        if (!loaded.length || loaded[0].testFrameChanges < 8) return
        test.check(loaded.length < 24, "only visible previews are loaded")
        loaded.forEach(function(p) {
          test.check(p.status === Image.Ready && p.frameCount === 2, "GIF decoded")
          test.check(p.cache && p.sourceSize.width > 0 && p.sourceSize.width <= 160
            && p.sourceSize.height > 0 && p.sourceSize.height <= 100, "bounded cached frame dimensions")
        })
        test.firstPreview = loaded[0]
        test.find(view, "gifSearchGrid", [])[0].positionViewAtIndex(23, GridView.End)
        test.advance(); return
      case 1:
        if (test.ticks < 3) return
        test.check(!test.firstPreview || String(test.firstPreview.source) === "", "scrolled-out preview released")
        test.check(loaded.length > 0 && loaded.length < 24, "new visible tiles load")
        service.active = false
        test.advance(); return
      case 2:
        if (test.ticks < 2) return
        test.check(loaded.length === 0, "inactive service releases every preview")
        view.visible = false; service.active = true
        test.advance(); return
      case 3:
        if (test.ticks < 2) return
        test.check(loaded.length === 0, "hidden view keeps previews unloaded")
        view.visible = true
        test.advance(); return
      case 4:
        if (!loaded.length || loaded.some(function(p) { return p.status !== Image.Ready })) return
        service.dismiss()
        test.advance(); return
      case 5:
        if (test.ticks < 2) return
        test.check(loaded.length === 0, "dismiss releases previews")
        console.log("PASS sequential GIF loops, bounded dimensions, scroll, hide, reopen, dismiss")
        Qt.quit()
      }
    }
  }
  Timer { interval: 15000; running: true; onTriggered: { console.log("FAIL timeout", test.stage); Qt.exit(1) } }
}
'''.replace("__URL__", json.dumps(url)))
    env = dict(os.environ, HOME=temp, XDG_CONFIG_HOME=str(work / ".config"),
               XDG_DATA_HOME=str(work / ".local/share"), XDG_STATE_HOME=str(work / ".local/state"),
               XDG_CACHE_HOME=str(work / ".cache"), XDG_RUNTIME_DIR=temp,
               QT_QPA_PLATFORM="offscreen", QT_QPA_PLATFORMTHEME="generic",
               QT_QUICK_BACKEND="software", QML_IMPORT_PATH=temp, QML_DISABLE_DISK_CACHE="1",
               QS_DISABLE_CRASH_HANDLER="1")
    for name in ("DISPLAY", "WAYLAND_DISPLAY", "DBUS_SESSION_BUS_ADDRESS"):
        env.pop(name, None)
    result = subprocess.run(["quickshell", "-p", str(work / "shell.qml")], env=env,
                            capture_output=True, text=True, timeout=20, preexec_fn=no_core)
    output = result.stdout + result.stderr
    assert result.returncode == 0 and "PASS sequential GIF" in output and "FAIL" not in output, output + f"\nexit={result.returncode}"
    assert not any(error in output for error in ("TypeError", "ReferenceError", "Unable to assign")), output
    print("PASS sequential GIF loops, bounded dimensions, scroll, hide, reopen, dismiss")
