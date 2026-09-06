from pathlib import Path

import pytest

from statusboard.config import Config, ConfigError, load_config

EXAMPLE = Path(__file__).parent.parent / "statusboard.example.toml"


def _write(tmp_path, text):
    path = tmp_path / "statusboard.toml"
    path.write_text(text)
    return str(path)


def test_missing_file_is_inactive(tmp_path):
    config = load_config(str(tmp_path / "nope.toml"))
    assert config == Config(frozenset())
    assert config.active is False


def test_example_file_loads_and_is_active():
    config = load_config(str(EXAMPLE))
    assert config.active is True
    assert config.my_regions == frozenset(
        {
            ("aws", "eu-west-2"),
            ("aws", "us-east-1"),
            ("gcp", "europe-west2"),
            ("azure", "uksouth"),
            ("azure", "westeurope"),
        }
    )


def test_empty_regions_table_is_inactive(tmp_path):
    assert load_config(_write(tmp_path, "[regions]\n")).active is False
    assert load_config(_write(tmp_path, "")).active is False


def test_unknown_cloud_raises(tmp_path):
    with pytest.raises(ConfigError, match="unknown cloud 'oracle'"):
        load_config(_write(tmp_path, '[regions]\noracle = ["us-ashburn-1"]\n'))


def test_unknown_region_suggests_near_match(tmp_path):
    with pytest.raises(ConfigError) as info:
        load_config(_write(tmp_path, '[regions]\naws = ["eu-west2"]\n'))
    message = str(info.value)
    assert "unknown aws region 'eu-west2'" in message
    assert "eu-west-2" in message


def test_unknown_region_prefix_suggestions(tmp_path):
    with pytest.raises(ConfigError) as info:
        load_config(_write(tmp_path, '[regions]\ngcp = ["europe-west99"]\n'))
    assert "europe-west1" in str(info.value)


def test_string_instead_of_list_raises(tmp_path):
    with pytest.raises(ConfigError, match="must be a list of strings"):
        load_config(_write(tmp_path, '[regions]\naws = "eu-west-2"\n'))


def test_invalid_toml_raises(tmp_path):
    with pytest.raises(ConfigError, match="not valid TOML"):
        load_config(_write(tmp_path, "[regions\n"))


def test_env_var_is_honoured(tmp_path, monkeypatch):
    path = _write(tmp_path, '[regions]\nazure = ["uksouth"]\n')
    monkeypatch.setenv("STATUSBOARD_CONFIG", path)
    assert load_config().my_regions == frozenset({("azure", "uksouth")})
