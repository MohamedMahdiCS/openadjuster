"""Text recognition with Apple's Vision framework (on-device, no model download).

Returns each recognised line with its pixel box in the image, top-left origin, in the same
(x, y, width, height) format ClaimDocBench uses for gold evidence boxes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

Box = tuple[int, int, int, int]


@dataclass(frozen=True)
class Line:
    text: str
    confidence: float
    box: Box


CJK = re.compile(r"[\u4e00-\u9fff]")


def _recognize(path: Path, languages: list[str]) -> list[tuple[str, float, tuple[float, ...]]]:
    from ocrmac import ocrmac  # macOS only

    result: list[tuple[str, float, tuple[float, ...]]] = ocrmac.OCR(
        str(path), language_preference=languages
    ).recognize()
    return result


def read_lines(path: Path) -> list[Line]:
    width, height = Image.open(path).size
    # English-first reads English and Malay best but turns Chinese into junk; Chinese-first is
    # the reverse. Run both and keep the Chinese pass only if it found real Chinese text.
    raw = _recognize(path, ["en-US", "zh-Hans"])
    raw_zh = _recognize(path, ["zh-Hans", "en-US"])
    if len(CJK.findall("".join(r[0] for r in raw_zh))) >= 8:
        raw = raw_zh
    lines = []
    for text, conf, (nx, ny, nw, nh) in raw:
        # Vision boxes are normalised with the origin at the bottom-left.
        x = round(nx * width)
        y = round((1 - ny - nh) * height)
        lines.append(Line(text, float(conf), (x, y, round(nw * width), round(nh * height))))
    lines.sort(key=lambda ln: (ln.box[1] // 12, ln.box[0]))  # reading order, row by row
    return lines


def as_prompt_text(lines: list[Line]) -> str:
    """Numbered lines, so a model can cite which line a value came from."""
    return "\n".join(f"[{i}] {ln.text}" for i, ln in enumerate(lines))


@dataclass(frozen=True)
class Row:
    """OCR lines that sit on the same visual row, joined left to right."""

    text: str
    box: Box
    lines: tuple[Line, ...]


def rows(lines: list[Line]) -> list[Row]:
    out: list[list[Line]] = []
    for ln in sorted(lines, key=lambda x: x.box[1] + x.box[3] / 2):
        mid = ln.box[1] + ln.box[3] / 2
        if out:
            last = out[-1]
            ref = sum(x.box[1] + x.box[3] / 2 for x in last) / len(last)
            height = max(x.box[3] for x in last)
            if abs(mid - ref) < 0.6 * max(height, ln.box[3]):
                last.append(ln)
                continue
        out.append([ln])
    result = []
    for group in out:
        group.sort(key=lambda x: x.box[0])
        x0 = min(g.box[0] for g in group)
        y0 = min(g.box[1] for g in group)
        x1 = max(g.box[0] + g.box[2] for g in group)
        y1 = max(g.box[1] + g.box[3] for g in group)
        result.append(
            Row(" | ".join(g.text for g in group), (x0, y0, x1 - x0, y1 - y0), tuple(group))
        )
    return result


def rows_prompt_text(rs: list[Row]) -> str:
    return "\n".join(f"[{i}] {r.text}" for i, r in enumerate(rs))
