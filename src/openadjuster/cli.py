"""Command line: run OpenAdjuster over a ClaimDocBench split and write predictions."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from openadjuster.assess import Registry, assess_packet, to_prediction
from openadjuster.llm import DEFAULT_MODEL, LocalModel


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="openadjuster")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="assess every packet in a split")
    run.add_argument("--split-dir", type=Path, required=True)
    run.add_argument("--out", type=Path, required=True)
    run.add_argument("--model", default=DEFAULT_MODEL)
    run.add_argument("--subset", choices=["all", "smoke"], default="all")
    run.add_argument("--use-image", action="store_true", help="also send page images")

    exp = sub.add_parser("export", help="assess packets and write case records for the console")
    exp.add_argument("--split-dir", type=Path, required=True)
    exp.add_argument("--out", type=Path, required=True)
    exp.add_argument("--model", default=DEFAULT_MODEL)
    exp.add_argument("--packets", nargs="+", required=True)
    exp.add_argument(
        "--with-benchmark",
        action="store_true",
        help="include the benchmark's expected answer (for the public demo)",
    )

    srv = sub.add_parser("serve", help="run the review console locally")
    srv.add_argument("--cases", type=Path, default=Path("cases"))
    srv.add_argument("--split-dir", type=Path, help="ClaimDocBench split to assess packets from")
    srv.add_argument("--model", default=DEFAULT_MODEL)
    srv.add_argument("--port", type=int, default=8077)
    args = parser.parse_args(argv)

    if args.command == "export":
        return _export(args)
    if args.command == "serve":
        from openadjuster.server import serve

        serve(args.cases, args.split_dir, args.model, args.port)
        return 0

    index = json.loads((args.split_dir / "index.json").read_text(encoding="utf-8"))
    ids = index["smoke"] if args.subset == "smoke" else [*index["packets"], *index.get("twins", [])]
    done: set[str] = set()
    if args.out.exists():
        done = {json.loads(x)["packet_id"] for x in args.out.read_text().splitlines() if x}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    registry = Registry.load(args.split_dir / "context")
    model = LocalModel(args.model)
    todo = [p for p in ids if p not in done]
    for n, pid in enumerate(todo, 1):
        try:
            pred = to_prediction(
                assess_packet(args.split_dir / "packets" / pid, registry, model, args.use_image),
                model,
            )
        except Exception as exc:  # keep long runs alive; scored as wrong
            pred = {
                "packet_id": pid,
                "decision": "MISSING",
                "payable_amount": None,
                "error": f"{type(exc).__name__}: {exc}"[:300],
            }
        with args.out.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(pred, ensure_ascii=False) + "\n")
        print(
            f"[{n}/{len(todo)}] {pid} {pred['decision']} {pred.get('payable_amount')} "
            f"{pred.get('latency_s')}s",
            flush=True,
        )
    return 0


def _export(args: argparse.Namespace) -> int:
    from openadjuster.case import build_case, write_case, write_index

    registry = Registry.load(args.split_dir / "context")
    model = LocalModel(args.model)
    for pid in args.packets:
        pdir = args.split_dir / "packets" / pid
        gold = None
        if args.with_benchmark:
            gold = json.loads((args.split_dir / "gold" / f"{pid}.json").read_text("utf-8"))
        case = build_case(assess_packet(pdir, registry, model), pdir, model.model, gold)
        write_case(case, pdir, args.out)
        print(f"{pid} {case['decision']['decision']} {case['decision']['payable']}", flush=True)
    write_index(args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
