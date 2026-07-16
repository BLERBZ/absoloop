#!/usr/bin/env python3
"""Render the AbsoLoop logo in a terminal with no external dependencies."""

from __future__ import annotations

import argparse
import math
import os
import re
import shutil
import sys
from typing import Iterable

RESET = "\x1b[0m"
BOLD = "\x1b[1m"
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")

# Color positions around the infinity loop. The order follows the ribbon:
# center -> upper right -> lower right -> center -> upper left -> lower left.
LOOP_STOPS: tuple[tuple[float, tuple[int, int, int]], ...] = (
    (0.000, (40, 205, 120)),   # green at the crossing
    (0.125, (210, 245, 20)),   # lime/yellow, upper right
    (0.250, (255, 145, 20)),   # orange, far right
    (0.375, (255, 25, 95)),    # pink/red, lower right
    (0.500, (255, 190, 15)),   # gold at the crossing
    (0.625, (0, 205, 225)),    # cyan, upper left
    (0.750, (0, 105, 255)),    # blue, far left
    (0.875, (210, 0, 165)),    # magenta, lower left
    (1.000, (40, 205, 120)),   # close the loop
)

WORD_STOPS: tuple[tuple[float, tuple[int, int, int]], ...] = (
    (0.00, (0, 155, 255)),
    (0.22, (0, 210, 225)),
    (0.42, (45, 210, 115)),
    (0.56, (245, 220, 20)),
    (0.72, (255, 125, 25)),
    (0.86, (255, 35, 80)),
    (1.00, (220, 0, 160)),
)

# Compact 3x5 pixel font. Each filled pixel is printed as two terminal cells,
# keeping the letters visually square in most monospace fonts.
FONT: dict[str, tuple[str, ...]] = {
    "A": ("010", "101", "111", "101", "101"),
    "b": ("100", "100", "110", "101", "110"),
    "s": ("000", "011", "100", "010", "110"),
    "o": ("000", "010", "101", "101", "010"),
    "L": ("100", "100", "100", "100", "111"),
    "l": ("100", "100", "100", "100", "111"),
    "p": ("000", "110", "101", "110", "100"),
}

WORDMARK = "AbsoLoop"


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _sample_gradient(
    position: float,
    stops: Iterable[tuple[float, tuple[int, int, int]]],
) -> tuple[int, int, int]:
    """Linearly interpolate an RGB color from normalized gradient stops."""
    position = _clamp(position, 0.0, 1.0)
    stop_list = tuple(stops)

    for index in range(len(stop_list) - 1):
        left_pos, left_rgb = stop_list[index]
        right_pos, right_rgb = stop_list[index + 1]
        if left_pos <= position <= right_pos:
            span = right_pos - left_pos
            amount = 0.0 if span == 0 else (position - left_pos) / span
            return tuple(
                round(left + (right - left) * amount)
                for left, right in zip(left_rgb, right_rgb)
            )  # type: ignore[return-value]

    return stop_list[-1][1]


def _ansi(rgb: tuple[int, int, int]) -> str:
    red, green, blue = rgb
    return f"\x1b[38;2;{red};{green};{blue}m"


def _color_enabled(mode: str) -> bool:
    if mode == "always":
        return True
    if mode == "never":
        return False
    return (
        sys.stdout.isatty()
        and os.environ.get("TERM", "") != "dumb"
        and "NO_COLOR" not in os.environ
    )


def _pad_line(line: str, visual_width: int, terminal_width: int, align: str) -> str:
    if align == "left" or terminal_width <= visual_width:
        return line
    padding = max(0, (terminal_width - visual_width) // 2)
    return " " * padding + line


def _paint(
    text: str,
    position: float,
    stops: Iterable[tuple[float, tuple[int, int, int]]],
    color: bool,
) -> str:
    if not color:
        return text
    return f"{_ansi(_sample_gradient(position, stops))}{text}{RESET}"


def _left_trim_block(rows: list[str]) -> list[str]:
    """Trim shared leading spaces so an embed sits flush on the left."""
    if not rows:
        return rows
    leading = min((len(row) - len(row.lstrip(" ")) for row in rows), default=0)
    if leading <= 0:
        return rows
    return [row[leading:] if len(row) >= leading else row for row in rows]


def _render_infinity(
    terminal_width: int,
    requested_width: int | None,
    color: bool,
    ascii_only: bool,
    *,
    align: str = "center",
    height: int | None = None,
) -> list[str]:
    # Two characters are used for every horizontal pixel to correct the usual
    # terminal-cell aspect ratio. The resulting mark is intentionally bold.
    output_width = requested_width or min(72, max(34, terminal_width - 2))
    output_width = max(16, min(output_width, max(16, terminal_width)))
    output_width -= output_width % 2

    pixel_columns = max(8, output_width // 2)
    if height is not None:
        pixel_rows = max(4, height)
    else:
        pixel_rows = max(8, round(pixel_columns * 0.375))
    block = "##" if ascii_only else "██"

    sample_count = 1_200
    curve: list[tuple[float, float, float]] = []
    for index in range(sample_count):
        t = (2.0 * math.pi * index) / sample_count
        x = math.sin(t)
        y = 0.52 * math.sin(2.0 * t)
        curve.append((x, y, index / sample_count))

    # Slightly thicker stroke on short embeds so the ribbon stays readable.
    stroke = 0.12 if pixel_rows < 8 else 0.095
    x_min, x_max = -1.15, 1.15
    y_min, y_max = -0.65, 0.65
    rows: list[str] = []

    for row in range(pixel_rows):
        y = y_max - (row + 0.5) * ((y_max - y_min) / pixel_rows)
        cells: list[str] = []

        for column in range(pixel_columns):
            x = x_min + (column + 0.5) * ((x_max - x_min) / pixel_columns)
            nearest_distance = float("inf")
            nearest_path_position = 0.0

            for point_x, point_y, path_position in curve:
                distance = (x - point_x) ** 2 + (y - point_y) ** 2
                if distance < nearest_distance:
                    nearest_distance = distance
                    nearest_path_position = path_position

            if nearest_distance <= stroke**2:
                cells.append(
                    _paint(block, nearest_path_position, LOOP_STOPS, color)
                )
            else:
                cells.append("  ")

        # Keep a fixed left edge so every row stays aligned; trim only the right.
        line = "".join(cells).rstrip()
        rows.append(_pad_line(line, output_width, terminal_width, align))

    if align == "left":
        return _left_trim_block(rows)
    return rows


def _render_wordmark(
    terminal_width: int,
    color: bool,
    ascii_only: bool,
    *,
    align: str = "center",
    white: bool = False,
    compact_glyphs: bool = False,
) -> list[str]:
    text = WORDMARK
    # compact_glyphs: one cell per pixel (~31 cols) for side-column embeds;
    # full glyphs use two cells so letters stay square in a wide banner.
    if compact_glyphs and not ascii_only:
        pixel, empty, gap, step = "█", " ", " ", 1
    else:
        pixel = "##" if ascii_only else "██"
        empty, gap, step = "  ", "  ", 2
    pixel_width = len(next(iter(FONT.values()))[0])
    visual_width = len(text) * (pixel_width * step) + (len(text) - 1) * len(gap)
    rows: list[str] = []

    for row_index in range(5):
        output: list[str] = []
        visual_column = 0

        for letter_index, letter in enumerate(text):
            pattern = FONT[letter][row_index]
            for bit in pattern:
                position = visual_column / max(1, visual_width - 1)
                if bit == "1":
                    if color and white:
                        output.append(f"{BOLD}\x1b[97m{pixel}{RESET}")
                    else:
                        output.append(_paint(pixel, position, WORD_STOPS, color))
                else:
                    output.append(empty)
                visual_column += step

            if letter_index != len(text) - 1:
                output.append(gap)
                visual_column += len(gap)

        line = "".join(output).rstrip()
        rows.append(_pad_line(line, visual_width, terminal_width, align))

    if align == "left":
        return _left_trim_block(rows)
    return rows


def _render_compact(
    terminal_width: int,
    color: bool,
    ascii_only: bool,
    *,
    align: str = "center",
    white_label: bool = False,
    mark: bool = True,
) -> str:
    infinity = "<>" if ascii_only else "∞"
    mark_width = (2 if ascii_only else 1) if mark else 0
    label = WORDMARK

    if color and mark:
        mark_text = f"{BOLD}{_ansi((0, 190, 240))}{infinity}{RESET}"
    elif mark:
        mark_text = infinity
    else:
        mark_text = ""

    if color and not white_label:
        colored_label = "".join(
            f"{BOLD}{_ansi(_sample_gradient(i / (len(label) - 1), WORD_STOPS))}"
            f"{character}{RESET}"
            for i, character in enumerate(label)
        )
    elif color and white_label:
        # Bright white wordmark; infinity mark keeps its own color above/beside.
        colored_label = f"{BOLD}\x1b[97m{label}{RESET}"
    else:
        colored_label = label

    if mark_text:
        body = f"{mark_text} {colored_label}"
        visual_width = mark_width + 1 + len(label)
    else:
        body = colored_label
        visual_width = len(label)
    return _pad_line(body, visual_width, terminal_width, align)


def build_logo_lines(
    *,
    width: int | None = None,
    height: int | None = None,
    compact: bool = False,
    color_mode: str = "auto",
    ascii_only: bool = False,
    wordmark: bool = True,
    terminal_width: int | None = None,
    align: str = "center",
    white_label: bool = False,
    compact_mark: bool = True,
    compact_glyphs: bool = False,
) -> list[str]:
    """Return logo rows as a list (useful for side-by-side CLI layouts)."""
    terminal_width = terminal_width or shutil.get_terminal_size((80, 24)).columns
    color = _color_enabled(color_mode)
    align = "left" if align == "left" else "center"

    # The full pixel wordmark needs roughly 64 columns. Fall back gracefully in
    # a narrow terminal instead of wrapping the logo — unless height is set for
    # an explicit embed (watch dashboard), which opts into the mark.
    if compact or (height is None and terminal_width < 66 and width is None):
        return [_render_compact(
            terminal_width, color, ascii_only, align=align,
            white_label=white_label, mark=compact_mark,
        )]

    mark_height = height
    if height is not None and wordmark:
        # Reserve one blank row + five wordmark rows when the embed is tall
        # enough; otherwise drop the wordmark so the mark fills the section.
        # white_label embeds keep the wordmark and let the column grow.
        if height >= 10:
            mark_height = max(4, height - 6)
        elif not white_label:
            wordmark = False

    lines = _render_infinity(
        terminal_width,
        width,
        color,
        ascii_only,
        align=align,
        height=mark_height,
    )
    if wordmark:
        lines.append("")
        lines.extend(
            _render_wordmark(
                terminal_width, color, ascii_only, align=align,
                white=white_label, compact_glyphs=compact_glyphs,
            )
        )
    if align == "left":
        return _left_trim_block(lines)
    return lines


def build_logo(
    *,
    width: int | None = None,
    height: int | None = None,
    compact: bool = False,
    color_mode: str = "auto",
    ascii_only: bool = False,
    wordmark: bool = True,
    terminal_width: int | None = None,
    align: str = "center",
    white_label: bool = False,
    compact_mark: bool = True,
    compact_glyphs: bool = False,
) -> str:
    """Return the complete logo as an ANSI-capable string."""
    return "\n".join(
        build_logo_lines(
            width=width,
            height=height,
            compact=compact,
            color_mode=color_mode,
            ascii_only=ascii_only,
            wordmark=wordmark,
            terminal_width=terminal_width,
            align=align,
            white_label=white_label,
            compact_mark=compact_mark,
            compact_glyphs=compact_glyphs,
        )
    )


def print_logo(**options: object) -> None:
    """Print the logo; useful when importing this file from another CLI."""
    print(build_logo(**options))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Print the AbsoLoop terminal logo.",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="print a one-line version",
    )
    parser.add_argument(
        "--width",
        type=int,
        default=None,
        help="full logo width in terminal columns (default: auto)",
    )
    parser.add_argument(
        "--height",
        type=int,
        default=None,
        help="infinity-mark height in terminal rows (default: auto)",
    )
    parser.add_argument(
        "--color",
        choices=("auto", "always", "never"),
        default="auto",
        help="ANSI color policy (default: auto)",
    )
    parser.add_argument(
        "--ascii",
        action="store_true",
        dest="ascii_only",
        help="use ASCII characters only",
    )
    parser.add_argument(
        "--mark-only",
        action="store_true",
        help="omit the AbsoLoop wordmark",
    )
    parser.add_argument(
        "--left",
        action="store_true",
        help="left-align instead of centering",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    print(
        build_logo(
            width=args.width,
            height=args.height,
            compact=args.compact,
            color_mode=args.color,
            ascii_only=args.ascii_only,
            wordmark=not args.mark_only,
            align="left" if args.left else "center",
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
