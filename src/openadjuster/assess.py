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


@dataclass
class Assessment:
    packet_id: str
    documents: list[Document]
    adjudication: Adjudication | None
    integrity: list[str]
    injection: list[str]
    checks: list[tuple[str, bool, str]] = field(default_factory=list)
    confidence: float = 0.0
    seconds: float = 0.0


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


def _categories(model: LocalModel, descriptions: list[str]) -> list[ItemCategory]:
    if not descriptions:
        return []
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
    listing = "\n".join(f"{i + 1}. {d}" for i, d in enumerate(descriptions))
    out = model.json(CATEGORY_SYSTEM, listing, schema).get("categories", [])
    cats = [
        ItemCategory(c) if c in ItemCategory._value2member_map_ else ItemCategory.MEDICATION
        for c in out
    ]
    return (cats + [ItemCategory.MEDICATION] * len(descriptions))[: len(descriptions)]


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
        return Assessment(manifest["packet_id"], docs, None, [], [], confidence=0.3)
    member = _member(record)
    receipt, form = by_type.get("receipt"), by_type.get("claim_form")
    mc, referral = by_type.get("medical_certificate"), by_type.get("referral_letter")
    checks: list[tuple[str, bool, str]] = []

    # Documents present. An unreadable page is assumed to be the receipt if none was found.
    present = {DocType(t) for t in by_type}
    illegible: set[DocType] = set()
    if unreadable and receipt is None:
        present.add(DocType.RECEIPT)
        illegible.add(DocType.RECEIPT)

    # Who is the patient?
    patient_name = (
        form.get("patient_name") if form else (receipt.get("patient_name") if receipt else "")
    )
    person = next((p for p in member.persons if nz.same_name(p.full_name, patient_name)), None)
    person_id = person.person_id if person else "NOT-LISTED"
    checks.append(("Patient is a covered person", bool(person and person.covered), "C2.1"))

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
    if receipt:
        descriptions = [it.description for it in receipt.items if nz.amount(it.amount)]
        cats = _categories(model, descriptions)
        for k, (it, cat) in enumerate(
            zip([i for i in receipt.items if nz.amount(i.amount)], cats, strict=True)
        ):
            amt = nz.amount(it.amount)
            assert amt is not None
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

    def check(label: str, ok: bool, issue: IntegrityIssue | None, clause: str = "C6.1") -> None:
        checks.append((label, ok, clause))
        if not ok and issue:
            integrity.append(issue.value)

    if receipt and DocType.RECEIPT not in illegible:
        printed_total = nz.amount(receipt.get("total"))
        item_sum = sum((i.amount for i in items), Decimal("0"))
        if printed_total is not None:
            check(
                "Receipt items add up to the total",
                printed_total == item_sum,
                IntegrityIssue.AMOUNT_ALTERED,
            )
        check("Clinic is in the registry", clinic is not None, IntegrityIssue.UNKNOWN_CLINIC)
        receipt_no = nz.code_key(receipt.get("receipt_no"))
        if clinic is not None and receipt_no:
            check(
                "Receipt number matches the clinic's format",
                receipt_no.startswith(nz.code_key(clinic["receipt_number_prefix"]) + "-"),
                IntegrityIssue.RECEIPT_NUMBER_ANOMALY,
            )
        seen = {
            nz.code_key(h["receipt_no"])
            for h in registry.history
            if h["member_id"] == member.member_id
        }
        check(
            "Receipt not claimed before", receipt_no not in seen, IntegrityIssue.DUPLICATE_RECEIPT
        )
        if form:
            check(
                "Same patient on receipt and claim form",
                nz.same_name(receipt.get("patient_name"), form.get("patient_name")),
                IntegrityIssue.NAME_MISMATCH,
            )
        if mc:
            check(
                "Receipt and MC dates match",
                nz.day(receipt.get("date")) == nz.day(mc.get("date")),
                IntegrityIssue.DATE_ALTERED,
            )
            mc_clinic = registry.clinic_by_name(mc.get("clinic_name"))
            check(
                "MC is from the same clinic",
                mc_clinic is None or clinic is None or mc_clinic["clinic_id"] == clinic_id,
                IntegrityIssue.CLINIC_MISMATCH,
            )

    # Instructions hidden in documents are flagged, never followed.
    injection = [
        f"{d.doc_id}: {ln.text}" for d in docs for ln in d.lines if INJECTION.search(ln.text)
    ]

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
