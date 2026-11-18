/**
 * CAT-WO-02 item 8 (R-023): edit labels from the app, as the signed-in user.
 * Writes ONLY: Allegis Document (kind, entity, portco, fiscal year, period, effective date), Parties (issuing,
 * receiving: once published), Status & Execution (stage, executed date, status, issued date) and Catalog Review
 * (Confirmed + Reviewed by). Handling (tier, LP PII) is never written: a Handling key in a request is refused.
 */
import { hasField, SCHEMA } from "./labels";
import { FILE_ID_RE, modifyLabels, type FetchLike } from "./google";

export const EDIT_FIELDS = ["kind", "entities", "portcos", "fiscal_year", "period", "effective_date", "issuing_entity",
  "receiving_entities", "status", "issued_date", "stage", "executed_date"] as const;
export type EditField = (typeof EDIT_FIELDS)[number];
/** Bulk: "Set kind / entity / fiscal year / status…" (item 8) */
export const BULK_FIELDS: EditField[] = ["kind", "entities", "fiscal_year", "status"];
export const BULK_CAP = 500;
/** Anything about Handling is refused outright, whatever the spelling. */
const HANDLING_KEYS = /^(tier|handling|contains|pii|pii_lp|lp_pii|secret|restricted)$/i;

// field -> [label key, schema field key, kind]
const MAP: Record<EditField, [string, string, "one" | "many" | "int" | "date"]> = {
  kind: ["doc", "kind", "one"], entities: ["doc", "entity", "many"], portcos: ["doc", "portco", "many"],
  fiscal_year: ["doc", "fiscal_year", "int"], period: ["doc", "period", "one"], effective_date: ["doc", "effective_date", "date"],
  issuing_entity: ["parties", "issuing_entity", "one"], receiving_entities: ["parties", "receiving_entities", "many"],
  status: ["exec", "status", "one"], issued_date: ["exec", "issued_date", "date"],
  stage: ["exec", "stage", "one"], executed_date: ["exec", "executed_date", "date"],
};
export const LABELS_THE_APP_MAY_WRITE = ["doc", "parties", "exec", "review"] as const;

export type EditValue = string | number | string[] | null;
export type EditSet = Partial<Record<EditField, EditValue>>;
type L = { label_id: string; fields: Record<string, { field_id: string; choices?: Record<string, string> }> };
const labelOf = (k: string) => (SCHEMA as unknown as Record<string, L | undefined>)[k];

const ISO = /^\d{4}-\d{2}-\d{2}$/;
const isDate = (s: string) => ISO.test(s) && !isNaN(Date.parse(s));

export function validateEdit(x: unknown, opts: { bulk?: boolean } = {}): { ok: true; value: EditSet } | { ok: false; reason: string } {
  if (!x || typeof x !== "object" || Array.isArray(x)) return { ok: false, reason: "set_must_be_an_object" };
  const keys = Object.keys(x as object);
  if (!keys.length) return { ok: false, reason: "nothing_to_change" };
  for (const k of keys) if (HANDLING_KEYS.test(k)) return { ok: false, reason: "handling_not_editable" };
  const out: EditSet = {};
  for (const k of keys) {
    if (!(EDIT_FIELDS as readonly string[]).includes(k)) return { ok: false, reason: `field_not_editable:${k.replace(/[^a-z_]/gi, "").slice(0, 40)}` };
    const f = k as EditField;
    if (opts.bulk && !BULK_FIELDS.includes(f)) return { ok: false, reason: `not_a_bulk_field:${f}` };
    const [lk, fk, kind] = MAP[f];
    if (!hasField(lk, fk)) return { ok: false, reason: `label_not_published:${lk}.${fk}` };
    const v = (x as Record<string, unknown>)[k];
    if (v === null || v === "" || (Array.isArray(v) && !v.length)) { out[f] = null; continue; } // unset
    const choices = labelOf(lk)!.fields[fk].choices;
    if (kind === "one") {
      if (typeof v !== "string" || !choices || !(v in choices)) return { ok: false, reason: `bad_value:${f}` };
      out[f] = v;
    } else if (kind === "many") {
      if (!Array.isArray(v) || v.length > 30 || !v.every((c) => typeof c === "string" && !!choices && c in choices)) return { ok: false, reason: `bad_value:${f}` };
      out[f] = [...new Set(v as string[])].sort();
    } else if (kind === "int") {
      const n = Number(v);
      if (!Number.isInteger(n) || n < 1990 || n > 2100) return { ok: false, reason: `bad_value:${f}` };
      out[f] = n;
    } else {
      if (typeof v !== "string" || !isDate(v)) return { ok: false, reason: `bad_value:${f}` };
      out[f] = v;
    }
  }
  if (out.executed_date && out.stage !== "fully_executed") return { ok: false, reason: "executed_date_needs_fully_executed" };
  return { ok: true, value: out };
}

function ymd(s: string) { const [year, month, day] = s.split("-").map(Number); return { year, month, day }; }

/** labelModifications for an edit + Catalog Review = Confirmed, Reviewed by = the user. Never Handling. */
export function buildEditMods(e: EditSet, reviewerEmail: string): { labelModifications: unknown[]; labels: string[] } {
  const per: Record<string, unknown[]> = {};
  for (const [f, v] of Object.entries(e) as [EditField, EditValue][]) {
    const [lk, fk, kind] = MAP[f];
    const F = labelOf(lk)!.fields[fk];
    let m: unknown;
    if (v === null) m = { fieldId: F.field_id, unsetValues: true };
    else if (kind === "one") m = { fieldId: F.field_id, setSelectionValues: [F.choices![v as string]] };
    else if (kind === "many") m = { fieldId: F.field_id, setSelectionValues: (v as string[]).map((c) => F.choices![c]) };
    else if (kind === "int") m = { fieldId: F.field_id, setIntegerValues: [String(v)] };
    else m = { fieldId: F.field_id, setDateValues: [ymd(v as string)] };
    (per[lk] ??= []).push(m);
  }
  // a stage other than fully executed clears a stale executed date (same rule as the Review write)
  if (e.stage && e.stage !== "fully_executed" && !("executed_date" in e)) (per.exec ??= []).push({ fieldId: labelOf("exec")!.fields.executed_date.field_id, unsetValues: true });
  const R = labelOf("review")!;
  per.review = [
    { fieldId: R.fields.status.field_id, setSelectionValues: [R.fields.status.choices!.confirmed] },
    { fieldId: R.fields.reviewed_by.field_id, setUserValues: [reviewerEmail] },
  ];
  const labels = (LABELS_THE_APP_MAY_WRITE as readonly string[]).filter((k) => per[k]?.length);
  return { labels, labelModifications: labels.map((k) => ({ labelId: labelOf(k)!.label_id, fieldModifications: per[k] })) };
}

/** Codes-only record of an edit for app.review_event.edits. */
export function editRecord(e: EditSet): Record<string, EditValue> {
  return Object.fromEntries(Object.entries(e));
}

export interface BulkResult { done: string[]; skippedNoAccess: string[]; failed: { file_id: string; drive_status: number }[] }

/**
 * Writes the same edit on many files: batches of 25 (5 at a time), retry on 429 / 5xx / rate-limit 403 with
 * backoff (as labels_sync.py), a pause between batches. A 403/404 is "no access" (skipped), never retried.
 */
export async function bulkWrite(accessToken: string, ids: string[], mods: unknown[], opts: { fetch?: FetchLike; sleep?: (ms: number) => Promise<void>; batch?: number; parallel?: number } = {}): Promise<BulkResult> {
  const sleep = opts.sleep ?? ((ms: number) => new Promise((r) => setTimeout(r, ms)));
  const BATCH = opts.batch ?? 25, PAR = opts.parallel ?? 5;
  const out: BulkResult = { done: [], skippedNoAccess: [], failed: [] };
  let queue = ids.filter((id) => FILE_ID_RE.test(id));
  const tries = new Map<string, number>();
  while (queue.length) {
    const chunk = queue.slice(0, BATCH);
    queue = queue.slice(BATCH);
    const retry: string[] = [];
    for (let i = 0; i < chunk.length; i += PAR) {
      await Promise.all(chunk.slice(i, i + PAR).map(async (id) => {
        const r = await modifyLabels(accessToken, id, mods, opts.fetch).catch(() => ({ status: 0, body: null }));
        if (r.status === 200) { out.done.push(id); return; }
        const reason = String(((r.body?.error as { errors?: { reason?: string }[] } | undefined)?.errors?.[0]?.reason) ?? "").toLowerCase();
        const transient = r.status === 0 || r.status === 429 || r.status >= 500 || (r.status === 403 && /rate|limit/.test(reason));
        if (transient && (tries.get(id) ?? 0) < 4) { tries.set(id, (tries.get(id) ?? 0) + 1); retry.push(id); return; }
        if (r.status === 403 || r.status === 404) out.skippedNoAccess.push(id);
        else out.failed.push({ file_id: id, drive_status: r.status });
      }));
    }
    if (retry.length) { queue = [...retry, ...queue]; await sleep(5000 + Math.random() * 5000); }
    else if (queue.length) await sleep(1000);
  }
  return out;
}
