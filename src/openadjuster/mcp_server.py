"""MCP tool server: expose OpenAdjuster as tools for any MCP client."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer

from openadjuster.assess import Registry, assess_packet, to_prediction
from openadjuster.llm import DEFAULT_MODEL, LocalModel

mcp = MCPServer("openadjuster")

_registry: Registry | None = None
_model: LocalModel | None = None
_split_dir: Path | None = None
_cases_dir: Path | None = None


def configure(split_dir: Path, cases: Path, model: str = DEFAULT_MODEL) -> None:
    global _registry, _model, _split_dir, _cases_dir
    _split_dir = split_dir
    _cases_dir = cases
    _cases_dir.mkdir(parents=True, exist_ok=True)
    _registry = Registry.load(split_dir / "context")
    _model = LocalModel(model)


@mcp.tool()
def list_pending() -> str:
    """List claim packet IDs that have not been assessed yet."""
    if _split_dir is None:
        return json.dumps({"error": "Server not configured with a split directory"})
    index = json.loads((_split_dir / "index.json").read_text(encoding="utf-8"))
    done = set()
    if _cases_dir and _cases_dir.is_dir():
        done = {p.name for p in _cases_dir.iterdir() if p.is_dir()}
    pending = [p for p in index["packets"] if p not in done]
    return json.dumps({"pending": pending, "count": len(pending)})


@mcp.tool()
def assess_claim(packet_id: str) -> str:
    """Assess a single claim packet. Returns the AI recommendation with evidence."""
    if _registry is None or _model is None or _split_dir is None:
        return json.dumps({"error": "Server not configured"})
    pdir = _split_dir / "packets" / packet_id
    if not pdir.is_dir():
        return json.dumps({"error": f"Unknown packet: {packet_id}"})

    result = assess_packet(pdir, _registry, _model)
    prediction = to_prediction(result, _model)

    if _cases_dir:
        from openadjuster.case import build_case, write_case, write_index

        case = build_case(result, pdir, _model.model)
        write_case(case, pdir, _cases_dir)
        write_index(_cases_dir)

    return json.dumps(prediction, ensure_ascii=False)


@mcp.tool()
def review_claim(
    packet_id: str,
    action: str,
    note: str = "",
    payable: str | None = None,
    reviewer: str = "reviewer",
) -> str:
    """Record a human review decision on an assessed claim.

    action: "approve" (accept AI recommendation), "override" (set different payable),
            or "request_info" (send back for more documents).
    """
    if _cases_dir is None:
        return json.dumps({"error": "Server not configured"})
    path = _cases_dir / packet_id / "case.json"
    if not path.exists():
        return json.dumps({"error": f"No assessed case for {packet_id}"})
    if action not in ("approve", "override", "request_info"):
        return json.dumps({"error": f"Invalid action: {action}"})

    case: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    entry = {
        "at": datetime.now(UTC).isoformat(timespec="seconds"),
        "reviewer": reviewer,
        "action": action,
        "note": note,
        "recommended": case["decision"]["decision"],
        "recommended_payable": case["decision"]["payable"],
        "final_payable": payable
        if action == "override"
        else case["decision"]["payable"]
        if action == "approve"
        else "0.00",
    }
    case["review"] = entry
    path.write_text(json.dumps(case, indent=2, ensure_ascii=False), encoding="utf-8")
    with (_cases_dir / "audit.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"packet_id": packet_id, **entry}) + "\n")
    return json.dumps({"status": "recorded", "packet_id": packet_id, **entry})


@mcp.tool()
def get_case(packet_id: str) -> str:
    """Retrieve the full case record for a previously assessed claim."""
    if _cases_dir is None:
        return json.dumps({"error": "Server not configured"})
    path = _cases_dir / packet_id / "case.json"
    if not path.exists():
        return json.dumps({"error": f"No case found for {packet_id}"})
    return path.read_text(encoding="utf-8")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="OpenAdjuster MCP server")
    parser.add_argument("--split-dir", type=Path, required=True)
    parser.add_argument("--cases", type=Path, default=Path("cases"))
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
    )
    parser.add_argument("--port", type=int, default=8078)
    args = parser.parse_args()

    configure(args.split_dir, args.cases, args.model)

    if args.transport == "sse":
        import uvicorn

        uvicorn.run(mcp.sse_app(), host="127.0.0.1", port=args.port)
    else:
        import asyncio

        asyncio.run(mcp.run_stdio_async())


if __name__ == "__main__":
    main()
