import os

import pytest

from tagos_launcher import config
from tagos_launcher.commands import CommandRegistry
from tagos_launcher.commands.obsidian_bookmarks import ObsidianBookmarksCommand
from tagos_launcher.commands.web import WebCommand
from tagos_launcher.commands.windows import WindowsCommand
from tagos_launcher.desktops import Desktop, DesktopInfo
from tagos_launcher.hotkey import MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, parse_hotkey
from tagos_launcher.matching import score
from tagos_launcher.obsidian import BookmarkIndex, parse_frontmatter
from tagos_launcher.winapi import WindowInfo


def test_score_ordering():
    assert score("", "anything") == 0
    assert score("vis", "Visual Studio Code") > score("stu", "Visual Studio Code") > score("udi", "Visual Studio Code")
    assert score("vsc", "Visual Studio Code") is not None
    assert score("zzz", "Visual Studio Code") is None
    assert score("code studio", "Visual Studio Code") is not None
    assert score("code zebra", "Visual Studio Code") is None


@pytest.mark.parametrize("text,expected", [
    ("Ctrl+Alt+Space", (MOD_CONTROL | MOD_ALT, 0x20)),
    ("Meta+K", (MOD_WIN, ord("K"))),
    ("Ctrl+Shift+F12", (MOD_CONTROL | MOD_SHIFT, 0x7B)),
    ("Alt+`", (MOD_ALT, 0xC0)),
    ("Space", None),
    ("Ctrl+Bogus", None),
    ("", None),
])
def test_parse_hotkey(text, expected):
    assert parse_hotkey(text) == expected


def test_config_merge_keeps_new_defaults():
    merged = config.merge(config.DEFAULT_CONFIG, {"obsidian": {"prefix": "o:"}, "theme": "light"})
    assert merged["obsidian"]["prefix"] == "o:"
    assert merged["obsidian"]["url_field"] == "source"
    assert merged["theme"] == "light"
    assert config.DEFAULT_CONFIG["obsidian"]["prefix"] == "obs:"


def test_frontmatter():
    text = "---\ntitle: Hello\naliases: [a, b]\n---\nbody"
    assert parse_frontmatter(text) == {"title": "Hello", "aliases": ["a", "b"]}
    assert parse_frontmatter("no frontmatter") == {}
    assert parse_frontmatter("---\n: : bad\n---") == {}


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


@pytest.fixture
def vault(tmp_path):
    folder = tmp_path / "Snippets"
    _write(str(folder / "asyncio.md"),
           "---\ntitle: Python asyncio docs\naliases:\n  - event loop\n  - coroutines\nsource: https://docs.python.org/3/library/asyncio.html\n---\n")
    _write(str(folder / "sub" / "Regex101.md"),
           "---\nAliases: regex tester\nSource: https://regex101.com\n---\n")
    _write(str(folder / "plain.md"), "---\ntitle: Plain note\n---\nno url")
    _write(str(folder / ".obsidian" / "skip.md"), "---\ntitle: hidden\nsource: x\n---")
    return str(folder)


def test_index_search(vault):
    index = BookmarkIndex(vault)
    index.refresh()
    titles = sorted(b.title for b in index.bookmarks)
    assert titles == ["Plain note", "Python asyncio docs", "Regex101"]  # filename fallback, dot-dirs skipped
    (bm, via), = index.search("event")
    assert bm.title == "Python asyncio docs" and via == "event loop"
    (bm, via), = index.search("regex tester")
    assert bm.url == "https://regex101.com"  # case-insensitive field names


def test_index_custom_fields_and_refresh(vault):
    index = BookmarkIndex(vault, title_field="name, title", url_field="link, source")
    index.refresh()
    assert {b.title for b in index.bookmarks} >= {"Python asyncio docs"}
    os.remove(os.path.join(vault, "plain.md"))
    index.refresh()
    assert len(index.bookmarks) == 2


def test_obsidian_command(vault):
    opened = []
    cfg = dict(config.DEFAULT_CONFIG["obsidian"])
    cmd = ObsidianBookmarksCommand(cfg, BookmarkIndex(vault), opened.append)
    cmd.on_open()
    items = cmd.query("loop")
    assert items[0].title == "Python asyncio docs"
    items[0].actions[0].callback()
    assert opened == ["https://docs.python.org/3/library/asyncio.html"]
    plain = cmd.query("plain")[0]
    assert plain.actions[0].label == "Open note in Obsidian"
    cfg["without_url"] = "hide"
    assert cmd.query("plain")[0].title == "No matching bookmarks"


def test_windows_ordering():
    cfg = dict(config.DEFAULT_CONFIG["windows"])
    cmd = WindowsCommand(cfg)
    info = DesktopInfo([Desktop("a", 1, "Main"), Desktop("b", 2, "Research")], "a")
    wins = [
        WindowInfo(1, "Editor - notes.md", process_name="code.exe", desktop_id="a"),
        WindowInfo(2, "Firefox", process_name="firefox.exe", desktop_id="b", on_current_desktop=False),
        WindowInfo(3, "Terminal", process_name="wt.exe", desktop_id="a"),
        WindowInfo(4, "Input", process_name="TextInputHost.exe", desktop_id="a"),
    ]
    cmd.set_snapshot(wins, info, foreground=1)
    items = cmd.query("")
    assert [i.title for i in items] == ["Editor - notes.md", "Terminal", "Firefox"]
    assert items[2].badge == "Research" and items[2].color == cfg["desktop_colors"][1]
    assert cmd.initial_index("", items) == 1
    assert [i.title for i in cmd.query("fire")] == ["Firefox"]
    cfg["show_other_desktops"] = False
    assert "Firefox" not in [i.title for i in cmd.query("")]


def test_registry_resolution():
    web = WebCommand("g:", "Google", "https://g.com/?q={query}", lambda u: None)
    reg = CommandRegistry(WindowsCommand({}), [web])
    assert reg.resolve("G: hello world") == (web, "hello world")
    cmd, rest = reg.resolve("firefox")
    assert cmd is reg.default and rest == "firefox"
    assert web.query("a b")[0].subtitle == "https://g.com/?q=a+b"
    assert [i.actions[0].fill for i in reg.suggestions("g")] == ["g:"]
    help_cmd, _ = reg.resolve("?")
    assert any("Google" in i.title for i in help_cmd.query(""))
