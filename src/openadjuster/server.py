"""Local review console: serves case records and the UI, assesses new claims, logs reviews.

Case files live under /data exactly as in the static demo, so the same front end works in both.
The live server adds /api endpoints for running an assessment and recording a reviewer decision.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from openadjuster.assess import Registry, assess_packet
from openadjuster.case import build_case, write_case, write_index
from openadjuster.llm import LocalModel

CONSOLE_DIST = Path(__file__).resolve().parents[2] / "console" / "dist"
PACKET_ID = re.compile(r"^[0-9a-f]{12}t?$")


class AssessRequest(BaseModel):
    packet_id: str


class ReviewRequest(BaseModel):
    action: Literal["approve", "override", "request_info"]
    note: str = ""
    payable: str | None = None
    reviewer: str = "reviewer"


def create_app(cases: Path, split_dir: Path | None, model: str) -> FastAPI:
    cases.mkdir(parents=True, exist_ok=True)
    write_index(cases)
    app = FastAPI(title="OpenAdjuster")
    llm = LocalModel(model)
    registry = Registry.load(split_dir / "context") if split_dir else None

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {"mode": "live", "model": model, "can_assess": registry is not None}

    @app.get("/api/packets")
    def packets() -> list[str]:
        if split_dir is None:
            return []
        index = json.loads((split_dir / "index.json").read_text(encoding="utf-8"))
        done = {p.name for p in cases.iterdir() if p.is_dir()}
        return [p for p in index["packets"] if p not in done]

    @app.post("/api/assess")
    def assess(req: AssessRequest) -> dict[str, Any]:
        if registry is None or split_dir is None:
            raise HTTPException(400, "Start the server with --split-dir to assess claims")
        if not PACKET_ID.match(req.packet_id):
            raise HTTPException(400, "Unknown packet")
        pdir = split_dir / "packets" / req.packet_id
        if not pdir.is_dir():
            raise HTTPException(404, "Unknown packet")
        case = build_case(assess_packet(pdir, registry, llm), pdir, model)
        write_case(case, pdir, cases)
        write_index(cases)
        return case

    @app.post("/api/cases/{packet_id}/review")
    def review(packet_id: str, req: ReviewRequest) -> dict[str, Any]:
        if not PACKET_ID.match(packet_id):
            raise HTTPException(404, "Unknown case")
        path = cases / packet_id / "case.json"
        if not path.exists():
            raise HTTPException(404, "Unknown case")
        case: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        entry = {
            "at": datetime.now(UTC).isoformat(timespec="seconds"),
            "reviewer": req.reviewer,
            "action": req.action,
            "note": req.note,
            "recommended": case["decision"]["decision"],
            "recommended_payable": case["decision"]["payable"],
            "final_payable": req.payable
            if req.action == "override"
            else case["decision"]["payable"]
            if req.action == "approve"
            else "0.00",
        }
        case["review"] = entry
        path.write_text(json.dumps(case, indent=2, ensure_ascii=False), encoding="utf-8")
        # Every human decision is kept, and overrides become test cases for the next version.
        with (cases / "audit.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"packet_id": packet_id, **entry}) + "\n")
        write_index(cases)
        return case

    app.mount("/data", StaticFiles(directory=cases), name="data")
    if CONSOLE_DIST.is_dir():
        app.mount("/", StaticFiles(directory=CONSOLE_DIST, html=True), name="console")
    return app


def serve(cases: Path, split_dir: Path | None, model: str, port: int) -> None:
    import uvicorn

    uvicorn.run(create_app(cases, split_dir, model), host="127.0.0.1", port=port)
