"""Flow Launcher plugin: search Obsidian bookmark notes by YAML title/aliases.

Type ``obs <query>`` in Flow Launcher. Each Markdown note in the bookmarks
folder is matched by the title and aliases in its YAML frontmatter; Enter opens
the URL from the configured field (``source`` by default). The context menu
(Shift+Enter / right arrow) opens the note itself in Obsidian.

Self-contained on purpose: it runs on Flow Launcher's bundled Python with no
packages installed. PyYAML is used when available, otherwise a small parser
that understands the frontmatter shapes Obsidian writes.
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
ICON = "Images\\icon.png"
CACHE_FILE = os.path.join(tempfile.gettempdir(), "flow-obsidian-bookmarks-cache.json")
HEAD_BYTES = 64 * 1024
GUESS_FOLDER_NAMES = ("Snippets", "snippets", "Bookmarks", "bookmarks", "Clippings")

DEFAULTS = {
    "folder": "",
    "recursive": True,
    "title_field": "title",
    "aliases_field": "aliases",
    "url_field": "source",
    "without_url": "Open in Obsidian",
    "max_results": "30",
}


# ---------------------------------------------------------------- frontmatter
def _scalar(text: str) -> Any:
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        return text[1:-1]
    return text


def _simple_yaml(block: str) -> Dict[str, Any]:
    """Fallback parser for ``key: value``, ``key: [a, b]`` and block lists."""
    data: Dict[str, Any] = {}
    key: Optional[str] = None
    for line in block.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        item = re.match(r"^\s*-\s*(.*)$", line)
        if item and key is not None:
            if not isinstance(data.get(key), list):
                data[key] = []
            data[key].append(_scalar(item.group(1)))
            continue
        pair = re.match(r"^([^\s:#][^:]*):\s*(.*)$", line)
        if not pair:
            continue
        key, value = pair.group(1).strip(), pair.group(2).strip()
        if value.startswith("[") and value.endswith("]"):
            data[key] = [_scalar(v) for v in value[1:-1].split(",") if v.strip()]
        else:
            data[key] = _scalar(value) if value else None
    return data


def parse_frontmatter(text: str) -> Dict[str, Any]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    for i in range(1, len(lines)):
        if lines[i].strip() in ("---", "..."):
            block = "\n".join(lines[1:i])
            try:
                import yaml  # type: ignore

                data = yaml.safe_load(block)
            except ImportError:
                data = _simple_yaml(block)
            except Exception:
                return {}
            return data if isinstance(data, dict) else {}
    return {}


def field_names(spec: str) -> List[str]:
    return [n.strip() for n in str(spec or "").split(",") if n.strip()]


def _lookup(meta: Dict[str, Any], name: str) -> Any:
    lowered = name.lower()
    for key, value in meta.items():
        if str(key).lower() == lowered:
            return value
    return None


def _strings(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value if v is not None and str(v).strip()]
    text = str(value).strip()
    return [text] if text else []


def read_note(path: str, title_field: str, aliases_field: str, url_field: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8-sig", errors="replace") as fh:
        meta = parse_frontmatter(fh.read(HEAD_BYTES))
    title = next((v[0] for n in field_names(title_field) for v in [_strings(_lookup(meta, n))] if v), "")
    title = title or os.path.splitext(os.path.basename(path))[0]
    aliases: List[str] = []
    for name in field_names(aliases_field):
        for alias in _strings(_lookup(meta, name)):
            if alias not in aliases and alias != title:
                aliases.append(alias)
    url = next((v[0] for n in field_names(url_field) for v in [_strings(_lookup(meta, n))] if v), "")
    return {"title": title, "aliases": aliases, "url": url}


# ------------------------------------------------------------------- matching
def _token_score(token: str, text: str) -> Optional[float]:
    if text.startswith(token):
        return 100.0 - min(len(text) - len(token), 40) * 0.1
    idx = text.find(token)
    if idx >= 0:
        boundary = not text[idx - 1].isalnum()
        return (80.0 if boundary else 60.0) - min(idx, 40) * 0.25
    if len(token) < 2:
        return None
    pos, gaps = -1, 0
    for ch in token:
        nxt = text.find(ch, pos + 1)
        if nxt < 0:
            return None
        if pos >= 0:
            gaps += nxt - pos - 1
        pos = nxt
    if gaps > len(token) * 4:
        return None
    return max(1.0, 30.0 - gaps)


def score(query: str, text: str) -> Optional[float]:
    tokens = query.lower().split()
    if not tokens:
        return 0.0
    text = text.lower()
    total = 0.0
    for token in tokens:
        s = _token_score(token, text)
        if s is None:
            return None
        total += s
    return total / len(tokens)


# ---------------------------------------------------------------------- index
def obsidian_vaults() -> List[str]:
    base = os.environ.get("APPDATA") or os.path.expanduser("~/.config")
    try:
        with open(os.path.join(base, "obsidian", "obsidian.json"), "r", encoding="utf-8") as fh:
            vaults = json.load(fh).get("vaults", {})
    except (OSError, ValueError, AttributeError):
        return []
    entries = sorted((v for v in vaults.values() if isinstance(v, dict) and v.get("path")),
                     key=lambda v: v.get("ts", 0), reverse=True)
    return [v["path"] for v in entries]


def resolve_folder(configured: str) -> str:
    if configured:
        return os.path.expandvars(os.path.expanduser(configured.strip().strip('"')))
    for vault in obsidian_vaults():
        for name in GUESS_FOLDER_NAMES:
            if os.path.isdir(os.path.join(vault, name)):
                return os.path.join(vault, name)
    return ""


def note_paths(folder: str, recursive: bool) -> List[Tuple[str, float]]:
    found, stack = [], [folder]
    while stack:
        try:
            entries = list(os.scandir(stack.pop()))
        except OSError:
            continue
        for e in entries:
            try:
                if e.is_dir(follow_symlinks=False):
                    if recursive and not e.name.startswith("."):
                        stack.append(e.path)
                elif e.name.lower().endswith(".md"):
                    found.append((e.path, e.stat().st_mtime))
            except OSError:
                continue
    return found


def load_index(folder: str, s: Dict[str, Any]) -> List[Dict[str, Any]]:
    """All notes, re-reading only those changed since the cached copy.

    Flow starts a fresh process for every keystroke, so the parsed notes are
    cached on disk keyed by the settings that affect parsing.
    """
    signature = "|".join([folder, s["title_field"], s["aliases_field"], s["url_field"]])
    cache: Dict[str, Any] = {}
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as fh:
            stored = json.load(fh)
        if stored.get("signature") == signature:
            cache = stored.get("notes", {})
    except (OSError, ValueError):
        pass
    notes, changed = {}, False
    for path, mtime in note_paths(folder, s["recursive"]):
        cached = cache.get(path)
        if cached and cached.get("mtime") == mtime:
            notes[path] = cached
            continue
        try:
            note = read_note(path, s["title_field"], s["aliases_field"], s["url_field"])
        except OSError:
            continue
        note["mtime"] = mtime
        notes[path] = note
        changed = True
    if changed or len(notes) != len(cache):
        try:
            with open(CACHE_FILE, "w", encoding="utf-8") as fh:
                json.dump({"signature": signature, "notes": notes}, fh)
        except OSError:
            pass
    for path, note in notes.items():
        note["path"] = path
    return list(notes.values())


# --------------------------------------------------------------------- plugin
def settings_from(request: Dict[str, Any]) -> Dict[str, Any]:
    s = dict(DEFAULTS)
    for key, value in (request.get("settings") or {}).items():
        if value not in (None, ""):
            s[key] = value
    s["recursive"] = str(s["recursive"]).lower() not in ("false", "0", "no")
    try:
        s["max_results"] = max(1, int(s["max_results"]))
    except (TypeError, ValueError):
        s["max_results"] = 30
    return s


def obsidian_uri(path: str) -> str:
    return "obsidian://open?path=" + quote(os.path.abspath(path), safe="")


def result(title: str, subtitle: str = "", method: str = "", params: Optional[list] = None,
           score_: int = 0, copy: str = "", context: Any = None) -> Dict[str, Any]:
    r: Dict[str, Any] = {"Title": title, "SubTitle": subtitle, "IcoPath": ICON, "Score": score_}
    if method:
        r["JsonRPCAction"] = {"method": method, "parameters": params or [], "dontHideAfterAction": False}
    if copy:
        r["CopyText"] = copy
    if context is not None:
        r["ContextData"] = context
    return r


def query(text: str, s: Dict[str, Any]) -> List[Dict[str, Any]]:
    folder = resolve_folder(s["folder"])
    if not folder or not os.path.isdir(folder):
        return [result("Bookmarks folder not found",
                       "Set it in Flow Launcher → Settings → Plugins → Obsidian Bookmarks"
                       + (f" (tried {folder})" if folder else ""))]
    hide_without_url = str(s["without_url"]).lower().startswith("hide")
    scored = []
    for note in load_index(folder, s):
        if not note["url"] and hide_without_url:
            continue
        if not text.strip():
            scored.append((note["mtime"], note, None))  # empty query: most recent first
            continue
        best, via = score(text, note["title"]), None
        for alias in note["aliases"]:
            a = score(text, alias)
            if a is not None and (best is None or a > best):
                best, via = a, alias
        if best is not None:
            scored.append((best, note, via))
    scored.sort(key=lambda t: (-t[0], t[1]["title"].lower()))

    results = []
    for rank, (_, note, via) in enumerate(scored[: s["max_results"]]):
        uri = obsidian_uri(note["path"])
        bits = [f"alias: {via}"] if via else ([", ".join(note["aliases"][:3])] if note["aliases"] else [])
        bits.append(note["url"] or "no URL — opens the note in Obsidian")
        target = note["url"] or uri
        results.append(result(
            note["title"], "  ·  ".join(bits), "open", [target],
            score_=1000 - rank, copy=target, context=[note["path"], note["url"]],
        ))
    if not results:
        results.append(result("No matching bookmarks", folder))
    return results


def context_menu(data: Any) -> List[Dict[str, Any]]:
    path, url = (list(data) + ["", ""])[:2] if isinstance(data, list) else ("", "")
    items = []
    if path:
        items.append(result("Open note in Obsidian", path, "open", [obsidian_uri(path)]))
    if url:
        items.append(result("Open link", url, "open", [url]))
    return items


def open_target(target: str) -> None:
    if os.name == "nt":
        os.startfile(target)  # type: ignore[attr-defined]  # handles http(s):// and obsidian://
    else:
        import webbrowser

        webbrowser.open(target)


def main(argv: List[str]) -> None:
    request = json.loads(argv[1]) if len(argv) > 1 else {"method": "query", "parameters": [""]}
    method = request.get("method")
    params = request.get("parameters") or []
    if method == "query":
        out = query(params[0] if params else "", settings_from(request))
    elif method == "context_menu":
        out = context_menu(params[0] if params else None)
    elif method == "open":
        open_target(params[0])
        return
    else:
        out = []
    print(json.dumps({"result": out}))


if __name__ == "__main__":
    main(sys.argv)
