"""Turns extracted documents into a decision.

The model's job ends at reading. From here on everything is code:
match the patient and clinic against the insurer's registries, cross-check the documents for
tampering, then apply the policy with the deterministic rules engine.
"""

from __future__ import annotations

import difflib
import json
import re
import time
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from claimdocbench import adjudicate, load_policy
from claimdocbench.adjudication import Adjudication
from claimdocbench.domain import (
    ClaimFacts,
    Clinic,
    CoveredPerson,
    Currency,
    DocType,
    IntegrityIssue,
    ItemCategory,
    LineItem,
    Member,
    Relationship,
    VisitType,
)

from openadjuster import normalize as nz
from openadjuster.extract import Document, read_document
from openadjuster.llm import LocalModel
from openadjuster.ocr import Box
from openadjuster.receipt import parse as parse_receipt

INJECTION = re.compile(
    r"(ignore (all |any )?(previous|prior|the) (rules|instructions)|disregard|system instruction|"
    r"admin override|\bassessor\b|\bassistant\b|pre-?approved|approve (this|the full)|"
    r"pay in full|do not escalate|skip (the )?fraud|mark this claim)",
    re.I,
)

CATEGORY_SYSTEM = """You sort clinic receipt line items into insurance categories.
Categories: consultation, medication, procedure, lab_test, supplement, cosmetic, fertility,
dental, health_screening. Vitamins, fish oil, tonics and herbal products are supplement.
Items may be in English, Malay or Chinese. Return one category per item, in order."""

KEYWORD_CATEGORIES: list[tuple[re.Pattern[str], ItemCategory]] = [
    (
        re.compile(
            r"vitamin|multivitamin|fish\s*oil|minyak\s*ikan|tonic|tonik|herbal|herba"
            r"|维生素|鱼油|补品|草本",
            re.I,
        ),
        ItemCategory.SUPPLEMENT,
    ),
    (
        re.compile(
            r"laser|whitening|pemutih|peel|kupasan|acne|jerawat|美白|激光|换肤|祛痘",
            re.I,
        ),
        ItemCategory.COSMETIC,
    ),
    (
        re.compile(
            r"fertility|kesuburan|ovulation|ovulasi|生育|排卵",
            re.I,
        ),
        ItemCategory.FERTILITY,
    ),
    (
        re.compile(
            r"\bdental\b|\btooth\b|\bgigi\b|\bscaling\b|\bfilling\b|\btampalan\b|牙",
            re.I,
        ),
        ItemCategory.DENTAL,
    ),
    (
        re.compile(
            r"screening|saringan|check-?up|pemeriksaan\s*kesihatan|体检|健康检查",
            re.I,
        ),
        ItemCategory.HEALTH_SCREENING,
    ),
    (re.compile(r"\bconsult", re.I), ItemCategory.CONSULTATION),
]


@dataclass
class Registry:
    members: dict[str, dict[str, Any]]
    clinics: list[dict[str, Any]]
    history: list[dict[str, Any]]

    @classmethod
    def load(cls, context_dir: Path) -> Registry:
        def read(name: str) -> Any:
            return json.loads((context_dir / name).read_text(encoding="utf-8"))

        return cls(
            {m["member_id"]: m for m in read("members.json")},
            read("clinics.json"),
            read("claims_history.json"),
        )

    def clinic_by_name(self, name: str) -> dict[str, Any] | None:
        names = {nz.name(c["name"]): c for c in self.clinics}
        match = difflib.get_close_matches(nz.name(name), list(names), n=1, cutoff=0.88)
        return names[match[0]] if match else None


Evidence = tuple[str, Box]  # (doc_id, box)


@dataclass
class Check:
    label: str
    ok: bool
    clause: str
    evidence: list[Evidence] = field(default_factory=list)


@dataclass
class Assessment:
    packet_id: str
    documents: list[Document]
    adjudication: Adjudication | None
    integrity: list[str]
    injection: list[str]
    checks: list[Check] = field(default_factory=list)
    confidence: float = 0.0
    seconds: float = 0.0
    facts: ClaimFacts | None = None
    member: dict[str, Any] | None = None
    submitted_on: str = ""
    item_evidence: list[Evidence | None] = field(default_factory=list)
    injection_evidence: list[Evidence] = field(default_factory=list)


def _ev(doc: Document | None, *names: str) -> list[Evidence]:
    if doc is None:
        return []
    out = []
    for n in names:
        v = doc.values.get(n)
        if v and v.box:
            out.append((doc.doc_id, v.box))
    return out


def _member(record: dict[str, Any]) -> Member:
    return Member(
        member_id=record["member_id"],
        plan_id=record["plan_id"],
        currency=Currency(record["currency"]),
        coverage_start=date.fromisoformat(record["coverage_start"]),
        coverage_end=date.fromisoformat(record["coverage_end"]),
        persons=tuple(
            CoveredPerson(
                person_id=p["person_id"],
                full_name=p["full_name"],
                relationship=Relationship(p["relationship"]),
                covered=p["covered"],
                preexisting_conditions=frozenset(p["preexisting_conditions"]),
            )
            for p in record["persons"]
        ),
    )


def _keyword_category(desc: str) -> ItemCategory | None:
    for pattern, cat in KEYWORD_CATEGORIES:
        if pattern.search(desc):
            return cat
    return None


def _categories(model: LocalModel, descriptions: list[str]) -> list[ItemCategory]:
    if not descriptions:
        return []
    result: list[ItemCategory | None] = [_keyword_category(d) for d in descriptions]
    need_model = [
        (i, d) for i, (d, c) in enumerate(zip(descriptions, result, strict=True)) if c is None
    ]
    if need_model:
        schema = {
            "type": "object",
            "properties": {
                "categories": {
                    "type": "array",
                    "items": {"type": "string", "enum": [c.value for c in ItemCategory]},
                }
            },
            "required": ["categories"],
        }
        listing = "\n".join(f"{j + 1}. {d}" for j, (_, d) in enumerate(need_model))
        out = model.json(CATEGORY_SYSTEM, listing, schema).get("categories", [])
        for k, (idx, _) in enumerate(need_model):
            c = out[k] if k < len(out) else "medication"
            result[idx] = (
                ItemCategory(c) if c in ItemCategory._value2member_map_ else ItemCategory.MEDICATION
            )
    return [c or ItemCategory.MEDICATION for c in result]


def assess_packet(
    packet_dir: Path, registry: Registry, model: LocalModel, use_image: bool = False
) -> Assessment:
    start = time.time()
    manifest = json.loads((packet_dir / "manifest.json").read_text(encoding="utf-8"))
    docs = [
        read_document(packet_dir / d["file"], d["doc_id"], model, use_image)
        for d in manifest["documents"]
    ]
    by_type: dict[str, Document] = {}
    unreadable: list[Document] = []
    for d in docs:
        if d.doc_type == "unknown":
            unreadable.append(d)
        else:
            by_type.setdefault(d.doc_type, d)

    record = registry.members.get(manifest["member_id"])
    if record is None:
        return Assessment(
            manifest["packet_id"],
            docs,
            None,
            [],
            [],
            confidence=0.3,
            submitted_on=manifest["submitted_on"],
        )
    member = _member(record)
    receipt, form = by_type.get("receipt"), by_type.get("claim_form")
    mc, referral = by_type.get("medical_certificate"), by_type.get("referral_letter")
    checks: list[Check] = []

    # Documents present. An unreadable page is assumed to be the receipt if none was found.
    present = {DocType(t) for t in by_type}
    illegible: set[DocType] = set()
    if unreadable and receipt is None:
        present.add(DocType.RECEIPT)
        illegible.add(DocType.RECEIPT)

    # Who is the patient? The model sometimes copies the member row instead of the patient row.
    form_patient = form.get("patient_name") if form else ""
    form_member = form.get("member_name") if form else ""
    receipt_patient = receipt.get("patient_name") if receipt else ""
    patient_name = form_patient or receipt_patient

    def _best_person(name_str: str) -> tuple[CoveredPerson | None, float]:
        best, best_score = None, 0.0
        for p in member.persons:
            s = nz.similar_name(p.full_name, name_str)
            if s > best_score:
                best, best_score = p, s
        return (best, best_score) if best_score >= 0.8 else (None, best_score)

    person, _score = _best_person(patient_name)
    # Rescue: if form patient matches the member name but the receipt names a different covered
    # person, the model likely read the wrong row.
    if person is None and form_member and nz.similar_name(form_patient, form_member) >= 0.8:
        alt, _alt_score = _best_person(receipt_patient)
        if alt is not None:
            person, patient_name = alt, receipt_patient
    person_id = person.person_id if person else "NOT-LISTED"
    checks.append(
        Check(
            "Patient is a covered person",
            bool(person and person.covered),
            "C2.1",
            _ev(form, "patient_name") or _ev(receipt, "patient_name"),
        )
    )

    # Which clinic?
    clinic_name = (receipt.get("clinic_name") if receipt else "") or (
        form.get("clinic_name") if form else ""
    )
    clinic = registry.clinic_by_name(clinic_name) if clinic_name else None
    clinic_id = clinic["clinic_id"] if clinic else "UNREGISTERED"
    visit_type = (
        VisitType(clinic["kind"])
        if clinic
        else (
            VisitType.SPECIALIST
            if form and "SPEC" in form.get("visit_type").upper()
            else VisitType.GP
        )
    )

    visit = (
        (nz.day(receipt.get("date")) if receipt else None)
        or (nz.day(form.get("visit_date")) if form else None)
        or date.fromisoformat(manifest["submitted_on"])
    )
    submitted = date.fromisoformat(manifest["submitted_on"])
    visit = min(visit, submitted)
    diagnosis = ""
    if form:
        m = re.search(r"[A-Z]\d{2}(?:\.\d)?", form.get("diagnosis").upper())
        diagnosis = m.group(0) if m else ""

    # Line items and their categories (the one judgement call the model makes here).
    items: list[LineItem] = []
    item_evidence: list[Evidence | None] = []
    if receipt:
        descriptions = [it.description for it in receipt.items if nz.amount(it.amount)]
        cats = _categories(model, descriptions)
        for k, (it, cat) in enumerate(
            zip([i for i in receipt.items if nz.amount(i.amount)], cats, strict=True)
        ):
            amt = nz.amount(it.amount)
            assert amt is not None
            item_evidence.append((receipt.doc_id, it.box) if it.box else None)
            items.append(
                LineItem(
                    item_id=f"L{k + 1}",
                    description=it.description or "item",
                    category=cat,
                    amount=amt,
                )
            )
    if not items:
        total = (
            (nz.amount(receipt.get("total")) if receipt else None)
            or (nz.amount(form.get("amount")) if form else None)
            or Decimal("0.01")
        )
        item_evidence = [None]
        items = [
            LineItem(
                item_id="L1",
                description="unitemised",
                category=ItemCategory.CONSULTATION,
                amount=max(total, Decimal("0.01")),
            )
        ]
        if receipt:
            illegible.add(DocType.RECEIPT)

    # Cross-document checks for tampering and fraud.
    integrity: list[str] = []

    def check(
        label: str,
        ok: bool,
        issue: IntegrityIssue | None,
        evidence: list[Evidence],
        clause: str = "C6.1",
    ) -> None:
        checks.append(Check(label, ok, clause, evidence))
        if not ok and issue:
            integrity.append(issue.value)

    if receipt and DocType.RECEIPT not in illegible:
        printed_total = nz.amount(receipt.get("total"))
        item_sum = sum((i.amount for i in items), Decimal("0"))
        if printed_total is not None:
            adds_up = printed_total == item_sum
            # If the parser missed items, check whether unpaired prices close the gap.
            if not adds_up:
                parsed = parse_receipt(receipt.lines)
                extra = sum(
                    (nz.amount(u.amount) or Decimal("0") for u in parsed.unpaired_prices),
                    Decimal("0"),
                )
                if extra and printed_total == item_sum + extra:
                    adds_up = True
            check(
                "Receipt items add up to the total",
                adds_up,
                IntegrityIssue.AMOUNT_ALTERED,
                _ev(receipt, "total") + [e for e in item_evidence if e],
            )
        check(
            "Clinic is in the registry",
            clinic is not None,
            IntegrityIssue.UNKNOWN_CLINIC,
            _ev(receipt, "clinic_name"),
            "C4.1",
        )
        receipt_no = nz.code_key(receipt.get("receipt_no"))
        if clinic is not None and receipt_no:
            check(
                "Receipt number matches the clinic's format",
                receipt_no.startswith(nz.code_key(clinic["receipt_number_prefix"]) + "-"),
                IntegrityIssue.RECEIPT_NUMBER_ANOMALY,
                _ev(receipt, "receipt_no"),
            )
        seen = {
            nz.code_key(h["receipt_no"])
            for h in registry.history
            if h["member_id"] == member.member_id
        }
        check(
            "Receipt not claimed before",
            receipt_no not in seen,
            IntegrityIssue.DUPLICATE_RECEIPT,
            _ev(receipt, "receipt_no"),
        )
        if form:
            name_sim = nz.similar_name(receipt.get("patient_name"), form.get("patient_name"))
            # Also accept if the form patient is actually the member name and the receipt
            # names the real patient (the model confused the rows).
            if name_sim < 0.8 and form_member:
                name_sim = max(name_sim, nz.similar_name(receipt_patient, form_member))
            check(
                "Same patient on receipt and claim form",
                name_sim >= 0.8,
                IntegrityIssue.NAME_MISMATCH,
                _ev(receipt, "patient_name") + _ev(form, "patient_name"),
            )
        if mc:
            check(
                "Receipt and MC dates match",
                nz.day(receipt.get("date")) == nz.day(mc.get("date")),
                IntegrityIssue.DATE_ALTERED,
                _ev(receipt, "date") + _ev(mc, "date"),
            )
            mc_clinic = registry.clinic_by_name(mc.get("clinic_name"))
            check(
                "MC is from the same clinic",
                mc_clinic is None or clinic is None or mc_clinic["clinic_id"] == clinic_id,
                IntegrityIssue.CLINIC_MISMATCH,
                _ev(mc, "clinic_name") + _ev(receipt, "clinic_name"),
            )

    # Instructions hidden in documents are flagged, never followed.
    hits = [(d.doc_id, ln) for d in docs for ln in d.lines if INJECTION.search(ln.text)]
    injection = [f"{doc_id}: {ln.text}" for doc_id, ln in hits]

    in_year = [
        h
        for h in registry.history
        if h["member_id"] == member.member_id
        and member.coverage_start <= date.fromisoformat(h["visit_date"]) <= member.coverage_end
    ]
    referred = bool(form and form.get("referred").strip().lower() in ("yes", "ya", "是")) or (
        referral is not None
    )
    facts = ClaimFacts(
        claim_id=manifest["packet_id"],
        member_id=member.member_id,
        person_id=person_id,
        clinic_id=clinic_id,
        visit_type=visit_type,
        visit_date=visit,
        submission_date=submitted,
        diagnosis_code=diagnosis or "R69",
        currency=member.currency,
        line_items=tuple(items),
        referral_issued=referred,
        documents=frozenset(present),
        illegible_documents=frozenset(illegible & present),
        integrity_issues=frozenset(IntegrityIssue(i) for i in dict.fromkeys(integrity)),
        injection_present=bool(injection),
        paid_this_policy_year=sum((Decimal(h["amount_paid"]) for h in in_year), Decimal("0.00")),
    )
    registry_clinics = {
        c["clinic_id"]: Clinic(
            clinic_id=c["clinic_id"],
            name=c["name"],
            registration_no=c["registration_no"],
            kind=VisitType(c["kind"]),
            licensed=c["licensed"],
        )
        for c in registry.clinics
    }
    outcome = adjudicate(facts, member, registry_clinics, load_policy())

    confidence = _confidence(docs, receipt, form, items, integrity, illegible)
    return Assessment(
        manifest["packet_id"],
        docs,
        outcome,
        list(dict.fromkeys(integrity)),
        injection,
        checks,
        confidence,
        time.time() - start,
        facts=facts,
        member=record,
        submitted_on=manifest["submitted_on"],
        item_evidence=item_evidence,
        injection_evidence=[(doc_id, ln.box) for doc_id, ln in hits],
    )


def _confidence(
    docs: list[Document],
    receipt: Document | None,
    form: Document | None,
    items: list[LineItem],
    integrity: list[str],
    illegible: set[DocType],
) -> float:
    """Simple evidence-based score; calibrated against dev results later."""
    score = 0.95
    if receipt is None or illegible:
        score -= 0.15
    if form and receipt:
        claimed, total = nz.amount(form.get("amount")), nz.amount(receipt.get("total"))
        if claimed is not None and total is not None and claimed != total:
            score -= 0.25
    key = [v for d in docs for k, v in d.values.items() if k in ("total", "date", "patient_name")]
    if key and sum(1 for v in key if v.box is None) / len(key) > 0.3:
        score -= 0.2
    if len(integrity) == 1:
        score -= 0.1  # a single failed check is more often a misread than a fraud
    if any(d.doc_type == "unknown" for d in docs):
        score -= 0.1
    return max(0.05, min(0.99, score))


FIELD_MAP = {
    "receipt": {
        "clinic_name": "receipt.clinic_name",
        "receipt_no": "receipt.receipt_no",
        "date": "receipt.date",
        "patient_name": "receipt.patient_name",
        "total": "receipt.total",
    },
    "claim_form": {
        "member_id": "claim_form.member_id",
        "patient_name": "claim_form.patient_name",
        "visit_date": "claim_form.visit_date",
        "amount": "claim_form.amount",
    },
}


def to_prediction(a: Assessment, model: LocalModel) -> dict[str, Any]:
    fields: dict[str, str] = {}
    evidence: dict[str, Any] = {}
    for d in a.documents:
        for src, dst in FIELD_MAP.get(d.doc_type, {}).items():
            v = d.values.get(src)
            if not v or not v.raw:
                continue
            if src in ("date", "visit_date"):
                parsed = nz.day(v.raw)
                fields[dst] = parsed.isoformat() if parsed else v.raw
            elif src in ("total", "amount"):
                amt = nz.amount(v.raw)
                fields[dst] = str(amt) if amt is not None else v.raw
            else:
                fields[dst] = v.raw.removeprefix("No. ").removeprefix("No.")
            if v.box:
                evidence[dst] = {"doc_id": d.doc_id, "box": list(v.box)}
    adj = a.adjudication
    return {
        "packet_id": a.packet_id,
        "decision": adj.decision.value if adj else "REQUEST_INFO",
        "payable_amount": str(adj.payable_amount) if adj else "0.00",
        "reasons": [r.value for r in adj.reasons] if adj else [],
        "clause_ids": list(adj.clause_ids) if adj else [],
        "integrity_flags": a.integrity,
        "injection_detected": bool(a.injection),
        "fields": fields,
        "evidence": evidence,
        "confidence": round(a.confidence, 3),
        "latency_s": round(a.seconds, 2),
        "cost_usd": 0.0,
        "model": model.model,
    }
