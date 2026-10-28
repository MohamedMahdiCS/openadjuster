"""Text recognition with Apple's Vision framework (on-device, no model download).

Returns each recognised line with its pixel box in the image, top-left origin, in the same
(x, y, width, height) format ClaimDocBench uses for gold evidence boxes.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image

Box = tuple[int, int, int, int]


@dataclass(frozen=True)
class Line:
    text: str
    confidence: float
    box: Box


def read_lines(path: Path) -> list[Line]:
    from ocrmac import ocrmac  # macOS only

    width, height = Image.open(path).size
    raw = ocrmac.OCR(str(path), language_preference=["en-US", "zh-Hans"]).recognize()
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
