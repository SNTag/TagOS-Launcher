# Obsidian Bookmarks — Flow Launcher plugin

Search your Obsidian bookmark notes from [Flow Launcher](https://flowlauncher.com)
by the **title** or **aliases** in their YAML header, and open the URL in their
`source` field.

```
obs asyncio        → "Python asyncio docs" (matched by title)
obs event loop     → same note (matched by alias)
obs                → most recently changed bookmarks
```

- **Enter** opens the note's `source` URL in your browser.
- **Shift+Enter** (or →) shows the context menu, which has **Open note in Obsidian**.
- **Ctrl+C** copies the URL.

A note looks like this:

```yaml
---
title: Python asyncio docs
aliases: [event loop, coroutines]
source: https://docs.python.org/3/library/asyncio.html
---
```

No `title` → the file name is used. Notes without a URL are still listed and
open in Obsidian, unless you choose to hide them.

## Install

1. Copy this `flow_plugin` folder to
   `%APPDATA%\FlowLauncher\Plugins\` and rename it `Obsidian Bookmarks`.
   (Portable install: `<Flow folder>\UserData\Plugins\`.)
2. Restart Flow Launcher. If it asks about Python, let it download its own
   copy, or point it at yours under **Settings → General → Python path**.
3. **Settings → Plugins → Obsidian Bookmarks**:
   - **Bookmarks folder** — e.g. `C:\Users\you\Vault\Snippets`. Leave it empty
     to use a `Snippets`, `Bookmarks` or `Clippings` folder found in your
     Obsidian vaults.
   - **Title / Aliases / URL field** — the YAML header names to read. List
     several separated by commas (`source, url`) and the first one present is
     used.
   - **Action keyword** — `obs` by default; change it here (e.g. to `obs:`).

No Python packages are needed. If PyYAML is installed it's used; otherwise a
built-in parser handles the usual Obsidian header formats.

## Notes

- Flow runs the plugin fresh for each keystroke, so parsed notes are cached in
  `%TEMP%\flow-obsidian-bookmarks-cache.json`, and only changed notes are
  re-read. Delete that file to force a full re-read.
- Test from a terminal without Flow:
  `python main.py "{\"method\":\"query\",\"parameters\":[\"loop\"],\"settings\":{\"folder\":\"C:\\\\path\\\\to\\\\Snippets\"}}"`
