from vibe_cli.config import Config


def test_load_default_config(tmp_path):
    # Test loading when file doesn't exist (should return defaults)
    config = Config.load(tmp_path / "nonexistent.toml")
    assert config.ui.theme == "dark"
    assert config.default_provider == "local"

def test_load_custom_config(tmp_path):
    config_content = """
    default_provider = "openai"
    
    [ui]
    theme = "light"
    
    [providers.openai]
    api_key = "sk-test"
    model = "gpt-4"
    """

    config_file = tmp_path / "config.toml"
    config_file.write_text(config_content)

    config = Config.load(config_file)
    assert config.default_provider == "openai"
    assert config.ui.theme == "light"
    assert config.providers["openai"].api_key == "sk-test"
