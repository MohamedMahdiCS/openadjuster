import { useState } from "react";
import { submitReview } from "../api";
import { money } from "../format";
import type { Case, Review } from "../types";
import { Icon } from "./Icon";

interface Props {
  data: Case;
  live: boolean;
  onReviewed: (c: Case) => void;
}

export function ReviewBar({ data, live, onReviewed }: Props) {
  const [mode, setMode] = useState<"idle" | "override">("idle");
  const [amount, setAmount] = useState(data.decision.payable);
  const [note, setNote] = useState("");
  const [error, setError] = useState("");
  const cur = data.decision.currency;

  async function send(action: Review["action"]) {
    setError("");
    if (action === "override" && !(Number(amount) >= 0)) {
      setError("Enter the amount to pay.");
      return;
    }
    if (action === "override" && !note.trim()) {
      setError("Add a short reason for the override.");
      return;
    }
    const payable = action === "override" ? Number(amount).toFixed(2) : undefined;
    if (!live) {
      // Static demo: show the outcome without saving anything.
      onReviewed({ ...data, review: {
        at: new Date().toISOString(), reviewer: "you", action, note,
        recommended: data.decision.decision, recommended_payable: data.decision.payable,
        final_payable: payable ?? (action === "approve" ? data.decision.payable : "0.00"),
      } });
      return;
    }
    try {
      onReviewed(await submitReview(data.packet_id, { action, note, payable }));
    } catch (e) {
      setError(String(e));
    }
  }

  // "approve" means accepting the recommendation, whatever it is.
  const accept: Record<string, string> = {
    APPROVE: `Approve ${money(data.decision.payable, cur)}`,
    PARTIAL: `Approve ${money(data.decision.payable, cur)}`,
    REJECT: "Confirm rejection",
    REQUEST_INFO: "Send document request",
    ESCALATE: "Send to fraud review",
  };
  const done: Record<string, string> = {
    APPROVE: "Approved", PARTIAL: "Approved", REJECT: "Rejected",
    REQUEST_INFO: "Documents requested", ESCALATE: "Sent to fraud review",
  };

  if (data.review) {
    const r = data.review;
    const verb = r.action === "approve" ? done[data.decision.decision]
      : r.action === "override" ? "Overridden" : "Sent back for documents";
    return (
      <section className="panel review done">
        <Icon name="check" /> {verb} · pays {money(r.final_payable, cur)} · by {r.reviewer}
        {r.note && <span className="muted"> · “{r.note}”</span>}
        {!live && <span className="muted"> · demo, not saved</span>}
      </section>
    );
  }

  return (
    <section className="panel review">
      <div className="who"><Icon name="lock" /> Nothing is paid until a person approves.</div>
      {mode === "override" ? (
        <div className="override">
          <label>Amount to pay ({cur})
            <input inputMode="decimal" value={amount} onChange={(e) => { setAmount(e.target.value); setError(""); }} />
          </label>
          <label>Reason
            <input value={note} placeholder="Receipt confirmed with clinic by phone"
              onChange={(e) => { setNote(e.target.value); setError(""); }} />
          </label>
          <div className="buttons">
            <button className="primary" onClick={() => send("override")}>Save override</button>
            <button onClick={() => setMode("idle")}>Cancel</button>
          </div>
        </div>
      ) : (
        <div className="buttons">
          <button className="primary" onClick={() => send("approve")}>
            {accept[data.decision.decision]}
          </button>
          <button onClick={() => setMode("override")}>Override</button>
          {data.decision.decision !== "REQUEST_INFO" && (
            <button onClick={() => send("request_info")}>Request documents</button>
          )}
        </div>
      )}
      {error && <p className="error">{error}</p>}
    </section>
  );
}
