import json
import shutil
from datetime import datetime
from pathlib import Path

from vibe_cli.models.messages import Conversation


class CheckpointManager:
    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.checkpoint_dir = workspace / ".vibe" / "checkpoints"
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

    def create(self, conversation: Conversation, description: str = "") -> str:
        """Create a checkpoint of current state"""
        checkpoint_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        checkpoint_path = self.checkpoint_dir / checkpoint_id
        checkpoint_path.mkdir()

        # Save conversation
        with open(checkpoint_path / "conversation.json", "w") as f:
            f.write(conversation.model_dump_json())

        # Save file snapshots (simple version: copy all non-ignored files)
        files_dir = checkpoint_path / "files"
        files_dir.mkdir()

        for file_path in self._get_tracked_files():
            try:
                rel_path = file_path.relative_to(self.workspace)
                dest = files_dir / rel_path
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(file_path, dest)
            except Exception:
                continue # Skip files we can't copy

        # Metadata
        with open(checkpoint_path / "meta.json", "w") as f:
            json.dump({
                "id": checkpoint_id,
                "description": description,
                "timestamp": datetime.now().isoformat(),
            }, f)

        return checkpoint_id

    def _get_tracked_files(self) -> list[Path]:
        """Simple file listing, skipping .git and .vibe"""
        files = []
        for path in self.workspace.rglob("*"):
            if path.is_file():
                rel = str(path.relative_to(self.workspace))
                if ".vibe" in rel or ".git" in rel or ".venv" in rel or "__pycache__" in rel:
                    continue
                files.append(path)
        return files
