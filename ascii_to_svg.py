"""
ascii_to_svg.py

Converts a plain-text ASCII portrait (portrait.txt) into a series of
SVG <tspan> elements (portrait_tspan.txt) that can be pasted inside the
<text class="portrait"> block in dark.template.svg / light.template.svg.

Unlike a fixed font-size/line-height, this script AUTO-FITS your ASCII art
to the screen box every time — it measures how many lines you have and how
wide the longest line is, then computes a font-size and line-height that
guarantee the whole portrait fits inside the box, no matter the source
image's width/height settings.

Usage:
    python ascii_to_svg.py

The screen box dimensions below must match the inner screen <rect> in the
SVG templates (currently x=40 y=140 width=348 height=354). If you resize
that rect in the template, update these to match.
"""

import html

INPUT_FILE = "portrait.txt"
OUTPUT_FILE = "portrait_tspan.txt"

# Must match the inner screen rect in templates/*.template.svg
BOX_X = 40
BOX_Y = 140
BOX_WIDTH = 348
BOX_HEIGHT = 354
PADDING = 8

# Tuning constants for the monospace font used (Consolas / Courier New)
CHAR_WIDTH_RATIO = 0.6   # approx glyph width as a fraction of font-size
LINE_HEIGHT_RATIO = 1.15  # approx line spacing as a multiple of font-size
MAX_FONT_SIZE = 11        # don't blow up the art if there are very few/short lines


def escape_ascii_line(line: str) -> str:
    """Escape XML-special characters so the ASCII art renders safely inside SVG."""
    return html.escape(line, quote=False)


def convert(input_path: str, output_path: str) -> int:
    with open(input_path, "r", encoding="utf-8") as f:
        lines = f.read().splitlines()

    if not lines:
        raise ValueError(f"{input_path} is empty.")

    num_lines = len(lines)
    max_chars = max(len(line) for line in lines) or 1

    available_width = BOX_WIDTH - 2 * PADDING
    available_height = BOX_HEIGHT - 2 * PADDING

    font_size_by_width = available_width / (max_chars * CHAR_WIDTH_RATIO)
    font_size_by_height = available_height / (num_lines * LINE_HEIGHT_RATIO)
    font_size = min(font_size_by_width, font_size_by_height, MAX_FONT_SIZE)
    font_size = round(font_size, 2)

    line_height = round(font_size * LINE_HEIGHT_RATIO, 2)
    start_x = BOX_X + PADDING
    start_y = BOX_Y + PADDING + font_size

    tspans = []
    for i, raw_line in enumerate(lines):
        y = start_y + i * line_height
        escaped = escape_ascii_line(raw_line)
        tspans.append(
            f'<tspan x="{start_x}" y="{y:.2f}" font-size="{font_size}" '
            f'xml:space="preserve">{escaped}</tspan>'
        )

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(tspans) + "\n")

    print(f"Lines: {num_lines}, longest line: {max_chars} chars")
    print(f"Computed font-size: {font_size}px, line-height: {line_height}px")
    if font_size < 3:
        print(
            "Warning: computed font-size is very small — your ASCII art may be "
            "too large (too many lines and/or too wide) to read clearly at this "
            "box size. Consider regenerating it with a smaller --width, or fewer lines."
        )

    return num_lines


if __name__ == "__main__":
    count = convert(INPUT_FILE, OUTPUT_FILE)
    print(f"Converted {count} lines from '{INPUT_FILE}' into '{OUTPUT_FILE}'.")
