export type Box = [number, number, number, number];

export interface Evidence {
  doc_id: string;
  box: Box;
}

export interface Clause {
  id: string;
  title: string;
  text: string;
}

export interface Check {
  label: string;
  ok: boolean;
  clause: Clause;
  evidence: Evidence[];
}

export interface Item {
  description: string;
  amount: string;
  category: string;
  covered: boolean;
  clause: Clause | null;
  evidence: Evidence | null;
}

export interface Field {
  name: string;
  value: string;
  box: Box | null;
}

export interface Doc {
  doc_id: string;
  type: string;
  label: string;
  file: string;
  width: number;
  height: number;
  fields: Field[];
}

export interface Review {
  at: string;
  reviewer: string;
  action: "approve" | "override" | "request_info";
  note: string;
  recommended: string;
  recommended_payable: string;
  final_payable: string;
}

export interface Case {
  packet_id: string;
  member: { member_id: string; plan: string; currency: string; employer: string; patient: string };
  submitted_on: string;
  decision: {
    decision: Decision;
    payable: string;
    claimed: string;
    currency: string;
    route: string;
    confidence: number;
    reasons: { code: string; clause: Clause | null }[];
  };
  checks: Check[];
  items: Item[];
  injection: { text: string; doc_id: string; box: Box }[];
  documents: Doc[];
  run: { model: string; seconds: number; cost_usd: number; version: string; assessed_at: string };
  review: Review | null;
  benchmark?: { decision: string; payable: string; kind: string; variant: string };
}

export type Decision = "APPROVE" | "PARTIAL" | "REJECT" | "REQUEST_INFO" | "ESCALATE";

export interface CaseSummary {
  packet_id: string;
  patient: string;
  decision: Decision;
  payable: string;
  claimed: string;
  currency: string;
  flags: number;
  injection: boolean;
  variant: string | null;
}
