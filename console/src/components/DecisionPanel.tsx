import { DECISION_LABEL, DECISION_TONE, REASON_TEXT, money } from "../format";
import type { Case } from "../types";
import { Icon } from "./Icon";

export function DecisionPanel({ data }: { data: Case }) {
  const d = data.decision;
  const tone = DECISION_TONE[d.decision];
  const pct = Math.round(d.confidence * 100);
  const bench = data.benchmark;
  const matches = bench && bench.decision === d.decision && Number(bench.payable) === Number(d.payable);

  return (
    <section className="panel decision">
      <div className="label">Recommended decision</div>
      <div className={`verdict ${tone}`}>
        <span>{DECISION_LABEL[d.decision]}</span>
        <strong>{money(d.payable, d.currency)}</strong>
      </div>
      <div className="sub">
        Claimed {money(d.claimed, d.currency)} · {d.route}
      </div>
      <div className="confidence" title="How sure OpenAdjuster is, from the quality of its evidence">
        <span>Confidence</span>
        <div className="bar"><div style={{ width: `${pct}%` }} /></div>
        <span>{pct}%</span>
      </div>
      {d.reasons.length > 0 && (
        <ul className="reasons">
          {d.reasons.map((r) => (
            <li key={r.code}>
              {REASON_TEXT[r.code] ?? r.code}
              {r.clause && <span className="clause" title={r.clause.text}>{r.clause.id}</span>}
            </li>
          ))}
        </ul>
      )}
      {bench && (
        <div className={`benchmark ${matches ? "ok" : "miss"}`}>
          <Icon name={matches ? "check" : "x"} />
          Benchmark answer: {DECISION_LABEL[bench.decision as keyof typeof DECISION_LABEL]}{" "}
          {money(bench.payable, d.currency)}
          <span className="muted"> · scenario: {bench.variant.replaceAll("_", " ")}</span>
        </div>
      )}
    </section>
  );
}
