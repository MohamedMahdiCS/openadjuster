import type { Decision } from "./types";

export function money(amount: string, currency: string): string {
  const symbol = currency === "SGD" ? "S$" : currency === "MYR" ? "RM" : "";
  const n = Number(amount);
  return `${symbol}${Number.isFinite(n) ? n.toFixed(2) : amount}`;
}

export const DECISION_LABEL: Record<Decision, string> = {
  APPROVE: "Approve in full",
  PARTIAL: "Pay in part",
  REJECT: "Reject",
  REQUEST_INFO: "Request documents",
  ESCALATE: "Fraud review",
};

export const DECISION_TONE: Record<Decision, "good" | "warn" | "bad" | "info"> = {
  APPROVE: "good",
  PARTIAL: "good",
  REJECT: "bad",
  REQUEST_INFO: "info",
  ESCALATE: "warn",
};

export const REASON_TEXT: Record<string, string> = {
  PERSON_NOT_COVERED: "Patient isn't covered",
  OUTSIDE_COVER_PERIOD: "Treatment outside the cover period",
  LATE_SUBMISSION: "Submitted after the deadline",
  UNLICENSED_CLINIC: "Clinic isn't licensed",
  MISSING_CLAIM_FORM: "Claim form missing",
  MISSING_RECEIPT: "Receipt missing",
  MISSING_REFERRAL_LETTER: "Referral letter missing",
  DOCUMENT_ILLEGIBLE: "A required document can't be read",
  NO_REFERRAL: "Specialist visit without a GP referral",
  WAITING_PERIOD: "Pre-existing condition in waiting period",
  EXCLUDED_ITEM: "Some items aren't covered",
  ALL_ITEMS_EXCLUDED: "None of the items are covered",
  GP_VISIT_CAP: "GP visit limit applied",
  SPECIALIST_VISIT_CAP: "Specialist visit limit applied",
  COPAY: "Co-payment applied",
  ANNUAL_LIMIT_APPLIED: "Annual limit reached part-way",
  ANNUAL_LIMIT_REACHED: "Annual limit already used",
  INTEGRITY_REVIEW: "Documents need fraud review",
};

export const CATEGORY_TEXT: Record<string, string> = {
  consultation: "Consultation",
  medication: "Medication",
  procedure: "Procedure",
  lab_test: "Lab test",
  supplement: "Supplement",
  cosmetic: "Cosmetic",
  fertility: "Fertility",
  dental: "Dental",
  health_screening: "Health screening",
};
