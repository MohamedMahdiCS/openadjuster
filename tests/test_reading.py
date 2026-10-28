from datetime import date
from decimal import Decimal

from openadjuster import normalize as nz
from openadjuster.classify import classify
from openadjuster.ocr import Line
from openadjuster.receipt import parse


def test_amounts_survive_ocr_noise() -> None:
    assert nz.amount("RM 263-50") == Decimal("263.50")
    assert nz.amount("S$1,234.50") == Decimal("1234.50")
    assert nz.amount("MYR 8,50") == Decimal("8.50")
    assert nz.amount("13-09-2026") is None


def test_dates_in_three_languages() -> None:
    assert nz.day("12 Mac 2026") == date(2026, 3, 12)
    assert nz.day("2026年2月21日") == date(2026, 2, 21)
    assert nz.day("21/09/2026 15:51") == date(2026, 9, 21)
    assert nz.day("2026-06-10") == date(2026, 6, 10)


def test_names_and_codes_ignore_ocr_noise() -> None:
    assert nz.same_name("Chan Méi Ling", "chan mei  ling")
    assert not nz.same_name("Lim Xin Yi", "Priya a/p Gopal")
    assert nz.code_key("No. 0C7-2609292") == nz.code_key("OC7-2609292")


def _line(text: str, x: int, y: int, w: int = 200, h: int = 24) -> Line:
    return Line(text, 1.0, (x, y, w, h))


def test_receipt_parser_pairs_items_on_a_tilted_page() -> None:
    # Prices on the right sit 12 px lower per row than their descriptions (a tilted photo).
    lines = [
        _line("OFFICIAL RECEIPT", 100, 40),
        _line("Date: 21-09-2026", 20, 80),
        _line("Consultation fee", 20, 130),
        _line("RM 30.00", 600, 142, 90),
        _line("Paracetamol 500mg x 10", 20, 170),
        _line("RM 5.50", 600, 182, 90),
        _line("Vitamin C 1000mg x 30", 20, 210),
        _line("RM 25.00", 600, 222, 90),
        _line("TOTAL", 20, 260, 80),
        _line("RM 60.50", 600, 272, 90),
    ]
    parsed = parse(lines)
    assert parsed.total == "RM 60.50"
    assert [(i.description, i.amount) for i in parsed.items] == [
        ("Consultation fee", "RM 30.00"),
        ("Paracetamol 500mg x 10", "RM 5.50"),
        ("Vitamin C 1000mg x 30", "RM 25.00"),
    ]


def test_addresses_are_not_prices() -> None:
    lines = [
        _line("Blk 446 Clementi St 90, #01-52, Singapore", 20, 20, 500),
        _line("Consultation fee", 20, 100),
        _line("S$ 45.00", 600, 100, 90),
        _line("TOTAL", 20, 140, 80),
        _line("S$ 45.00", 600, 140, 90),
    ]
    assert [i.amount for i in parse(lines).items] == ["S$ 45.00"]


def test_document_types_in_three_languages() -> None:
    assert classify([_line("GROUP OUTPATIENT CLAIM FORM", 0, 0)]) == "claim_form"
    assert classify([_line("SIJIL CUTI SAKIT", 0, 0)]) == "medical_certificate"
    assert classify([_line("正式收据", 0, 0)]) == "receipt"
    assert classify([_line("nothing readable", 0, 0)]) == "unknown"
