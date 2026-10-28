import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from openadjuster.server import create_app

CASE: dict[str, Any] = {
    "packet_id": "abcdef123456",
    "member": {"member_id": "M1", "plan": "A", "currency": "MYR", "employer": "", "patient": "A"},
    "submitted_on": "2026-06-12",
    "decision": {
        "decision": "PARTIAL",
        "payable": "45.00",
        "claimed": "50.00",
        "currency": "MYR",
        "route": "",
        "confidence": 0.9,
        "reasons": [],
    },
    "checks": [],
    "items": [],
    "injection": [],
    "documents": [],
    "run": {"model": "m", "seconds": 1, "cost_usd": 0, "version": "0", "assessed_at": ""},
    "review": None,
}


def _client(tmp: Path) -> TestClient:
    (tmp / CASE["packet_id"]).mkdir(parents=True)
    (tmp / CASE["packet_id"] / "case.json").write_text(json.dumps(CASE))
    return TestClient(create_app(tmp, None, "m"))


def test_health_and_case_files(tmp_path: Path) -> None:
    client = _client(tmp_path)
    assert client.get("/api/health").json()["mode"] == "live"
    index = client.get("/data/index.json").json()
    assert index[0]["decision"] == "PARTIAL"


def test_override_is_saved_and_audited(tmp_path: Path) -> None:
    client = _client(tmp_path)
    res = client.post(
        f"/api/cases/{CASE['packet_id']}/review",
        json={"action": "override", "payable": "50.00", "note": "clinic confirmed"},
    )
    assert res.status_code == 200
    assert res.json()["review"]["final_payable"] == "50.00"
    audit = (tmp_path / "audit.jsonl").read_text().splitlines()
    assert json.loads(audit[0])["recommended_payable"] == "45.00"


def test_unknown_case_and_bad_ids_are_rejected(tmp_path: Path) -> None:
    client = _client(tmp_path)
    # Path tricks never reach the review handler (the client normalises them away).
    escape = client.post("/api/cases/../../etc/review", json={"action": "approve"})
    assert escape.status_code in (404, 405)
    assert (
        client.post("/api/cases/ffffffffffff/review", json={"action": "approve"}).status_code == 404
    )
    assert client.post("/api/assess", json={"packet_id": "x"}).status_code == 400
