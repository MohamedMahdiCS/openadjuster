import type { Case, CaseSummary, Review } from "./types";

// The same build runs as a static demo (GitHub Pages) and against the local server.
// Case files are always read from ./data; only the live server has /api.

export interface Health {
  mode: "live" | "demo";
  model?: string;
  can_assess?: boolean;
}

export async function health(): Promise<Health> {
  try {
    const res = await fetch("api/health");
    if (res.ok && res.headers.get("content-type")?.includes("json")) return await res.json();
  } catch {
    // no server: static demo
  }
  return { mode: "demo" };
}

async function json<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return res.json() as Promise<T>;
}

export const listCases = () => json<CaseSummary[]>(`data/index.json?t=${Date.now()}`);
export const getCase = (id: string) => json<Case>(`data/${id}/case.json?t=${Date.now()}`);
export const fileUrl = (id: string, file: string) => `data/${id}/${file}`;
export const listPackets = () => json<string[]>("api/packets");

export const assess = (packet_id: string) =>
  json<Case>("api/assess", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ packet_id }),
  });

export const submitReview = (id: string, body: Pick<Review, "action" | "note"> & { payable?: string }) =>
  json<Case>(`api/cases/${id}/review`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
