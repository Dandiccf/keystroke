# Browser profiles

Open a new window in any profile of any installed browser from Keystroke.
Turn on **Extensions > Browser profiles**, then type a profile's name in the
main palette, or use `profile work` to search only profiles. Enter opens a new
window in that profile; Ctrl+Enter opens a private window instead (InPrivate
in Edge, Incognito in Chromium, Chrome, Brave and Vivaldi, a private window in
Firefox-family browsers). Profiles you open often rise to the top.

To bind a key straight to the profile list:

```sh
omarchy-shell shell summon omarchy.menu '{"scope":"browser-profiles","title":"Browser profiles"}'
```

**Show profiles in the main search** (on by default) controls whether profile
names match at the root; with it off, profiles appear only after the `profile`
command or on this extension's screen. The root needs at least two
characters and matches profile names and account emails only; the browser's
name is searched only by the command (`profile edge personal`), since at the
root it would match every profile of that browser. The command prefix can be renamed under
`providers.browser-profiles` in Keystroke's configuration.

## Browsers

- Chromium family: Chromium, Google Chrome (stable/beta/dev), Brave, Vivaldi,
  Microsoft Edge (stable/beta/dev). Profiles and their display names come from
  `Local State` (`profile.info_cache`) under the browser's configuration
  directory (`$CHROME_CONFIG_HOME`, else `$XDG_CONFIG_HOME`, else
  `~/.config`). Guest, system, ephemeral and hidden profiles, and entries whose
  directory no longer exists, are left out. Without a readable `Local State`,
  the `Default` and `Profile *` directories are listed under their directory
  names. Launched with `--profile-directory=<dir> --new-window`.
- Firefox family: Firefox, Firefox ESR, LibreWolf, Zen. Profiles come from
  `profiles.ini` (the XDG location first, then the legacy dot directory),
  relative and absolute paths. Launched with `--profile <path> --browser`;
  a profile that is not running starts its own instance, one that is running
  gets a new window. Firefox and Firefox ESR share one profile directory, so
  with both installed the profiles are listed once, under Firefox.
- Flatpak installs of the same browsers (user or system installation), read
  from `~/.var/app/<app-id>` and launched with `flatpak run <app-id>`.
- A browser is listed only if its binary is on `PATH` (or its Flatpak is
  installed) and it has profile data. Browsers that share one profile
  directory are listed once. At most 200 profiles per browser.
- When `uwsm-app` is available, launches go through `uwsm-app --`, as
  Omarchy's own launchers do, so the browser runs in its own scope rather than
  inside the shell's.

## Data access and dependencies

Needs Python 3 (standard library only). On every palette open, the service
runs `python3 bin/profiles.py` once, asynchronously; it reads only
`Local State` (up to 32 MB) and `profiles.ini` (up to 1 MB), never history,
cookies or any other profile data, and prints the list as JSON. Typing only
filters the list kept in memory; nothing runs per keystroke. The scan takes
about a tenth of a second and can finish after the palette closes; a
five-second watchdog stops a stuck one. A scan that fails or times out keeps
the last list that had profiles and says so only when nothing is listed; a
successful scan replaces the list, even with an empty one. No network calls,
no files written, nothing else runs while the palette is closed. Disabling the
extension destroys the service and stops the scan.

Row ids are `<browser>:<profile directory or path>`, so renaming a profile
keeps its place in Keystroke's frecency.

## Verification

```sh
bin/keystroke check-extensions extensions/browser-profiles
python3 -m unittest discover -s extensions/browser-profiles/tests -p 'test_*.py'
python3 extensions/browser-profiles/tests/palette_check.py
```

Tests use synthetic profiles: Chromium naming, accounts and skipped
guest/ephemeral/hidden entries, a corrupt `Local State`, `profiles.ini` with
relative and absolute paths, Flatpak, `CHROME_CONFIG_HOME`, a shared Firefox
directory, the per-browser cap, launch argv (including hostile names), the
rescan policy and root versus command matching. The offscreen palette check
covers loading, the screen listing, the command, root search and its switch,
launch effects and unload.
