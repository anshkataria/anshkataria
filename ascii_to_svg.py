"""
ascii_to_svg.py

Converts a plain-text ASCII portrait (portrait.txt) into a series of
SVG <tspan> elements (portrait_tspan.txt) that can be pasted inside a
<text> block in dark.svg / light.svg.

Usage:
    python ascii_to_svg.py

Config (edit these to match your terminal layout):
    INPUT_FILE   - path to the ASCII art file
    OUTPUT_FILE  - path to write the generated <tspan> lines
    START_X      - x-position (left edge) for every line of the portrait
    START_Y      - y-position of the first line
    LINE_HEIGHT  - vertical spacing between lines
"""

import html

INPUT_FILE = "portrait.txt"
OUTPUT_FILE = "portrait_tspan.txt"

START_X = 50
START_Y = 145
LINE_HEIGHT = 10


def escape_ascii_line(line: str) -> str:
    """Escape XML-special characters so the ASCII art renders safely inside SVG."""
    # Preserve leading spaces (SVG collapses them by default unless xml:space="preserve"
    # is set on the parent <text>/<tspan>, which the templates in this repo already set).
    return html.escape(line, quote=False)


def convert(input_path: str, output_path: str) -> int:
    with open(input_path, "r", encoding="utf-8") as f:
        lines = f.read().splitlines()

    if len(lines) > 60:
        print(
            f"Warning: {input_path} has {len(lines)} lines. "
            "60 or fewer is recommended for a clean, high-quality portrait."
        )

    tspans = []
    for i, raw_line in enumerate(lines):
        y = START_Y + i * LINE_HEIGHT
        escaped = escape_ascii_line(raw_line)
        tspans.append(f'<tspan x="{START_X}" y="{y:.2f}" xml:space="preserve">{escaped}</tspan>')

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(tspans) + "\n")

    return len(lines)


if __name__ == "__main__":
    count = convert(INPUT_FILE, OUTPUT_FILE)
    print(f"Converted {count} lines from '{INPUT_FILE}' into '{OUTPUT_FILE}'.")
