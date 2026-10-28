"""Works out what kind of document a page is from its OCR text.

Titles are distinctive in all three languages, so keywords settle almost every page. The
receipt check comes last because claim forms and MCs also mention "receipt" in passing.
"""

from __future__ import annotations

import re

from openadjuster.ocr import Line

PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("claim_form", re.compile(r"claim form|borang tuntutan|索赔表格", re.I)),
    (
        "medical_certificate",
        re.compile(r"medical certificate|sijil cuti sakit|医疗证明书|病假单", re.I),
    ),
    ("referral_letter", re.compile(r"referral|rujukan|转诊", re.I)),
    ("receipt", re.compile(r"receipt|resit|收据|tax invoice|invois|发票", re.I)),
]


def classify(lines: list[Line]) -> str:
    """Returns claim_form, medical_certificate, referral_letter, receipt or unknown."""
    head = " ".join(ln.text for ln in lines[:12])
    for doc_type, pattern in PATTERNS:
        if pattern.search(head):
            return doc_type
    full = " ".join(ln.text for ln in lines)
    for doc_type, pattern in PATTERNS:
        if pattern.search(full):
            return doc_type
    return "unknown"
