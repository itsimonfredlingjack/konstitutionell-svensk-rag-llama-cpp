from rag_cli.config import Config


def test_load_default_config(tmp_path):
    config = Config.load(tmp_path / "nonexistent.toml")
    assert config.ui.theme == "light"
    assert config.ui.sidebar_visible is True
    assert config.ui.sidebar_width == 26
    assert config.rag_backend_url == "http://localhost:8900"


def test_load_custom_config(tmp_path):
    config_content = """
rag_backend_url = "http://myserver:9000"

[ui]
theme = "dark"
"""

    config_file = tmp_path / "config.toml"
    config_file.write_text(config_content)

    config = Config.load(config_file)
    assert config.rag_backend_url == "http://myserver:9000"
    assert config.ui.theme == "dark"
