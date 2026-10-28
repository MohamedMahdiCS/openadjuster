import { useEffect, useState } from "react";
import { assess, getCase, health, listCases, listPackets, type Health } from "./api";
import { Checks, Items } from "./components/Checks";
import { DecisionPanel } from "./components/DecisionPanel";
import { DocumentViewer } from "./components/DocumentViewer";
import { Icon } from "./components/Icon";
import { ReviewBar } from "./components/ReviewBar";
import { DECISION_LABEL, DECISION_TONE, money } from "./format";
import type { Case, CaseSummary, Evidence } from "./types";

export function App() {
  const [env, setEnv] = useState<Health>({ mode: "demo" });
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [selected, setSelected] = useState<string>("");
  const [data, setData] = useState<Case | null>(null);
  const [activeDoc, setActiveDoc] = useState("");
  const [highlights, setHighlights] = useState<Evidence[]>([]);
  const [packets, setPackets] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    health().then((h) => {
      setEnv(h);
      if (h.mode === "live" && h.can_assess) listPackets().then(setPackets).catch(() => {});
    });
    listCases().then((rows) => {
      setCases(rows);
      const fromHash = window.location.hash.slice(1);
      setSelected(rows.some((r) => r.packet_id === fromHash) ? fromHash : rows[0]?.packet_id ?? "");
    }).catch(() => setError("No cases found. Export some with `openadjuster export`."));
  }, []);

  useEffect(() => {
    if (!selected) return;
    window.history.replaceState(null, "", `#${selected}`);
    getCase(selected).then((c) => {
      setData(c);
      setHighlights([]);
      setActiveDoc((c.documents.find((d) => d.type === "receipt") ?? c.documents[0])?.doc_id ?? "");
    });
  }, [selected]);

  function focus(evidence: Evidence[]) {
    setHighlights(evidence);
    if (evidence.length && !evidence.some((e) => e.doc_id === activeDoc)) setActiveDoc(evidence[0].doc_id);
  }

  async function runAssessment(packetId: string) {
    setBusy(true);
    setError("");
    try {
      const c = await assess(packetId);
      setCases(await listCases());
      setPackets((p) => p.filter((x) => x !== packetId));
      setSelected(c.packet_id);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  const live = env.mode === "live";
  return (
    <div className="app">
      <header className="top">
        <div className="brand"><Icon name="shield" size={20} /> OpenAdjuster</div>
        <div className="env">
          <span className="pill"><Icon name="laptop" /> Runs on a laptop · {env.model ?? "bonsai-2:4b"} · $0 per claim</span>
          {!live && <span className="pill muted">Demo: recorded results on synthetic claims</span>}
        </div>
        <a className="repo" href="https://github.com/MohamedMahdiCS/openadjuster">GitHub</a>
      </header>

      <aside className="sidebar">
        {live && packets.length > 0 && (
          <div className="assess">
            <select disabled={busy} defaultValue="" onChange={(e) => e.target.value && runAssessment(e.target.value)}>
              <option value="" disabled>{busy ? "Assessing… (about 30 s)" : "Assess a new claim"}</option>
              {packets.slice(0, 50).map((p) => <option key={p} value={p}>{p}</option>)}
            </select>
          </div>
        )}
        <ul className="cases">
          {cases.map((c) => (
            <li key={c.packet_id}>
              <button className={c.packet_id === selected ? "on" : ""} onClick={() => setSelected(c.packet_id)}>
                <span className="who">{c.patient || c.packet_id}</span>
                <span className={`tag ${DECISION_TONE[c.decision]}`}>{DECISION_LABEL[c.decision]}</span>
                <span className="muted small">
                  {money(c.payable, c.currency)} of {money(c.claimed, c.currency)}
                  {c.injection && " · injection blocked"}
                </span>
              </button>
            </li>
          ))}
        </ul>
      </aside>

      <main className="main">
        {error && <p className="error">{error}</p>}
        {data && (
          <>
            <div className="claimhead">
              <h1>{data.member.patient || "Unknown patient"}</h1>
              <span className="muted">
                Claim {data.packet_id} · Member {data.member.member_id} · Plan {data.member.plan} ·
                Received {data.submitted_on} · Assessed in {data.run.seconds.toFixed(0)} s
              </span>
            </div>
            <div className="grid">
              <DocumentViewer data={data} activeDoc={activeDoc} onSelect={setActiveDoc} highlights={highlights} />
              <div className="side">
                <DecisionPanel data={data} />
                <ReviewBar key={data.packet_id} data={data} live={live} onReviewed={setData} />
                <Checks data={data} onFocus={focus} />
                <Items data={data} onFocus={focus} />
              </div>
            </div>
          </>
        )}
      </main>
    </div>
  );
}
