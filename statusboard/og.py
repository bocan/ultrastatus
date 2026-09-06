"""The Open Graph board image: a 1200 by 630 SVG listing every provider by group.

Crawlers want a real PNG at an absolute URL, so `make og-image` renders this
SVG with headless Chrome once and commits statusboard/static/og.png. The SVG is
built from render.GROUPS, so re-run that target after adding a provider.
"""

import html

WIDTH = 1200
HEIGHT = 630
MARGIN = 64

BG = "#0d1117"
INK = "#e6edf3"
INK_2 = "#8b949e"
GREEN = "#3fb950"
RED = "#f85149"
BORDER = "#30363d"

FONT = "system-ui, -apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"
TAGLINE = (
    "Live status of the clouds and services your work runs on, on one page and one map."
)


def _icon(x: float, y: float, size: float) -> str:
    s = size / 32.0
    return (
        f'<g transform="translate({x} {y}) scale({s})">'
        f'<rect width="32" height="32" rx="7" fill="#161b22" stroke="{BORDER}" stroke-width="1"/>'
        f'<circle cx="15" cy="17.5" r="9" fill="{GREEN}"/>'
        f'<circle cx="24.5" cy="8" r="5.5" fill="#161b22"/>'
        f'<circle cx="24.5" cy="8" r="4.2" fill="{RED}"/>'
        "</g>"
    )


def og_svg(groups: list[tuple[str, list[tuple[str, str]]]]) -> str:
    """groups is render.GROUPS: [(group label, [(provider name, label), ...]), ...]."""
    e = html.escape
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}">',
        f'<rect width="{WIDTH}" height="{HEIGHT}" fill="{BG}"/>',
        _icon(MARGIN, 56, 88),
        f'<text x="{MARGIN + 112}" y="112" font-family="{FONT}" font-size="64" font-weight="700" fill="{INK}">Ultra Status</text>',
        f'<text x="{MARGIN}" y="192" font-family="{FONT}" font-size="26" fill="{INK_2}">{e(TAGLINE)}</text>',
        f'<line x1="{MARGIN}" y1="224" x2="{WIDTH - MARGIN}" y2="224" stroke="{BORDER}" stroke-width="1"/>',
    ]

    shown = [(label, pairs) for label, pairs in groups if pairs]

    # Column widths follow the longest text in each column, heading or name,
    # so "DEVELOPER TOOLING" does not run into its neighbour. Widths are
    # estimated from character counts and then scaled to fill the row.
    def natural_width(label: str, pairs: list) -> float:
        heading = len(label) * 12.5
        names = (
            max((len(provider_label) for _, provider_label in pairs), default=0) * 14
            + 26
        )
        return max(heading, names) + 36

    widths = [natural_width(label, pairs) for label, pairs in shown]
    scale = (WIDTH - 2 * MARGIN) / sum(widths) if widths else 1.0
    widths = [w * scale for w in widths]
    top = 272
    x = float(MARGIN)
    for index, (label, pairs) in enumerate(shown):
        if index:
            x += widths[index - 1]
        parts.append(
            f'<text x="{x:.0f}" y="{top}" font-family="{FONT}" font-size="18" font-weight="600" '
            f'letter-spacing="1.5" fill="{INK_2}">{e(label.upper())}</text>'
        )
        for row, (_name, provider_label) in enumerate(pairs):
            y = top + 44 + row * 40
            parts.append(
                f'<circle cx="{x + 8:.0f}" cy="{y - 8}" r="6" fill="{GREEN}"/>'
            )
            parts.append(
                f'<text x="{x + 26:.0f}" y="{y}" font-family="{FONT}" font-size="26" fill="{INK}">{e(provider_label)}</text>'
            )

    total = sum(len(pairs) for _, pairs in shown)
    parts.append(
        f'<text x="{MARGIN}" y="{HEIGHT - 40}" font-family="{FONT}" font-size="20" fill="{INK_2}">'
        f"{total} providers, polled every two minutes, no accounts or API keys.</text>"
    )
    parts.append("</svg>")
    return "".join(parts)
