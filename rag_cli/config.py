from pathlib import Path

import platformdirs
import tomli
from pydantic import BaseModel, Field


class UIConfig(BaseModel):
    theme: str = "light"
    show_tokens: bool = True
    sidebar_visible: bool = True
    sidebar_width: int = 26


class Config(BaseModel):
    ui: UIConfig = Field(default_factory=UIConfig)
    rag_backend_url: str = "http://localhost:8900"

    @classmethod
    def load(cls, path: Path | None = None) -> "Config":
        if path is None:
            config_dir = Path(platformdirs.user_config_dir("rag-cli"))
            path = config_dir / "config.toml"

        if not path.exists():
            return cls()

        with open(path, "rb") as f:
            data = tomli.load(f)

        return cls.model_validate(data)
