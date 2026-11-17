import schema from "./labels_schema.json";

type FieldDef = { field_id: string; type: string; choices?: Record<string, string> };
type LabelDef = { label_id: string; title: string; fields: Record<string, FieldDef> };
const S = schema as unknown as Record<"doc" | "exec" | "handling" | "review", LabelDef>;

export const LABEL_IDS = {
  doc: S.doc.label_id,
  exec: S.exec.label_id,
  handling: S.handling.label_id,
  review: S.review.label_id,
};
/** includeLabels for files.get: all four catalog labels. */
export const INCLUDE_LABELS = Object.values(LABEL_IDS).join(",");

const choiceToCode = new Map<string, string>(); // `${labelKey}.${fieldKey}.${choiceId}` -> code
for (const [lk, L] of Object.entries(S)) for (const [fk, F] of Object.entries(L.fields)) for (const [code, cid] of Object.entries(F.choices ?? {})) choiceToCode.set(`${lk}.${fk}.${cid}`, code);
const fieldKey = new Map<string, [string, string]>(); // `${labelId}.${fieldId}` -> [labelKey, fieldKey]
for (const [lk, L] of Object.entries(S)) for (const [fk, F] of Object.entries(L.fields)) fieldKey.set(`${L.label_id}.${F.field_id}`, [lk, fk]);
const labelKeyById = new Map(Object.entries(S).map(([k, L]) => [L.label_id, k]));

/** Live label values decoded to catalog codes. */
export interface LiveValues {
  has_doc_label: boolean;
  kind: string | null;
  entities: string[];
  portcos: string[];
  fiscal_year: number | null;
  period: string | null;
  workstream: string | null;
  issuer: string | null;
  stage: string | null;
  executed_date: string | null;
  tier: string | null;
  contains: string[];
  review_status: string | null;
  review_note: string | null;
}

type LabelField = { selection?: string[]; integer?: string[]; text?: string[]; dateString?: string[]; user?: { emailAddress?: string }[] };
type LabelInfo = { labels?: { id: string; fields?: Record<string, LabelField> }[] } | null | undefined;

export function decodeLabels(info: LabelInfo): LiveValues {
  const v: LiveValues = { has_doc_label: false, kind: null, entities: [], portcos: [], fiscal_year: null, period: null, workstream: null, issuer: null, stage: null, executed_date: null, tier: null, contains: [], review_status: null, review_note: null };
  for (const L of info?.labels ?? []) {
    const lk = labelKeyById.get(L.id);
    if (!lk) continue;
    if (lk === "doc") v.has_doc_label = true;
    for (const [fid, fv] of Object.entries(L.fields ?? {})) {
      const k = fieldKey.get(`${L.id}.${fid}`);
      if (!k) continue;
      const [, fk] = k;
      const sel = (fv.selection ?? []).map((c) => choiceToCode.get(`${lk}.${fk}.${c}`) ?? `?${c}`);
      const key = `${lk}.${fk}`;
      switch (key) {
        case "doc.kind": v.kind = sel[0] ?? null; break;
        case "doc.entity": v.entities = sel.sort(); break;
        case "doc.portco": v.portcos = sel.sort(); break;
        case "doc.fiscal_year": v.fiscal_year = fv.integer?.[0] != null ? Number(fv.integer[0]) : null; break;
        case "doc.period": v.period = sel[0] ?? null; break;
        case "doc.workstream": v.workstream = sel[0] ?? null; break;
        case "doc.issuer": v.issuer = sel[0] ?? null; break;
        case "exec.stage": v.stage = sel[0] ?? null; break;
        case "exec.executed_date": v.executed_date = fv.dateString?.[0] ?? null; break;
        case "handling.tier": v.tier = sel[0] ?? null; break;
        case "handling.contains": v.contains = sel.sort(); break;
        case "review.status": v.review_status = sel[0] ?? null; break;
        case "review.note": v.review_note = fv.text?.[0] ?? null; break;
      }
    }
  }
  return v;
}

/** Fields compared DB vs live; differing ones get the "changed in Drive" marker. */
export const COMPARED = ["kind", "entities", "portcos", "fiscal_year", "period", "workstream", "issuer", "stage", "tier"] as const;
export type Compared = (typeof COMPARED)[number];

export function changedFields(db: Partial<Record<Compared, unknown>>, live: LiveValues): Compared[] {
  const norm = (x: unknown) => (Array.isArray(x) ? [...x].map(String).sort().join("|") : x == null || x === "" ? "" : String(x));
  const out: Compared[] = [];
  for (const k of COMPARED) {
    let dbv = db[k];
    // the labelling run writes no Execution label for stage "unknown" / not-executable documents
    if (k === "stage" && (dbv === "unknown" || dbv === "n_a")) dbv = live.stage === "n_a" ? "n_a" : null;
    if (norm(dbv) !== norm(live[k as keyof LiveValues])) out.push(k);
  }
  return out;
}

// ------------------------------------------------------------------ Review-queue write (Execution + Catalog Review ONLY)
export const STAGES = ["draft", "final_unexecuted", "partially_executed", "fully_executed", "n_a"] as const;
export interface ReviewInput {
  status: "confirmed" | "wrong";
  stage: (typeof STAGES)[number] | null;
  executedDate: string | null; // YYYY-MM-DD
  note: string | null;
  reviewerEmail: string;
}

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;
export function validateReview(x: unknown): { ok: true; value: Omit<ReviewInput, "reviewerEmail"> } | { ok: false; reason: string } {
  const o = (x ?? {}) as Record<string, unknown>;
  if (o.status !== "confirmed" && o.status !== "wrong") return { ok: false, reason: "status" };
  const stage = o.stage == null || o.stage === "" ? null : String(o.stage);
  if (stage !== null && !(STAGES as readonly string[]).includes(stage)) return { ok: false, reason: "stage" };
  const executedDate = o.executed_date == null || o.executed_date === "" ? null : String(o.executed_date);
  if (executedDate !== null && (!ISO_DATE.test(executedDate) || isNaN(Date.parse(executedDate)))) return { ok: false, reason: "executed_date" };
  if (executedDate !== null && stage !== "fully_executed") return { ok: false, reason: "executed_date_needs_fully_executed" };
  const note = o.note == null || o.note === "" ? null : String(o.note);
  if (note !== null && note.length > 2000) return { ok: false, reason: "note_too_long" };
  return { ok: true, value: { status: o.status, stage: stage as ReviewInput["stage"], executedDate, note } };
}

function dateValue(s: string) {
  const [year, month, day] = s.split("-").map(Number);
  return { year, month, day };
}

/** Builds files.modifyLabels labelModifications. Touches ONLY the Execution and Catalog Review labels. */
export function buildReviewMods(r: ReviewInput): { labelModifications: unknown[]; labels: ("exec" | "review")[] } {
  const E = S.exec.fields, R = S.review.fields;
  const mods: unknown[] = [];
  const labels: ("exec" | "review")[] = [];
  if (r.stage) {
    const fm: unknown[] = [{ fieldId: E.stage.field_id, setSelectionValues: [E.stage.choices![r.stage]] }];
    if (r.executedDate) fm.push({ fieldId: E.executed_date.field_id, setDateValues: [dateValue(r.executedDate)] });
    else if (r.stage !== "fully_executed") fm.push({ fieldId: E.executed_date.field_id, unsetValues: true });
    // (fully executed with no date given: an executed date already on the label is left as it is)
    mods.push({ labelId: S.exec.label_id, fieldModifications: fm });
    labels.push("exec");
  }
  mods.push({
    labelId: S.review.label_id,
    fieldModifications: [
      { fieldId: R.status.field_id, setSelectionValues: [R.status.choices![r.status]] },
      { fieldId: R.reviewed_by.field_id, setUserValues: [r.reviewerEmail] },
      r.note ? { fieldId: R.note.field_id, setTextValues: [r.note] } : { fieldId: R.note.field_id, unsetValues: true },
    ],
  });
  labels.push("review");
  return { labelModifications: mods, labels };
}
