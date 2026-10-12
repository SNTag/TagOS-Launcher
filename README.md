# TagOS Launcher

A vibe-coded Windows launcher that integrates my Obsidian setup.

> **Using Flow Launcher instead?** [`flow_plugin/`](flow_plugin/README.md) is a
> Flow Launcher plugin that does the `obs` bookmark search on its own.

Press a hotkey (**Ctrl+Alt+Space** by default) and a command box pops up over
whatever you're doing. Type to switch windows across virtual desktops, or use
a command such as `obs:` to search your Obsidian bookmarks. The rest of the
time it sits in the system tray.

## Commands

| Type | What it does | Enter | Shift+Enter | Ctrl+Enter |
|------|--------------|-------|-------------|------------|
| *(nothing, or any text)* | Lists open windows. Windows on the **current desktop** come first (most recently used first). Windows on **other desktops** come next, in coloured rows with the desktop's name. Typing narrows the list by window title (and process name). | Switch to it (changing desktop if needed) | Bring it to this desktop¹ | Close it |
| `obs:` *query* | Searches your bookmark notes by **title** or **aliases** from their YAML frontmatter. `obs:` on its own lists the most recently changed bookmarks. | Open the note's `source` URL | Open the note in Obsidian | |
| `g:` *query* | Google search (an example **web command**; add your own in Settings). | Open | | |
| `?` | Lists every command. | Use it | | |

Also: **↑/↓/PgUp/PgDn** move, **Tab** completes a command prefix (type `ob`,
then Tab), **Ctrl+C** copies the selected row's URL/title, **Esc** clears the
box (or closes it if already empty). Clicking a row also activates it.

With an empty box, the window you were *previously* using is preselected, so
**hotkey → Enter** flips back and forth like Alt+Tab.

¹ Needs the optional `pyvda` package (installed by `run.bat` from
`requirements.txt`). Without it everything else still works — switching to a
window on another desktop relies on Windows following the window there.

### Obsidian bookmarks

A bookmark is any `.md` note in your bookmarks folder (sub-folders included)
with frontmatter like:

```yaml
---
title: Python asyncio docs
aliases: [event loop, coroutines]
source: https://docs.python.org/3/library/asyncio.html
---
```

- No `title`? The file name is used.
- `aliases` may be a list or a single string.
- Notes without a URL are still listed (Enter opens them in Obsidian), or can
  be hidden.
- The field names are **customisable** in Settings → Obsidian. You can list
  several, separated by commas: `url, source, link` uses the first one present.
- The folder is re-checked every time you open the launcher (only changed
  notes are re-read), so new bookmarks show up immediately.

On first start, if no folder is set, the launcher looks in the vaults Obsidian
knows about for a folder named `Snippets`, `Bookmarks` or `Clippings`. Settings
→ Obsidian → **From vault ▾** lets you pick any folder of any vault.

## Settings

Right-click the tray icon → **Settings…** (or run
`python -m tagos_launcher --settings`). Everything is saved to
`%APPDATA%\TagOS Launcher\config.json`.

- **General** — the hotkey (click the box and press the combination; it must
  include Ctrl, Alt, Shift or Win), light/dark theme, maximum results, hide on
  focus loss, start-up notification.
- **Windows** — show/hide other desktops, Alt+Tab-style preselection, the row
  colour for each desktop, and windows to hide (by process name, like
  `TextInputHost.exe`, or by text in the title).
- **Obsidian** — command prefix, bookmarks folder, frontmatter field names,
  what to do with notes without a URL, and a **Test** button that counts what
  it finds.
- **Web commands** — `prefix → URL` searches. `{query}` in the URL is replaced
  by what you type, e.g. `yt:` → `https://www.youtube.com/results?search_query={query}`.

A log is kept at `%APPDATA%\TagOS Launcher\launcher.log`.

## Running it

You'll need [Python 3.9+](https://www.python.org/downloads/) on your `PATH`.

### From TagOS Manager (recommended)

1. Copy `integration\TagOS Launcher.bat` and
   `integration\TagOS Launcher.bat.yaml` into your **TagOS Manager scripts
   folder**.
2. Edit the `.bat` and set `LAUNCHER_DIR` to where this repository lives.
3. In TagOS Manager, tick **Persistent** and **Run on startup** on the
   *TagOS Launcher* card.

TagOS Manager then starts the launcher when it opens, shows its log in a tab,
and restarts it if it ever exits. The first run creates `.venv` and installs
the dependencies, which takes a minute.

Optionally also copy `integration\TagOS Launcher Settings.bat` (same
`LAUNCHER_DIR` edit) for a one-click **Settings** card.

### On its own

Double-click `run.bat`. It creates `.venv` on first run, then starts the
launcher in the background (tray only, no console window).

### Command line

Only one launcher runs at a time; running it again sends a message to the
running copy instead:

```bat
.venv\Scripts\python -m tagos_launcher                 :: start
.venv\Scripts\python -m tagos_launcher --show          :: open the launcher
.venv\Scripts\python -m tagos_launcher --show "obs:"   :: open it pre-filled
.venv\Scripts\python -m tagos_launcher --settings      :: open Settings
.venv\Scripts\python -m tagos_launcher --quit          :: stop it
```

`--show "obs:"` is handy for a second hotkey (e.g. from AutoHotkey or a
Stream Deck) that jumps straight into bookmark search.

### Standalone `.exe`

`build_exe.bat` produces `dist\TagOS Launcher.exe` with PyInstaller.

## Development

```bat
.venv\Scripts\python -m pip install pytest
.venv\Scripts\python -m pytest
```

The core (matching, frontmatter parsing, commands) is tested without Windows;
the Win32 parts (`winapi.py`, `desktops.py`, `hotkey.py`) are no-ops elsewhere.

```
tagos_launcher/
  __main__.py      # CLI + single-instance messaging
  app.py           # tray icon, hotkey, settings, wiring
  config.py        # %APPDATA%\TagOS Launcher\config.json
  hotkey.py        # global hotkey (RegisterHotKey)
  winapi.py        # list / activate / close windows (Alt+Tab rules)
  desktops.py      # virtual desktops (documented COM API + registry, pyvda extras)
  obsidian.py      # frontmatter parsing, bookmark index, vault detection
  matching.py      # fuzzy scoring shared by all commands
  commands/
    base.py               # Item / Action / Command
    windows.py            # default: window switcher
    obsidian_bookmarks.py # obs:
    web.py                # g: and other URL-template commands
    __init__.py           # registry, prefix routing, ? help
  ui/
    launcher_window.py    # the pop-up
    settings_dialog.py    # settings GUI
    theme.py              # light/dark palettes (shared look with TagOS Manager)
```

### Adding a command

Subclass `Command` in `commands/`, give it a `prefix`, return `Item`s from
`query(text)` (each with up to three `Action`s for Enter / Shift+Enter /
Ctrl+Enter), and register it in `LauncherApp._build_registry`.
