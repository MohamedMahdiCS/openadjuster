"""Turns printed values into canonical ones: amounts to Decimal, dates to ISO, names tidied."""

from __future__ import annotations

import re
import unicodedata
from datetime import date
from decimal import Decimal, InvalidOperation

MONTHS = {
    m: i
    for i, m in enumerate(
        ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1
    )
}
MONTHS |= {"mac": 3, "mei": 5, "ogo": 8, "okt": 10, "dis": 12}

# OCR sometimes reads the decimal point as "-" or ",": "RM 263-50".
AMOUNT = re.compile(r"(\d{1,3}(?:,\d{3})*|\d+)[.\-,](\d{2})(?![\d\-/])")


def amount(text: str | None) -> Decimal | None:
    if not text:
        return None
    m = AMOUNT.search(text.replace(" ", ""))
    if not m:
        return None
    try:
        return Decimal(m.group(1).replace(",", "") + "." + m.group(2))
    except InvalidOperation:
        return None


def day(text: str | None) -> date | None:
    if not text:
        return None
    t = text.strip().lower()
    patterns = [
        (r"(\d{4})-(\d{1,2})-(\d{1,2})", "ymd"),
        (r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日", "ymd"),
        (r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})", "dmy"),
        (r"(\d{1,2})\s+([a-z]{3})[a-z]*\.?\s+(\d{4})", "dMy"),
    ]
    for pattern, order in patterns:
        m = re.search(pattern, t)
        if not m:
            continue
        try:
            if order == "ymd":
                return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            if order == "dmy":
                return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
            month = MONTHS.get(m.group(2)[:3])
            if month:
                return date(int(m.group(3)), month, int(m.group(1)))
        except ValueError:
            continue
    return None


def name(text: str | None) -> str:
    # Drop accents the handwriting font tempts OCR into ("Méi" -> "Mei").
    plain = "".join(
        c for c in unicodedata.normalize("NFKD", text or "") if not unicodedata.combining(c)
    )
    return re.sub(r"\s+", " ", plain).strip().casefold()


CONFUSABLE = str.maketrans({"0": "O", "1": "I", "l": "I", "5": "S", "8": "B"})


def code_key(text: str) -> str:
    """Compare codes like receipt numbers without tripping on 0/O and 1/I OCR mix-ups."""
    return text.replace(" ", "").upper().removeprefix("NO.").translate(CONFUSABLE)


def same_name(a: str | None, b: str | None) -> bool:
    """Names match if they're equal after tidying, ignoring OCR noise in punctuation."""

    def key(x: str | None) -> str:
        return re.sub(r"[^a-z0-9一-鿿]", "", name(x))

    return bool(key(a)) and key(a) == key(b)
