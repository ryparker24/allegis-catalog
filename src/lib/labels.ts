import schema from "./labels_schema.json";

type FieldDef = { field_id: string; type: string; choices?: Record<string, string> };
type LabelDef = { label_id: string; title: string; fields: Record<string, FieldDef> };
// "parties" (L11, R-021) and exec.status / exec.issued_date (R-022) exist only once published: optional here.
const S = schema as unknown as Record<"doc" | "exec" | "handling" | "review", LabelDef> & { parties?: LabelDef };
export const SCHEMA = S;
/** true when a label field exists on the published labels (labels_schema.json). */
export function hasField(label: string, field: string): boolean {
  const L = (S as Record<string, LabelDef | undefined>)[label];
  return !!L && !!L.fields[field];
}

export const LABEL_IDS: Record<string, string> = {
  doc: S.doc.label_id,
  exec: S.exec.label_id,
  handling: S.handling.label_id,
  review: S.review.label_id,
  ...(S.parties ? { parties: S.parties.label_id } : {}),
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
  status: string | null;
  issued_date: string | null;
  issuing_entity: string | null;
  receiving_entities: string[];
  /** R-026 (after publish): roster codes only (non-code text on the label is dropped), a staff account */
  subject_codes: string[];
  subject_person: string | null;
}

/** R-026: roster codes. Anything typed into Subject code(s) that is not a code is never shown, stored or written. */
export const SUBJECT_CODE_RE = /^(LP|GM|GPM)-[0-9]{2,6}(-[A-Z]{1,4})?$/;
export const STAFF_EMAIL_RE = /^[a-z0-9._%+-]{1,64}@allegiscapital\.com$/;
export function codesFromText(t: string | null | undefined): string[] {
  return [...new Set((t ?? "").split(/[,;\s]+/).map((x) => x.trim().toUpperCase()).filter((x) => SUBJECT_CODE_RE.test(x)))].sort();
}

type LabelField = { selection?: string[]; integer?: string[]; text?: string[]; dateString?: string[]; user?: { emailAddress?: string }[] };
type LabelInfo = { labels?: { id: string; fields?: Record<string, LabelField> }[] } | null | undefined;

export function decodeLabels(info: LabelInfo): LiveValues {
  const v: LiveValues = { has_doc_label: false, kind: null, entities: [], portcos: [], fiscal_year: null, period: null, workstream: null, issuer: null, stage: null, executed_date: null, tier: null, contains: [], review_status: null, review_note: null, status: null, issued_date: null, issuing_entity: null, receiving_entities: [], subject_codes: [], subject_person: null };
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
        case "exec.status": v.status = sel[0] ?? null; break;
        case "exec.issued_date": v.issued_date = fv.dateString?.[0] ?? null; break;
        case "parties.issuing_entity": v.issuing_entity = sel[0] ?? null; break;
        case "parties.receiving_entities": v.receiving_entities = sel.sort(); break;
        case "parties.subject_codes": v.subject_codes = codesFromText((fv.text ?? []).join(" ")); break;
        case "parties.subject_person": {
          const em = (fv.user?.[0]?.emailAddress ?? "").toLowerCase();
          v.subject_person = STAFF_EMAIL_RE.test(em) ? em : null;
          break;
        }
      }
    }
  }
  return v;
}

/** Fields compared DB vs live; differing ones get the "changed in Drive" marker. */
export const COMPARED = ["kind", "entities", "portcos", "fiscal_year", "period", "workstream", "issuer", "stage", "tier",
  // CAT-WO-03.1: Status & Execution, Parties and Subject too (Ryan: the "changed in Drive" marker never showed on Status)
  "status", "issued_date", "issuing_entity", "receiving_entities", "subject_codes", "subject_person"] as const;
export type Compared = (typeof COMPARED)[number];
/** label + field each later-published value lives on: compared only once that field is published */
const COMPARED_FIELD: Partial<Record<Compared, [string, string]>> = {
  status: ["exec", "status"], issued_date: ["exec", "issued_date"], issuing_entity: ["parties", "issuing_entity"],
  receiving_entities: ["parties", "receiving_entities"], subject_codes: ["parties", "subject_codes"], subject_person: ["parties", "subject_person"],
};

/** one comparable string: arrays sorted, dates as YYYY-MM-DD (the DB driver may give a Date), empty = "" */
function normCmp(x: unknown): string {
  if (Array.isArray(x)) return [...x].map(String).sort().join("|");
  if (x == null || x === "") return "";
  if (x instanceof Date) return isNaN(x.getTime()) ? "" : x.toISOString().slice(0, 10);
  const s = String(x);
  return /^\d{4}-\d{2}-\d{2}([T ]|$)/.test(s) ? s.slice(0, 10) : s;
}

export function changedFields(db: Partial<Record<Compared, unknown>>, live: LiveValues): Compared[] {
  const norm = normCmp;
  const out: Compared[] = [];
  for (const k of COMPARED) {
    const pub = COMPARED_FIELD[k];
    if (pub && (!live.has_doc_label || !hasField(pub[0], pub[1]))) continue;   // unlabelled / unpublished: nothing to compare
    if (pub && !(k in db)) continue;                                            // a view that doesn't select it (e.g. Review): no false marker
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
  /** R-022 Status (non-executable kinds), written on Status & Execution; refused until that field is published */
  docStatus?: (typeof DOC_STATUSES)[number] | null;
  reviewerEmail: string;
}
export const DOC_STATUSES = ["draft", "in_review", "final", "issued", "superseded"] as const;

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
  const docStatus = o.doc_status == null || o.doc_status === "" ? null : String(o.doc_status);
  if (docStatus !== null && !(DOC_STATUSES as readonly string[]).includes(docStatus)) return { ok: false, reason: "doc_status" };
  if (docStatus !== null && !hasField("exec", "status")) return { ok: false, reason: "label_not_published:exec.status" };
  if (docStatus !== null && stage !== null) return { ok: false, reason: "stage_or_status" };   // the form sends one, never both
  return { ok: true, value: { status: o.status, stage: stage as ReviewInput["stage"], executedDate, note, docStatus: docStatus as ReviewInput["docStatus"] } };
}

function dateValue(s: string) {
  const [year, month, day] = s.split("-").map(Number);
  return { year, month, day };
}

/** Builds files.modifyLabels labelModifications. Touches ONLY the (Status &) Execution and Catalog Review labels. */
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
  } else if (r.docStatus && hasField("exec", "status")) {
    const st = S.exec.fields.status;
    mods.push({ labelId: S.exec.label_id, fieldModifications: [{ fieldId: st.field_id, setSelectionValues: [st.choices![r.docStatus]] }] });
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
