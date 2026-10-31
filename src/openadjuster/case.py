"""A case record: everything the review screen shows for one claim, as plain JSON.

The same record feeds the live local console and the static demo on GitHub Pages.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import UTC, datetime
from importlib.resources import files
from pathlib import Path
from typing import Any

from claimdocbench import load_policy
from claimdocbench.adjudication import REASON_CLAUSE
from PIL import Image

from openadjuster import __version__
from openadjuster.assess import Assessment
from openadjuster.extract import HINTS, SYSTEM
from openadjuster.llm import model_digest


def _sha(*parts: bytes) -> str:
    h = hashlib.sha256()
    for part in parts:
        h.update(part)
    return h.hexdigest()[:16]


def versions(model: str) -> dict[str, str | None]:
    """Fingerprints of everything a decision depends on, so a replay can prove it matches."""
    policy = files("claimdocbench").joinpath("data/policy.yaml").read_bytes()
    source = sorted(Path(__file__).parent.glob("*.py"))
    return {
        "model": model_digest(model),
        "prompt": _sha(SYSTEM.encode(), json.dumps(HINTS, sort_keys=True, default=str).encode()),
        "policy": _sha(policy),
        "pipeline": _sha(*(p.read_bytes() for p in source)),
    }


LABELS = {
    "claim_form": "Claim form",
    "receipt": "Receipt",
    "medical_certificate": "Medical certificate",
    "referral_letter": "Referral letter",
    "unknown": "Unreadable page",
}

CLOSE_REVIEW_BELOW = 0.9
ROUTE = {
    "APPROVE": "Ready for approval",
    "PARTIAL": "Ready for approval",
    "REJECT": "Ready for approval",
    "REQUEST_INFO": "Ask the member for documents",
    "ESCALATE": "Send to fraud review",
}


def _clause(cid: str) -> dict[str, str]:
    c = load_policy().clauses.get(cid)
    return {"id": cid, "title": c.title if c else "", "text": c.text if c else ""}


def build_case(
    a: Assessment, packet_dir: Path, model: str, gold: dict[str, Any] | None = None
) -> dict[str, Any]:
    adj = a.adjudication
    record = a.member or {}
    facts = a.facts
    patient = ""
    if facts and record:
        patient = next(
            (
                p["full_name"]
                for p in record.get("persons", [])
                if p["person_id"] == facts.person_id
            ),
            "",
        )
    if not patient:
        patient = next((d.get("patient_name") for d in a.documents if d.get("patient_name")), "")

    reasons = []
    if adj:
        for r in adj.reasons:
            cid = REASON_CLAUSE.get(r)
            reasons.append({"code": r.value, "clause": _clause(cid) if cid else None})
    items = []
    if adj and facts:
        for k, (line, outcome) in enumerate(zip(facts.line_items, adj.items, strict=False)):
            ev = a.item_evidence[k] if k < len(a.item_evidence) else None
            items.append(
                {
                    "description": line.description,
                    "amount": str(line.amount),
                    "category": outcome.category.value,
                    "covered": outcome.covered,
                    "clause": _clause(outcome.clause_id) if outcome.clause_id else None,
                    "evidence": {"doc_id": ev[0], "box": list(ev[1])} if ev else None,
                }
            )

    documents = []
    for d in a.documents:
        width, height = Image.open(packet_dir / d.file).size
        documents.append(
            {
                "doc_id": d.doc_id,
                "type": d.doc_type,
                "label": LABELS.get(d.doc_type, d.doc_type),
                "file": d.file,
                "width": width,
                "height": height,
                "fields": [
                    {"name": k, "value": v.raw, "box": list(v.box) if v.box else None}
                    for k, v in d.values.items()
                    if v.raw
                ],
            }
        )

    case: dict[str, Any] = {
        "packet_id": a.packet_id,
        "member": {
            "member_id": record.get("member_id", ""),
            "plan": record.get("plan_id", ""),
            "currency": record.get("currency", ""),
            "employer": record.get("employer", ""),
            "patient": patient,
        },
        "submitted_on": a.submitted_on,
        "decision": {
            "decision": adj.decision.value if adj else "REQUEST_INFO",
            "payable": str(adj.payable_amount) if adj else "0.00",
            "claimed": str(adj.claimed_amount) if adj else "0.00",
            "currency": adj.currency.value if adj else record.get("currency", ""),
            "route": _route(adj.decision.value if adj else "REQUEST_INFO", a.confidence),
            "confidence": round(a.confidence, 2),
            "reasons": reasons,
        },
        "checks": [
            {
                "label": c.label,
                "ok": c.ok,
                "clause": _clause(c.clause),
                "evidence": [{"doc_id": e[0], "box": list(e[1])} for e in c.evidence],
            }
            for c in a.checks
        ],
        "items": items,
        "injection": [
            {"text": t.split(": ", 1)[-1], "doc_id": e[0], "box": list(e[1])}
            for t, e in zip(a.injection, a.injection_evidence, strict=False)
        ],
        "documents": documents,
        "run": {
            "model": model,
            "seconds": round(a.seconds, 1),
            "cost_usd": 0.0,
            "version": __version__,
            "versions": versions(model),
            "assessed_at": datetime.now(UTC).isoformat(timespec="seconds"),
        },
        "review": None,
    }
    if gold:
        case["benchmark"] = {
            "decision": gold["decision"],
            "payable": gold["payable_amount"],
            "kind": gold["kind"],
            "variant": gold["variant"],
        }
    return case


def write_case(case: dict[str, Any], packet_dir: Path, out_dir: Path) -> Path:
    """Writes `<out>/<packet_id>/case.json` with copies of the document images."""
    target = out_dir / str(case["packet_id"])
    target.mkdir(parents=True, exist_ok=True)
    for doc in case["documents"]:
        shutil.copy2(packet_dir / doc["file"], target / doc["file"])
    path = target / "case.json"
    path.write_text(json.dumps(case, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def write_index(out_dir: Path) -> Path:
    rows = []
    for path in sorted(out_dir.glob("*/case.json")):
        c = json.loads(path.read_text(encoding="utf-8"))
        rows.append(
            {
                "packet_id": c["packet_id"],
                "patient": c["member"]["patient"],
                "decision": c["decision"]["decision"],
                "payable": c["decision"]["payable"],
                "claimed": c["decision"]["claimed"],
                "currency": c["decision"]["currency"],
                "flags": sum(1 for ch in c["checks"] if not ch["ok"]),
                "injection": bool(c["injection"]),
                "variant": (c.get("benchmark") or {}).get("variant"),
            }
        )
    index: Path = out_dir / "index.json"
    index.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    return index


def _route(decision: str, confidence: float) -> str:
    route = ROUTE.get(decision, "")
    if route == "Ready for approval" and confidence < CLOSE_REVIEW_BELOW:
        return "Check closely before approving"
    return route


def replay_diff(stored: dict[str, Any], fresh: dict[str, Any]) -> list[str]:
    """What changed between a recorded decision and a re-run of it. Empty means identical."""
    diffs = [
        f"decision.{k}: {stored['decision'][k]} -> {fresh['decision'][k]}"
        for k in ("decision", "payable", "route")
        if stored["decision"][k] != fresh["decision"][k]
    ]
    old, new = stored["run"].get("versions", {}), fresh["run"]["versions"]
    diffs += [f"version.{k}: {old.get(k)} -> {new[k]}" for k in new if old.get(k) != new[k]]
    return diffs
