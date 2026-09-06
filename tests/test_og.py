from importlib import resources

from statusboard import render as render_module
from statusboard.config import Config, load_config
from statusboard.og import HEIGHT, WIDTH, og_svg
from statusboard.render import GROUPS, PROVIDER_ORDER, build_context, render

from conftest import utc

NOW = utc(2026, 9, 6, 2, 0, 0)


def test_og_svg_lists_every_provider_under_its_group():
    svg = og_svg(GROUPS)
    assert svg.startswith("<svg") and f'width="{WIDTH}" height="{HEIGHT}"' in svg
    for label, _pairs in GROUPS:
        assert label.upper() in svg
    for _name, label in PROVIDER_ORDER:
        assert f">{label}</text>" in svg
    assert f"{len(PROVIDER_ORDER)} providers" in svg


def test_og_svg_skips_empty_groups_and_escapes():
    svg = og_svg([("A & B", [("x", "Tom & Jerry <3")]), ("Ghost", [])])
    assert "A &amp; B" in svg
    assert "Tom &amp; Jerry &lt;3" in svg
    assert "GHOST" not in svg


def test_committed_png_exists_and_is_a_png():
    png = resources.files("statusboard").joinpath("static/og.png")
    assert png.is_file()
    assert png.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_site_url_config(tmp_path):
    path = tmp_path / "statusboard.toml"
    path.write_text('[site]\nurl = "https://status.example.com/"\n')
    assert load_config(str(path)).site_url == "https://status.example.com"
    path.write_text("[regions]\n")
    assert load_config(str(path)).site_url is None


def test_bad_site_url_raises(tmp_path):
    import pytest

    from statusboard.config import ConfigError

    path = tmp_path / "statusboard.toml"
    path.write_text('[site]\nurl = "status.example.com"\n')
    with pytest.raises(ConfigError, match="absolute http"):
        load_config(str(path))


def test_render_writes_og_png_and_tags_only_with_site_url(conn, tmp_path, monkeypatch):
    html = render(conn, tmp_path / "a", now=NOW).read_text()
    assert "og:image" not in html
    assert (tmp_path / "a" / "og.png").read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"

    monkeypatch.setattr(
        render_module,
        "load_config",
        lambda: Config(frozenset(), "https://status.example.com"),
    )
    html = render(conn, tmp_path / "b", now=NOW).read_text()
    assert (
        '<meta property="og:image" content="https://status.example.com/og.png">' in html
    )
    assert '<meta property="og:url" content="https://status.example.com/">' in html
    assert '<meta name="twitter:card" content="summary_large_image">' in html
    assert build_context(conn, NOW)["site_url"] == "https://status.example.com"
