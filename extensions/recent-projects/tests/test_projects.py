import contextlib
import io
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "bin"))
import projects  # noqa: E402


def which_from(available):
    return lambda name: "/usr/bin/" + name if name in available else None


def write_state(user, entries, key=projects.RECENT_KEY):
    """A state.vscdb shaped like the editor's: one ItemTable of key/value rows."""
    (user / "globalStorage").mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(user / "globalStorage/state.vscdb")
    con.execute("CREATE TABLE ItemTable (key TEXT UNIQUE ON CONFLICT REPLACE, value BLOB)")
    con.execute("INSERT INTO ItemTable VALUES (?, ?)", ("unrelated.key", "secret"))
    if entries is not None:
        con.execute("INSERT INTO ItemTable VALUES (?, ?)", (key, json.dumps({"entries": entries})))
    con.commit()
    con.close()


class DiscoverTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.config = self.home / ".config"

    def tearDown(self):
        self.tmp.cleanup()

    def folder(self, rel):
        path = self.home / rel
        path.mkdir(parents=True, exist_ok=True)
        return path

    def test_kinds_names_and_skips(self):
        app = self.folder("git/my app")
        ws = self.folder("work") / "team.code-workspace"
        ws.write_text("{}")
        note = self.folder("notes") / "todo.md"
        note.write_text("")
        untitled = self.folder(".config/Cursor/Workspaces/123") / "workspace.json"
        untitled.write_text("{}")
        write_state(self.config / "Cursor/User", [
            {"folderUri": app.as_uri()},
            {"workspace": {"id": "abc", "configPath": ws.as_uri()}},
            {"fileUri": note.as_uri()},
            {"folderUri": (self.home / "gone").as_uri()},
            {"workspace": {"id": "u", "configPath": untitled.as_uri()}},
            {"folderUri": "vscode-remote://ssh-remote%2Bbuild-box/srv/api", "remoteAuthority": "ssh-remote+build-box"},
            {"folderUri": "vscode-remote://dev-container%2B7b22/workspaces/site"},
            {"folderUri": "--help"},
            {"folderUri": app.as_uri()},
            {"label": "no uri"},
            "junk",
        ])
        result = projects.discover(self.home, self.config, which_from({"cursor", "uwsm-app", "xdg-terminal-exec"}))
        [cursor] = result["editors"]
        self.assertEqual(cursor["launch"], ["uwsm-app", "--", "/usr/bin/cursor"])
        self.assertEqual(cursor["terminal"], ["uwsm-app", "--", "/usr/bin/xdg-terminal-exec"])
        got = [(e["kind"], e["title"], e["where"], e["dir"], e["remote"]) for e in cursor["entries"]]
        self.assertEqual(got, [
            ("folder", "my app", "~/git/my app", str(app), ""),
            ("workspace", "team", "~/work/team.code-workspace", str(ws.parent), ""),
            ("file", "todo.md", "~/notes/todo.md", str(note.parent), ""),
            ("folder", "api", "/srv/api", "", "SSH: build-box"),
            ("folder", "site", "/workspaces/site", "", "Dev Container"),
        ])
        self.assertEqual(cursor["entries"][0]["uri"], app.as_uri())

    def test_editor_needs_binary_and_history(self):
        write_state(self.config / "Code/User", [{"folderUri": self.folder("a").as_uri()}])
        write_state(self.config / "VSCodium/User", None)  # a database without the key
        self.assertEqual(projects.discover(self.home, self.config, which_from({"codium"}))["editors"], [])
        self.assertEqual(projects.discover(self.home, self.config, which_from({"cursor"}))["editors"], [])
        [code] = projects.discover(self.home, self.config, which_from({"code"}))["editors"]
        self.assertEqual((code["id"], code["launch"], code["terminal"]), ("vscode", ["/usr/bin/code"], []))

    def test_code_binary_serves_either_build(self):
        # Arch's code package runs Code - OSS under the binary name "code".
        write_state(self.config / "Code - OSS/User", [{"folderUri": self.folder("a").as_uri()}])
        ids = [e["id"] for e in projects.discover(self.home, self.config, which_from({"code"}))["editors"]]
        self.assertEqual(ids, ["code-oss"])

    def test_unreadable_database(self):
        user = self.config / "Cursor/User/globalStorage"
        user.mkdir(parents=True)
        (user / "state.vscdb").write_text("not sqlite")
        self.assertEqual(projects.discover(self.home, self.config, which_from({"cursor"}))["editors"], [])

    def test_flatpak(self):
        write_state(self.home / ".var/app/com.visualstudio.code/config/Code/User", [{"folderUri": self.folder("a").as_uri()}])
        self.assertEqual(projects.discover(self.home, self.config, which_from({"flatpak"}))["editors"], [])
        (self.home / ".local/share/flatpak/app/com.visualstudio.code").mkdir(parents=True)
        [code] = projects.discover(self.home, self.config, which_from({"flatpak"}))["editors"]
        self.assertEqual(code["id"], "flatpak:com.visualstudio.code")
        self.assertEqual(code["launch"], ["/usr/bin/flatpak", "run", "com.visualstudio.code"])

    def test_cap_is_per_editor(self):
        base = self.folder("many")
        entries = [{"folderUri": self.folder("many/%d" % i).as_uri()} for i in range(projects.MAX_ENTRIES + 5)]
        write_state(self.config / "Cursor/User", entries)
        [cursor] = projects.discover(self.home, self.config, which_from({"cursor"}))["editors"]
        self.assertEqual(len(cursor["entries"]), projects.MAX_ENTRIES)
        self.assertTrue(base.is_dir())

    def test_main_prints_json(self):
        write_state(self.config / "Cursor/User", [{"folderUri": self.folder("a").as_uri()}])
        out = io.StringIO()
        env = {"HOME": str(self.home), "XDG_CONFIG_HOME": str(self.config), "PATH": ""}
        with mock.patch.dict(os.environ, env), mock.patch.object(projects.shutil, "which", which_from({"cursor"})), \
                contextlib.redirect_stdout(out):
            projects.main()
        self.assertEqual([e["id"] for e in json.loads(out.getvalue())["editors"]], ["cursor"])


if __name__ == "__main__":
    unittest.main()
