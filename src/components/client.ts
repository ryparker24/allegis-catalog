"use client";
import { display, type VocabList } from "@/lib/vocab";

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(path, { ...init, headers: { "content-type": "application/json", ...(init?.headers ?? {}) }, credentials: "same-origin" });
  if (r.status === 401) {
    window.location.href = `/api/auth/login?next=${encodeURIComponent(window.location.pathname)}`;
    throw new Error("signin_required");
  }
  const body = (await r.json().catch(() => ({}))) as T & { error?: string; login?: string };
  if (r.status === 409 && body.error === "consent_required" && body.login) {
    window.location.href = body.login; // incremental consent: drive.metadata on first Review write
    throw new Error("consent_required");
  }
  if (!r.ok) throw Object.assign(new Error(body.error || `HTTP ${r.status}`), { body, status: r.status });
  return body;
}

export interface Row {
  file_id: string;
  document_id: string | number | null;
  name: string;
  web_view_link: string;
  kind: string | null;
  entities: string[];
  portcos: string[];
  fiscal_year: number | null;
  period: string | null;
  stage: string | null;
  executed_date: string | null;
  workstream: string | null;
  issuer: string | null;
  tier: string | null;
  review_status: string | null;
  signed_date: string | null;
  effective_date: string | null;
  is_primary: boolean | null;
  modified_time: string | null;
  file_type_family: string | null;
  queue_reason: string | null;
  signals: string[] | null;
  confidence: string | null;
  stage_suggested: string | null;
  changed: string[];
  catalog: Record<string, unknown>;
}
export interface NotShown { noAccess: number; checkFailed: number; total: number }

const LIST_OF: Record<string, VocabList | undefined> = { kind: "kind", period: "period", stage: "stage", tier: "tier", workstream: "workstream", issuer: "issuer" };
export function show(col: string, v: unknown): string {
  if (v == null || v === "") return "";
  if (Array.isArray(v)) return v.join(", ");
  const list = LIST_OF[col];
  if (list) return display(list, String(v));
  if (typeof v === "boolean") return v ? "yes" : "";
  if (col.endsWith("_time") || col.endsWith("_date")) return String(v).slice(0, 10);
  return String(v);
}

export function previewUrl(fileId: string): string {
  return `https://drive.google.com/file/d/${encodeURIComponent(fileId)}/preview`;
}
