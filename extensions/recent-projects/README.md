# Recent projects

Reopen a folder, workspace or remote that VS Code, VSCodium, Cursor or
Windsurf opened recently, from Keystroke. Turn on **Extensions > Recent
projects**, then type a project's name in the main palette, or use
`proj keystroke` to search only projects. Enter opens the project in the
editor it was recent in; Ctrl+Enter opens a terminal in its folder (the
folder that holds it, for a workspace file). Projects you open often rise to
the top; otherwise the editors' own most-recent-first order is kept.

To bind a key straight to the project list:

```sh
omarchy-shell shell summon omarchy.menu '{"scope":"recent-projects","title":"Recent projects"}'
```

**Show projects in the main search** (on by default) controls whether project
names match at the root; with it off, projects appear only after the `proj`
command or on this extension's screen. The root needs at least two characters
and matches project names only; the path, the remote and the editor's name are
searched only by the command (`proj cursor dotfiles`, `proj ~/work`), since at
the root `git` would match every project under `~/git`. **Include recent
files** (off by default) also lists single files the editors opened. The
command prefix can be renamed under `providers.recent-projects` in Keystroke's
configuration.

## Editors

- Visual Studio Code (`Code`), Code - OSS (Arch's `code` package), VS Code
  Insiders, VSCodium, Cursor and Windsurf, each read from
  `$XDG_CONFIG_HOME/<editor>/User/globalStorage/state.vscdb` (else
  `~/.config`). Flatpak installs of VS Code and VSCodium (user or system
  installation) are read from `~/.var/app/<app-id>` and launched with
  `flatpak run <app-id>`.
- An editor is listed only if its binary is on `PATH` (or its Flatpak is
  installed) and it has a recent list. The same project in two editors is
  listed once per editor, with the editor's name in the subtitle.
- Local entries whose path no longer exists are left out, as are untitled
  workspaces (the editor's own `Workspaces/` folder). Remote entries (SSH, WSL,
  dev containers, tunnels) are listed as they are, since their existence
  cannot be checked from here; they have no terminal action. At most 500
  entries per editor.
- Launched with `--folder-uri <uri>` for a folder and `--file-uri <uri>` for a
  workspace or file, so remote URIs reopen their remote and nothing a path
  contains can read as a flag. The terminal is `xdg-terminal-exec --dir=<folder>`,
  Omarchy's default terminal.
- When `uwsm-app` is available, launches go through `uwsm-app --`, as
  Omarchy's own launchers do, so the editor runs in its own scope rather than
  inside the shell's.

Zed and JetBrains IDEs keep their recent lists in other formats and are not
read.

## Data access and dependencies

Needs Python 3 (standard library only, including `sqlite3`). On every palette
open, the service runs `python3 bin/projects.py` once, asynchronously; it opens
each editor's `state.vscdb` read-only, reads only the
`history.recentlyOpenedPathsList` key (up to 8 MB), and prints the list as
JSON. It never reads the database's other keys, workspace state or file
contents. Typing only filters the list kept in memory; nothing runs per
keystroke. The scan takes well under a tenth of a second and can finish after
the palette closes; a five-second watchdog stops a stuck one, and a database
locked by a running editor is given one second. A scan that fails or times out
keeps the last list that had entries and says so only when nothing is listed;
a successful scan replaces the list, even with an empty one. No network calls,
no files written, nothing else runs while the palette is closed. Disabling the
extension destroys the service and stops the scan.

Row ids are `<editor>:<uri>`, so a project keeps its place in Keystroke's
frecency for as long as it stays at the same path.

## Verification

```sh
bin/keystroke check-extensions extensions/recent-projects
python3 -m unittest discover -s extensions/recent-projects/tests -p 'test_*.py'
python3 extensions/recent-projects/tests/palette_check.py
```

Tests use synthetic `state.vscdb` databases: folders, workspaces, files,
missing paths, untitled workspaces, SSH and dev-container remotes, a URI that
reads as a flag, duplicates, a database without the key and a corrupt one,
Code - OSS behind the `code` binary, Flatpak, the per-editor cap, launch and
terminal argv, the rescan policy and root versus command matching. The
offscreen palette check covers loading, the screen listing, the command, root
search and its switch, launch effects and unload.
