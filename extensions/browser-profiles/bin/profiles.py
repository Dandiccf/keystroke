#!/usr/bin/env python3
"""List installed browsers and their profiles as JSON for Keystroke.

Prints {"browsers": [...]} on stdout, or {"browsers": [], "error": "..."}. Each browser carries the
argv prefix that starts it (`launch`); the QML side appends the profile flags.
Reads only profile metadata (Chromium's `Local State`, Firefox's
`profiles.ini`), never history, cookies or other profile data.
"""

import configparser
import json
import os
import shutil
import sys
from pathlib import Path

LOCAL_STATE_LIMIT = 32 * 1024 * 1024
INI_LIMIT = 1024 * 1024
MAX_PROFILES = 200  # per browser

# key: (display name, config dir under XDG config, binaries in order of preference, private-window flag, icon)
CHROMIUM = {
    "chromium": ("Chromium", "chromium", ("chromium", "chromium-browser"), "--incognito", "chromium"),
    "google-chrome": ("Google Chrome", "google-chrome", ("google-chrome-stable", "google-chrome"), "--incognito", "google-chrome"),
    "google-chrome-beta": ("Google Chrome Beta", "google-chrome-beta", ("google-chrome-beta",), "--incognito", "google-chrome-beta"),
    "google-chrome-unstable": ("Google Chrome Dev", "google-chrome-unstable", ("google-chrome-unstable",), "--incognito", "google-chrome-unstable"),
    "brave": ("Brave", "BraveSoftware/Brave-Browser", ("brave", "brave-browser"), "--incognito", "brave-browser"),
    "vivaldi": ("Vivaldi", "vivaldi", ("vivaldi-stable", "vivaldi"), "--incognito", "vivaldi"),
    "microsoft-edge": ("Microsoft Edge", "microsoft-edge", ("microsoft-edge-stable", "microsoft-edge"), "--inprivate", "microsoft-edge"),
    "microsoft-edge-beta": ("Microsoft Edge Beta", "microsoft-edge-beta", ("microsoft-edge-beta",), "--inprivate", "microsoft-edge-beta"),
    "microsoft-edge-dev": ("Microsoft Edge Dev", "microsoft-edge-dev", ("microsoft-edge-dev",), "--inprivate", "microsoft-edge-dev"),
}
# key: (display name, binaries, profile roots as (base, relative path), icon); base is "home" or "config"
FIREFOX = {
    "firefox": ("Firefox", ("firefox",), (("config", "mozilla/firefox"), ("home", ".mozilla/firefox")), "firefox"),
    "firefox-esr": ("Firefox ESR", ("firefox-esr",), (("config", "mozilla/firefox"), ("home", ".mozilla/firefox")), "firefox-esr"),
    "librewolf": ("LibreWolf", ("librewolf",), (("config", "librewolf/librewolf"), ("config", "librewolf"), ("home", ".librewolf")), "librewolf"),
    "zen": ("Zen", ("zen-browser", "zen"), (("config", "zen"), ("home", ".zen")), "zen-browser"),
}
# Flatpak app id -> key above
FLATPAKS = {
    "org.chromium.Chromium": "chromium",
    "com.google.Chrome": "google-chrome",
    "com.brave.Browser": "brave",
    "com.vivaldi.Vivaldi": "vivaldi",
    "com.microsoft.Edge": "microsoft-edge",
    "org.mozilla.firefox": "firefox",
    "io.gitlab.librewolf-community": "librewolf",
    "app.zen_browser.zen": "zen",
}
SKIP_DIRS = {"System Profile", "Guest Profile"}


def chromium_profiles(data):
    """Profiles of one Chromium user data dir, named as the browser's profile menu names them."""
    found, cache = {}, {}
    state = data / "Local State"
    try:
        if state.stat().st_size <= LOCAL_STATE_LIMIT:
            with state.open(encoding="utf-8") as f:
                cache = ((json.load(f) or {}).get("profile") or {}).get("info_cache") or {}
    except (OSError, ValueError, AttributeError):
        cache = {}
    if not isinstance(cache, dict):
        cache = {}
    for name, info in cache.items():
        if not isinstance(name, str) or not isinstance(info, dict) or "/" in name or name in SKIP_DIRS or name in (".", ".."):
            continue
        if info.get("is_ephemeral") or info.get("is_omitted_from_profile_list"):
            continue
        if not (data / name).is_dir():
            continue
        account = info.get("user_name") if isinstance(info.get("user_name"), str) else ""
        label = info.get("name") if isinstance(info.get("name"), str) and info.get("name").strip() else name
        found[name] = {"key": name, "dir": name, "name": label.strip()[:200], "account": account.strip()[:200]}
    if not cache:
        # No readable Local State: fall back to the directories themselves.
        try:
            for p in data.iterdir():
                if p.is_dir() and (p.name == "Default" or p.name.startswith("Profile ")):
                    found[p.name] = {"key": p.name, "dir": p.name, "name": p.name, "account": ""}
        except OSError:
            pass
    return list(found.values())


def firefox_profiles(root):
    ini = configparser.RawConfigParser(strict=False, interpolation=None)
    path = root / "profiles.ini"
    try:
        if path.stat().st_size > INI_LIMIT:
            return []
        ini.read(path, encoding="utf-8")
    except (OSError, configparser.Error, UnicodeDecodeError):
        return []
    found = []
    for section in ini.sections():
        if not section.startswith("Profile") or not ini.has_option(section, "Name") or not ini.has_option(section, "Path"):
            continue
        name, rel = ini.get(section, "Name").strip(), ini.get(section, "Path").strip()
        relative = ini.get(section, "IsRelative", fallback="1").strip() != "0"
        where = (root / rel) if relative else Path(rel)
        if name and where.is_dir():
            found.append({"key": str(where), "dir": "", "name": name[:200], "account": ""})
    return found


def flatpak_installed(app, home):
    roots = [home / ".local/share/flatpak/app", Path("/var/lib/flatpak/app")]
    return any((r / app).is_dir() for r in roots)


def discover(home=None, config=None, which=None):
    which = which or shutil.which
    home = Path(home or os.environ.get("HOME") or Path.home())
    config = Path(config or os.environ.get("XDG_CONFIG_HOME") or home / ".config")
    chrome_config = Path(os.environ.get("CHROME_CONFIG_HOME") or config)
    runner = ["uwsm-app", "--"] if which("uwsm-app") else []
    browsers, seen = [], set()

    def add(entry, profiles):
        profiles = sorted(profiles, key=lambda p: (p["name"].casefold(), p["key"]))[:MAX_PROFILES]
        if profiles:
            entry["profiles"] = profiles
            browsers.append(entry)

    for key, (name, rel, bins, private, icon) in CHROMIUM.items():
        binary = next((b for b in bins if which(b)), None)
        data = chrome_config / rel
        if binary and data.is_dir() and data.resolve() not in seen:
            seen.add(data.resolve())
            add({"id": key, "name": name, "family": "chromium", "icon": icon, "private": private,
                 "launch": runner + [which(binary)]}, chromium_profiles(data))
    for key, (name, bins, roots, icon) in FIREFOX.items():
        binary = next((b for b in bins if which(b)), None)
        root = next((r for r in ((config if b == "config" else home) / p for b, p in roots) if (r / "profiles.ini").is_file()), None)
        if binary and root and root.resolve() not in seen:
            seen.add(root.resolve())
            add({"id": key, "name": name, "family": "firefox", "icon": icon, "private": "--private-window",
                 "launch": runner + [which(binary)]}, firefox_profiles(root))
    flatpak = which("flatpak")
    for app, key in FLATPAKS.items() if flatpak else ():
        if not flatpak_installed(app, home):
            continue
        base = home / ".var/app" / app
        launch = runner + [flatpak, "run", app]
        if key in CHROMIUM:
            name, rel, _, private, _ = CHROMIUM[key]
            data = base / "config" / rel
            if data.is_dir():
                add({"id": "flatpak:" + app, "name": name + " (Flatpak)", "family": "chromium", "icon": app,
                     "private": private, "launch": launch}, chromium_profiles(data))
        else:
            name, _, roots, _ = FIREFOX[key]
            root = next((r for r in ((base / "config" if b == "config" else base) / p for b, p in roots) if (r / "profiles.ini").is_file()), None)
            if root:
                add({"id": "flatpak:" + app, "name": name + " (Flatpak)", "family": "firefox", "icon": app,
                     "private": "--private-window", "launch": launch}, firefox_profiles(root))
    return {"browsers": browsers}


def main():
    try:
        result = discover()
    except Exception as exc:  # never leave the palette without an answer
        result = {"browsers": [], "error": "Could not list browser profiles: %s" % type(exc).__name__}
    json.dump(result, sys.stdout, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
