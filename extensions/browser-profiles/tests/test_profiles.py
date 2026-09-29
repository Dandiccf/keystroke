import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "bin"))
import profiles  # noqa: E402


def which_from(available):
    return lambda name: "/usr/bin/" + name if name in available else None


class DiscoverTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.config = self.home / ".config"

    def tearDown(self):
        self.tmp.cleanup()

    def chromium(self, rel, cache, dirs):
        data = self.config / rel
        for d in dirs:
            (data / d).mkdir(parents=True)
        (data / "Local State").write_text(json.dumps({"profile": {"info_cache": cache}}))
        return data

    def test_chromium_names_accounts_and_skips(self):
        self.chromium("microsoft-edge", {
            "Default": {"name": "Work", "user_name": "me@example.org"},
            "Profile 1": {"name": "Zürich ü", "user_name": ""},
            "Profile 2": {"name": "Gone"},
            "Profile 3": {"name": "Temp", "is_ephemeral": True},
            "Guest Profile": {"name": "Guest"},
            "../escape": {"name": "Escape"},
            "..": {"name": "Parent"},
            ".": {"name": "Self"},
        }, ["Default", "Profile 1", "Profile 3", "Guest Profile"])
        result = profiles.discover(self.home, self.config, which_from({"microsoft-edge-stable", "uwsm-app"}))
        [edge] = result["browsers"]
        self.assertEqual(edge["launch"], ["uwsm-app", "--", "/usr/bin/microsoft-edge-stable"])
        self.assertEqual(edge["private"], "--inprivate")
        self.assertEqual([(p["dir"], p["name"], p["account"]) for p in edge["profiles"]],
                         [("Default", "Work", "me@example.org"), ("Profile 1", "Zürich ü", "")])

    def test_missing_binary_or_data_is_skipped(self):
        self.chromium("chromium", {"Default": {"name": "Me"}}, ["Default"])
        self.assertEqual(profiles.discover(self.home, self.config, which_from(set()))["browsers"], [])
        self.assertEqual(profiles.discover(self.home, self.config, which_from({"google-chrome-stable"}))["browsers"], [])

    def test_unreadable_local_state_falls_back_to_directories(self):
        data = self.chromium("chromium", {}, ["Default", "Profile 4", "Crashpad"])
        (data / "Local State").write_text("{not json")
        [browser] = profiles.discover(self.home, self.config, which_from({"chromium"}))["browsers"]
        self.assertEqual(browser["launch"], ["/usr/bin/chromium"])
        self.assertEqual([p["dir"] for p in browser["profiles"]], ["Default", "Profile 4"])

    def test_firefox_profiles_ini(self):
        root = self.home / ".mozilla/firefox"
        (root / "abc.default").mkdir(parents=True)
        absolute = self.home / "elsewhere"
        absolute.mkdir()
        (root / "profiles.ini").write_text(
            "[General]\nStartWithLastProfile=1\n\n"
            "[Profile0]\nName=default\nIsRelative=1\nPath=abc.default\n\n"
            "[Profile1]\nName=Work\nIsRelative=0\nPath=%s\n\n"
            "[Profile2]\nName=Missing\nIsRelative=1\nPath=nope\n\n"
            "[Install123]\nDefault=abc.default\n" % absolute)
        [fx] = profiles.discover(self.home, self.config, which_from({"firefox"}))["browsers"]
        self.assertEqual(fx["family"], "firefox")
        self.assertEqual([(p["name"], p["key"]) for p in fx["profiles"]],
                         [("default", str(root / "abc.default")), ("Work", str(absolute))])

    def test_chrome_config_home(self):
        other = self.home / "chrome-config"
        (other / "chromium/Default").mkdir(parents=True)
        (other / "chromium/Local State").write_text(json.dumps({"profile": {"info_cache": {"Default": {"name": "Moved"}}}}))
        with mock.patch.dict(os.environ, {"CHROME_CONFIG_HOME": str(other)}):
            [browser] = profiles.discover(self.home, self.config, which_from({"chromium"}))["browsers"]
        self.assertEqual(browser["profiles"][0]["name"], "Moved")

    def test_flatpak(self):
        (self.home / ".local/share/flatpak/app/com.microsoft.Edge").mkdir(parents=True)
        data = self.home / ".var/app/com.microsoft.Edge/config/microsoft-edge"
        (data / "Default").mkdir(parents=True)
        (data / "Local State").write_text(json.dumps({"profile": {"info_cache": {"Default": {"name": "Boxed"}}}}))
        fx = self.home / ".var/app/org.mozilla.firefox/.mozilla/firefox"
        (fx / "p.default").mkdir(parents=True)
        (fx / "profiles.ini").write_text("[Profile0]\nName=default\nPath=p.default\n")
        # Firefox's data without the Flatpak installed is not listed.
        result = profiles.discover(self.home, self.config, which_from({"flatpak"}))
        [edge] = result["browsers"]
        self.assertEqual(edge["id"], "flatpak:com.microsoft.Edge")
        self.assertEqual(edge["launch"], ["/usr/bin/flatpak", "run", "com.microsoft.Edge"])
        self.assertEqual(edge["private"], "--inprivate")
        self.assertEqual(edge["profiles"][0]["dir"], "Default")
        (self.home / ".local/share/flatpak/app/org.mozilla.firefox").mkdir(parents=True)
        ids = [b["id"] for b in profiles.discover(self.home, self.config, which_from({"flatpak"}))["browsers"]]
        self.assertEqual(ids, ["flatpak:com.microsoft.Edge", "flatpak:org.mozilla.firefox"])

    def test_shared_directory_listed_once(self):
        root = self.home / ".mozilla/firefox"
        (root / "a.default").mkdir(parents=True)
        (root / "profiles.ini").write_text("[Profile0]\nName=default\nPath=a.default\n")
        ids = [b["id"] for b in profiles.discover(self.home, self.config, which_from({"firefox", "firefox-esr"}))["browsers"]]
        self.assertEqual(ids, ["firefox"])

    def test_cap_is_per_browser(self):
        names = ["Profile %d" % i for i in range(profiles.MAX_PROFILES + 5)]
        self.chromium("microsoft-edge", {n: {"name": n} for n in names}, names)
        self.chromium("chromium", {"Default": {"name": "Me"}}, ["Default"])
        result = profiles.discover(self.home, self.config, which_from({"microsoft-edge-stable", "chromium"}))
        self.assertEqual({b["id"]: len(b["profiles"]) for b in result["browsers"]},
                         {"chromium": 1, "microsoft-edge": profiles.MAX_PROFILES})

    def test_main_prints_json(self):
        self.chromium("chromium", {"Default": {"name": "Me"}}, ["Default"])
        out = io.StringIO()
        env = {"HOME": str(self.home), "XDG_CONFIG_HOME": str(self.config), "PATH": ""}
        with mock.patch.dict(os.environ, env), mock.patch.object(profiles.shutil, "which", which_from({"chromium"})), \
                contextlib.redirect_stdout(out):
            profiles.main()
        self.assertEqual([b["id"] for b in json.loads(out.getvalue())["browsers"]], ["chromium"])


if __name__ == "__main__":
    unittest.main()
