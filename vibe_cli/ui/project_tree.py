from __future__ import annotations

import asyncio
from pathlib import Path

from rich.text import Text
from textual.message import Message
from textual.widgets import Static, Tree

from vibe_cli.ui.theme import COLORS


class FilePinMessage(Message):
    def __init__(self, path: Path) -> None:
        super().__init__()
        self.path = path


class ProjectTree(Tree[Path]):
    def __init__(self, root_path: Path, **kwargs) -> None:
        super().__init__(Text(root_path.name, style=COLORS["primary"]), root_path, **kwargs)
        self.root_path = root_path
        self._git_status: dict[Path, str] = {}
        self._ignored = {".git", "__pycache__", ".mypy_cache", ".pytest_cache", "venv", "node_modules"}
        self.show_root = True

    def on_mount(self) -> None:
        self._schedule_refresh()

    def _schedule_refresh(self) -> None:
        self.run_worker(self.refresh_tree(), group="project-tree")

    async def refresh_tree(self) -> None:
        self._git_status = await _load_git_status(self.root_path)
        self.root.data = self.root_path
        self.root.label = self._label_for(self.root_path)
        self.root.remove_children()
        tree_data = await asyncio.to_thread(self._collect_tree, self.root_path)
        self._populate_node(self.root, tree_data)
        self.root.expand()
        self.refresh()

    def _populate_node(self, node, entries: list[tuple[Path, list]]) -> None:
        for entry, children in entries:
            if entry.is_dir():
                child = node.add(self._label_for(entry), entry)
                self._populate_node(child, children)
            else:
                node.add_leaf(self._label_for(entry), entry)

    def _collect_tree(self, path: Path) -> list[tuple[Path, list]]:
        entries = sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        collected: list[tuple[Path, list]] = []
        for entry in entries:
            if entry.name in self._ignored:
                continue
            if entry.is_dir():
                collected.append((entry, self._collect_tree(entry)))
            else:
                collected.append((entry, []))
        return collected

    def _label_for(self, path: Path) -> Text:
        rel = path.relative_to(self.root_path)
        status = self._git_status.get(rel)
        label = Text(path.name)
        if status:
            label.stylize(_status_color(status))
        return label

    async def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        path = event.node.data
        if not isinstance(path, Path) or path.is_dir():
            return
        self.post_message(FilePinMessage(path))


class PinnedFilesPanel(Static):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._pins: list[Path] = []

    def set_pins(self, pins: list[Path]) -> None:
        self._pins = pins
        self.refresh()

    def render(self) -> Text:
        if not self._pins:
            return Text("  Pin files from tree", style=COLORS["text_dim"])

        text = Text()
        for idx, path in enumerate(self._pins):
            if idx > 0:
                text.append("\n")
            text.append(f" - {path}", style=COLORS["text"])
        return text


def _status_color(status: str) -> str:
    if status == "A":
        return COLORS["success"]
    if status == "M":
        return COLORS["warning"]
    if status == "D":
        return COLORS["error"]
    return COLORS["tertiary"]


async def _load_git_status(root: Path) -> dict[Path, str]:
    try:
        proc = await asyncio.create_subprocess_exec(
            "git",
            "status",
            "--porcelain",
            cwd=root,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        if proc.returncode != 0:
            return {}
    except Exception:
        return {}

    status_map: dict[Path, str] = {}
    for line in stdout.decode().splitlines():
        if not line:
            continue
        status = line[:2].strip()
        file_path = line[3:]
        if status:
            status_map[Path(file_path)] = status[0]
    return status_map
