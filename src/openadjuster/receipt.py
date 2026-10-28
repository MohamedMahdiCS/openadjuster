"""Reads receipt line items and the total with plain code, not the model.

Small models mis-pair item names with prices when OCR returns them as separate lines, and a
one-row shift makes an honest receipt look forged. Receipts are regular enough to parse:
find the total row, estimate how much the page is tilted from it, straighten the coordinates,
group text into rows, and read every row above the total that ends in a price.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from openadjuster.ocr import Box, Line

# Currency is optional and allowed to be a little garbled ("MIYR 8.50"), the amount is not.
MONEY = re.compile(
    # With a currency marker, OCR'd "-" or "," decimals are accepted ("RM 263-50");
    # bare numbers need a real decimal point, so addresses like "#01-52" never look like prices.
    r"(?:RM|S\$|MYR|SGD|M[I1l]YR|\$)\s?\d{1,3}(?:,\d{3})*[.\-,]\d{2}(?![\d\-/])"
    r"|(?<![\d.\-/#])\d{1,3}(?:,\d{3})*\.\d{2}(?![\d\-/])",
    re.I,
)
HEADER = re.compile(r"^(#|description|keterangan|项目|amount|amaun|金额|qty|code)$", re.I)
TOTAL = re.compile(r"\b(total|jumlah)\b|总额|总计|合计", re.I)
NOT_ITEM = re.compile(
    r"\b(tel|reg|date|tarikh|receipt|resit|invoice|invois|paid by|bayaran|no\.)\b"
    r"|日期|收据|发票|付款",
    re.I,
)


@dataclass(frozen=True)
class ParsedItem:
    description: str
    amount: str
    box: Box


@dataclass(frozen=True)
class ParsedReceipt:
    items: list[ParsedItem]
    total: str
    total_box: Box | None


def _mid(ln: Line) -> tuple[float, float]:
    x, y, w, h = ln.box
    return x + w / 2, y + h / 2


def _slope(lines: list[Line]) -> float:
    """Tilt of the page, from the TOTAL label to the price on the same row."""
    for label in reversed(lines):
        if TOTAL.search(label.text) and not MONEY.search(label.text):
            lx, ly = _mid(label)
            prices = [
                ln
                for ln in lines
                if MONEY.search(ln.text)
                and _mid(ln)[0] > lx
                and abs(_mid(ln)[1] - ly) < 4 * label.box[3]
            ]
            if prices:
                px, py = _mid(min(prices, key=lambda p: abs(_mid(p)[1] - ly)))
                if px - lx > 20:
                    return (py - ly) / (px - lx)
    return 0.0


def _level(ln: Line, slope: float) -> float:
    x, y = _mid(ln)
    return y - slope * x


def parse(lines: list[Line]) -> ParsedReceipt:
    """Price-first: find every price, then the closest description to its left on the same
    (straightened) row. The total is the price on the row of the last TOTAL label."""
    slope = _slope(lines)
    prices = [ln for ln in lines if MONEY.search(ln.text)]
    texts = [ln for ln in lines if not MONEY.search(ln.text)]

    total, total_box, total_level = "", None, float("inf")
    labels = [ln for ln in lines if TOTAL.search(ln.text)]
    if labels:
        label = max(labels, key=lambda ln: _level(ln, slope))
        if MONEY.search(label.text):
            total_line = label
        else:
            right = [p for p in prices if _mid(p)[0] > _mid(label)[0]] or prices
            total_line = min(
                right, key=lambda p: abs(_level(p, slope) - _level(label, slope)), default=label
            )
        if MONEY.search(total_line.text):
            total, total_box = MONEY.findall(total_line.text)[-1], total_line.box
            total_level = _level(total_line, slope)

    item_prices = sorted(
        (p for p in prices if p.box != total_box and _level(p, slope) < total_level - 2),
        key=lambda p: _level(p, slope),
    )
    if not item_prices:
        return ParsedReceipt([], total, total_box)
    left_edge = min(_mid(p)[0] for p in item_prices)
    top = _level(item_prices[0], slope) - 1.5 * item_prices[0].box[3]
    descs = sorted(
        (
            t
            for t in texts
            if _mid(t)[0] < left_edge
            and top <= _level(t, slope) < total_level - 0.5 * t.box[3]
            and not NOT_ITEM.search(t.text)
            and not HEADER.match(t.text.strip())
            and not t.text.strip().isdigit()
            and not TOTAL.search(t.text)
        ),
        key=lambda t: _level(t, slope),
    )

    def clean(desc: str) -> str:
        return re.sub(r"^\d{1,2}\s+", "", desc).strip(" |:-")

    items: list[ParsedItem] = []
    if len(descs) == len(item_prices):
        # Same count: pair in order. Survives perspective, where tilt changes down the page.
        for d, p in zip(descs, item_prices, strict=True):
            items.append(ParsedItem(clean(d.text), MONEY.findall(p.text)[-1], p.box))
        return ParsedReceipt(items, total, total_box)
    for price in item_prices:
        own = MONEY.sub("", price.text).strip(" |:-")
        near = min(descs, key=lambda t: abs(_level(t, slope) - _level(price, slope)), default=None)
        if own:
            desc = own
        elif near and abs(_level(near, slope) - _level(price, slope)) < 1.0 * price.box[3]:
            desc = near.text
        else:
            continue
        if not NOT_ITEM.search(desc) and clean(desc):
            items.append(ParsedItem(clean(desc), MONEY.findall(price.text)[-1], price.box))
    return ParsedReceipt(items, total, total_box)
