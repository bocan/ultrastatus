"""The Ultra Status favicon, drawn in code so the page needs no image files.

Design: a dark rounded square, a large green dot for "ok", and a small red
dot at the top right for "something is up". The same shapes are emitted as
SVG (crisp, most browsers) and as a 32 px PNG (Safari, and the .ico file).
"""

import base64
import struct
import zlib

BG = (0x0D, 0x11, 0x17)
GREEN = (0x3F, 0xB9, 0x50)
RED = (0xF8, 0x51, 0x49)


def svg_icon() -> str:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">'
        '<rect width="32" height="32" rx="7" fill="#0d1117"/>'
        '<circle cx="15" cy="17.5" r="9" fill="#3fb950"/>'
        '<circle cx="24.5" cy="8" r="5.5" fill="#0d1117"/>'
        '<circle cx="24.5" cy="8" r="4.2" fill="#f85149"/>'
        "</svg>"
    )


def _coverage_circle(x: float, y: float, cx: float, cy: float, r: float) -> float:
    """Anti-aliased coverage of pixel centre (x, y) by a circle, 0 to 1."""
    d = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5
    return max(0.0, min(1.0, r - d + 0.5))


def _coverage_rounded_square(x: float, y: float, size: float, radius: float) -> float:
    """Coverage by a rounded square filling the whole canvas."""
    qx = max(radius - x, x - (size - radius), 0.0)
    qy = max(radius - y, y - (size - radius), 0.0)
    d = (qx**2 + qy**2) ** 0.5
    return max(0.0, min(1.0, radius - d + 0.5))


def _blend(under: tuple, over: tuple, alpha: float) -> tuple:
    return tuple(round(u + (o - u) * alpha) for u, o in zip(under, over))


def png_icon(size: int = 32) -> bytes:
    scale = size / 32.0
    rows = []
    for py in range(size):
        row = bytearray([0])  # filter type: none
        for px in range(size):
            x, y = px + 0.5, py + 0.5
            bg_alpha = _coverage_rounded_square(x, y, size, 7 * scale)
            colour = BG
            colour = _blend(
                colour,
                GREEN,
                _coverage_circle(x, y, 15 * scale, 17.5 * scale, 9 * scale),
            )
            colour = _blend(
                colour, BG, _coverage_circle(x, y, 24.5 * scale, 8 * scale, 5.5 * scale)
            )
            colour = _blend(
                colour,
                RED,
                _coverage_circle(x, y, 24.5 * scale, 8 * scale, 4.2 * scale),
            )
            row += bytes([*colour, round(255 * bg_alpha)])
        rows.append(bytes(row))
    raw = b"".join(rows)

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return (
            struct.pack(">I", len(data))
            + body
            + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)  # 8-bit RGBA
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


def ico_icon(size: int = 32) -> bytes:
    """An .ico container holding one PNG image. Every current browser reads this."""
    png = png_icon(size)
    header = struct.pack("<HHH", 0, 1, 1)
    entry = struct.pack("<BBBBHHII", size, size, 0, 0, 1, 32, len(png), 6 + 16)
    return header + entry + png


def svg_data_uri() -> str:
    svg = (
        svg_icon()
        .replace('"', "'")
        .replace("#", "%23")
        .replace("<", "%3C")
        .replace(">", "%3E")
    )
    return "data:image/svg+xml," + svg


def png_data_uri(size: int = 32) -> str:
    return "data:image/png;base64," + base64.b64encode(png_icon(size)).decode("ascii")
