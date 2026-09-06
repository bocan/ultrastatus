import struct
import zlib

from statusboard import icon
from statusboard.render import render

from conftest import utc


def _png_size(png: bytes):
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    assert png[12:16] == b"IHDR"
    width, height, depth, colour = struct.unpack(">IIBB", png[16:26])
    return width, height, depth, colour


def test_png_is_valid_32px_rgba():
    png = icon.png_icon()
    assert _png_size(png) == (32, 32, 8, 6)
    # The IDAT payload inflates to 32 rows of (1 filter byte + 32 * 4 bytes).
    idat_len = struct.unpack(">I", png[33:37])[0]
    assert png[37:41] == b"IDAT"
    raw = zlib.decompress(png[41:41 + idat_len])
    assert len(raw) == 32 * (1 + 32 * 4)
    # Corners are transparent, the centre is green, the top-right dot is red.
    def pixel(x, y):
        start = y * (1 + 32 * 4) + 1 + x * 4
        return tuple(raw[start:start + 4])
    assert pixel(0, 0)[3] == 0
    assert pixel(15, 17)[:3] == icon.GREEN and pixel(15, 17)[3] == 255
    assert pixel(24, 8)[:3] == icon.RED


def test_ico_wraps_the_png():
    ico = icon.ico_icon()
    reserved, kind, count = struct.unpack("<HHH", ico[:6])
    assert (reserved, kind, count) == (0, 1, 1)
    width, height, _, _, planes, bits, size, offset = struct.unpack("<BBBBHHII", ico[6:22])
    assert (width, height, planes, bits, offset) == (32, 32, 1, 32, 22)
    assert ico[offset:offset + size] == icon.png_icon()


def test_data_uris_and_svg():
    assert icon.svg_data_uri().startswith("data:image/svg+xml,%3Csvg")
    assert '"' not in icon.svg_data_uri()
    assert icon.png_data_uri().startswith("data:image/png;base64,iVBORw0KGgo")
    assert icon.svg_icon().startswith("<svg") and "#3fb950" in icon.svg_icon()


def test_render_links_icons_and_writes_favicon_ico(conn, tmp_path):
    target = render(conn, tmp_path / "site", now=utc(2026, 9, 6, 1, 0))
    html = target.read_text()
    assert '<link rel="icon" type="image/svg+xml" href="data:image/svg+xml,' in html
    assert '<link rel="icon" type="image/png" sizes="32x32" href="data:image/png;base64,' in html
    ico = (tmp_path / "site" / "favicon.ico").read_bytes()
    assert ico[:4] == b"\x00\x00\x01\x00"
