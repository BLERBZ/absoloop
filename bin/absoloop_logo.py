#!/usr/bin/env python3
"""Render the Absoloop logo in a terminal with no external dependencies."""

from __future__ import annotations

import argparse
import math
import os
import shutil
import sys
from typing import Iterable

RESET = "\x1b[0m"
BOLD = "\x1b[1m"

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
    "l": ("110", "010", "010", "010", "111"),
    "p": ("000", "110", "101", "110", "100"),
}


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


def _center(line: str, visual_width: int, terminal_width: int) -> str:
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


def _render_infinity(
    terminal_width: int,
    requested_width: int | None,
    color: bool,
    ascii_only: bool,
) -> list[str]:
    # Two characters are used for every horizontal pixel to correct the usual
    # terminal-cell aspect ratio. The resulting mark is intentionally bold.
    output_width = requested_width or min(72, max(34, terminal_width - 2))
    output_width = max(30, min(output_width, max(30, terminal_width)))
    output_width -= output_width % 2

    pixel_columns = output_width // 2
    pixel_rows = max(8, round(pixel_columns * 0.375))
    block = "##" if ascii_only else "██"

    sample_count = 1_200
    curve: list[tuple[float, float, float]] = []
    for index in range(sample_count):
        t = (2.0 * math.pi * index) / sample_count
        x = math.sin(t)
        y = 0.52 * math.sin(2.0 * t)
        curve.append((x, y, index / sample_count))

    stroke = 0.095
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
        rows.append(_center(line, output_width, terminal_width))

    return rows


def _render_wordmark(
    terminal_width: int,
    color: bool,
    ascii_only: bool,
) -> list[str]:
    text = "Absoloop"
    pixel = "##" if ascii_only else "██"
    gap = "  "
    pixel_width = len(next(iter(FONT.values()))[0])
    visual_width = len(text) * (pixel_width * 2) + (len(text) - 1) * len(gap)
    rows: list[str] = []

    for row_index in range(5):
        output: list[str] = []
        visual_column = 0

        for letter_index, letter in enumerate(text):
            pattern = FONT[letter][row_index]
            for bit in pattern:
                position = visual_column / max(1, visual_width - 1)
                if bit == "1":
                    output.append(_paint(pixel, position, WORD_STOPS, color))
                else:
                    output.append("  ")
                visual_column += 2

            if letter_index != len(text) - 1:
                output.append(gap)
                visual_column += len(gap)

        line = "".join(output).rstrip()
        rows.append(_center(line, visual_width, terminal_width))

    return rows


def _render_compact(terminal_width: int, color: bool, ascii_only: bool) -> str:
    mark = "<>" if ascii_only else "∞"
    mark_width = 2 if ascii_only else 1
    label = "Absoloop"

    if color:
        mark_text = f"{BOLD}{_ansi((0, 190, 240))}{mark}{RESET}"
        colored_label = "".join(
            f"{BOLD}{_ansi(_sample_gradient(i / (len(label) - 1), WORD_STOPS))}"
            f"{character}{RESET}"
            for i, character in enumerate(label)
        )
    else:
        mark_text = mark
        colored_label = label

    visual_width = mark_width + 1 + len(label)
    return _center(f"{mark_text} {colored_label}", visual_width, terminal_width)


def build_logo(
    *,
    width: int | None = None,
    compact: bool = False,
    color_mode: str = "auto",
    ascii_only: bool = False,
    wordmark: bool = True,
    terminal_width: int | None = None,
) -> str:
    """Return the complete logo as an ANSI-capable string."""
    terminal_width = terminal_width or shutil.get_terminal_size((80, 24)).columns
    color = _color_enabled(color_mode)

    # The full pixel wordmark needs roughly 64 columns. Fall back gracefully in
    # a narrow terminal instead of wrapping the logo.
    if compact or terminal_width < 66:
        return _render_compact(terminal_width, color, ascii_only)

    lines = _render_infinity(terminal_width, width, color, ascii_only)
    if wordmark:
        lines.append("")
        lines.extend(_render_wordmark(terminal_width, color, ascii_only))
    return "\n".join(lines)


def print_logo(**options: object) -> None:
    """Print the logo; useful when importing this file from another CLI."""
    print(build_logo(**options))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Print the Absoloop terminal logo.",
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
        help="omit the Absoloop wordmark",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    print(
        build_logo(
            width=args.width,
            compact=args.compact,
            color_mode=args.color,
            ascii_only=args.ascii_only,
            wordmark=not args.mark_only,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
