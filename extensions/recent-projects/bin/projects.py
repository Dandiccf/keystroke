#!/usr/bin/env python3
"""List the recent projects of installed VS Code-family editors as JSON for Keystroke.

Prints {"editors": [...]} on stdout. Each editor carries the argv prefix that
starts it (`launch`); the QML side appends `--folder-uri` or `--file-uri`.
Reads only the editor's recently-opened list (the `history.recentlyOpenedPathsList`
key of `User/globalStorage/state.vscdb`, opened read-only), never the other
keys, workspace state or file contents.
"""

import json
import os
import re
import shutil
import sqlite3
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

VALUE_LIMIT = 8 * 1024 * 1024
MAX_ENTRIES = 500  # per editor
RECENT_KEY = "history.recentlyOpenedPathsList"
URI = re.compile(r"^[a-z][a-z0-9+.-]*://", re.I)

# key: (display name, config dir under XDG config, binaries in order of preference, icon names)
EDITORS = {
    "vscode": ("Visual Studio Code", "Code", ("code",), ("vscode", "visual-studio-code", "code")),
    "code-oss": ("Code - OSS", "Code - OSS", ("code-oss", "code"), ("com.visualstudio.code.oss", "code-oss")),
    "vscode-insiders": ("VS Code Insiders", "Code - Insiders", ("code-insiders",), ("vscode-insiders", "code-insiders")),
    "vscodium": ("VSCodium", "VSCodium", ("codium", "vscodium"), ("vscodium", "codium")),
    "cursor": ("Cursor", "Cursor", ("cursor",), ("co.anysphere.cursor", "cursor")),
    "windsurf": ("Windsurf", "Windsurf", ("windsurf",), ("windsurf",)),
}
# Flatpak app id -> key above
FLATPAKS = {
    "com.visualstudio.code": "vscode",
    "com.vscodium.codium": "vscodium",
}
REMOTES = {
    "ssh-remote": "SSH", "wsl": "WSL", "tunnel": "Tunnel", "codespaces": "Codespaces",
    "dev-container": "Dev Container", "attached-container": "Container",
}


def remote_name(authority):
    kind, _, rest = authority.partition("+")
    name = REMOTES.get(kind, kind or "Remote")
    # SSH hosts from a config object arrive hex-encoded; only a plain name is worth showing.
    if rest and kind in ("ssh-remote", "wsl", "tunnel") and re.fullmatch(r"[\w.@-]{1,64}", rest):
        return "%s: %s" % (name, rest)
    return name


def entry(item, home, untitled):
    """One recent entry as {kind, uri, title, where, dir, remote}, or None to leave it out."""
    if not isinstance(item, dict):
        return None
    if isinstance(item.get("folderUri"), str):
        kind, uri = "folder", item["folderUri"]
    elif isinstance(item.get("workspace"), dict) and isinstance(item["workspace"].get("configPath"), str):
        kind, uri = "workspace", item["workspace"]["configPath"]
    elif isinstance(item.get("fileUri"), str):
        kind, uri = "file", item["fileUri"]
    else:
        return None
    if not URI.match(uri) or len(uri) > 4096:
        return None
    parts = urlsplit(uri)
    path = unquote(parts.path)
    name = path.rstrip("/").rsplit("/", 1)[-1] or path or uri
    if kind == "workspace" and name.endswith(".code-workspace"):
        name = name[: -len(".code-workspace")]
    if parts.scheme == "file":
        local = Path(path)
        # An untitled workspace lives in the editor's own storage and has no name worth listing.
        if (kind == "workspace" and untitled in local.parents) or not local.exists():
            return None
        where = "~" + path[len(str(home)):] if path == str(home) or path.startswith(str(home) + "/") else path
        folder = path if kind == "folder" else str(local.parent)
        return {"kind": kind, "uri": uri, "title": name[:200], "where": where[:400], "dir": folder, "remote": ""}
    authority = unquote(parts.netloc)
    remote = remote_name(authority) if parts.scheme == "vscode-remote" else parts.scheme
    return {"kind": kind, "uri": uri, "title": name[:200], "where": path[:400], "dir": "", "remote": remote[:80]}


def recent(user, home):
    """Recent entries of one editor's User directory, newest first."""
    db = user / "globalStorage" / "state.vscdb"
    if not db.is_file():
        return []
    try:
        con = sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True, timeout=1)
        try:
            row = con.execute("SELECT value FROM ItemTable WHERE key = ?", (RECENT_KEY,)).fetchone()
        finally:
            con.close()
    except sqlite3.Error:
        return []
    if not row or row[0] is None:
        return []
    value = row[0]
    if len(value) > VALUE_LIMIT:
        return []
    try:
        items = (json.loads(value) or {}).get("entries") or []
    except (ValueError, AttributeError, UnicodeDecodeError):
        return []
    found, seen = [], set()
    for item in items if isinstance(items, list) else ():
        e = entry(item, home, user.parent / "Workspaces")
        if e and e["uri"] not in seen:
            seen.add(e["uri"])
            found.append(e)
            if len(found) >= MAX_ENTRIES:
                break
    return found


def flatpak_installed(app, home):
    roots = [home / ".local/share/flatpak/app", Path("/var/lib/flatpak/app")]
    return any((r / app).is_dir() for r in roots)


def discover(home=None, config=None, which=None):
    which = which or shutil.which
    home = Path(home or os.environ.get("HOME") or Path.home())
    config = Path(config or os.environ.get("XDG_CONFIG_HOME") or home / ".config")
    runner = ["uwsm-app", "--"] if which("uwsm-app") else []
    terminal = which("xdg-terminal-exec")
    editors = []

    def add(entry, entries):
        if entries:
            entry["entries"] = entries
            entry["terminal"] = runner + [terminal] if terminal else []
            editors.append(entry)

    for key, (name, rel, bins, icons) in EDITORS.items():
        binary = next((b for b in bins if which(b)), None)
        if binary:
            add({"id": key, "name": name, "icons": list(icons), "launch": runner + [which(binary)]},
                recent(config / rel / "User", home))
    flatpak = which("flatpak")
    for app, key in FLATPAKS.items() if flatpak else ():
        if flatpak_installed(app, home):
            name, rel, _, _ = EDITORS[key]
            add({"id": "flatpak:" + app, "name": name + " (Flatpak)", "icons": [app],
                 "launch": runner + [flatpak, "run", app]}, recent(home / ".var/app" / app / "config" / rel / "User", home))
    return {"editors": editors}


def main():
    try:
        result = discover()
    except Exception as exc:  # never leave the palette without an answer
        result = {"editors": [], "error": "Could not list recent projects: %s" % type(exc).__name__}
    json.dump(result, sys.stdout, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
