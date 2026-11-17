/**
 * CAT-WO-02 item 3 · the Labels panel: every label, its fields in plain words, and every choice (code + meaning).
 * Built from labels_schema.json (the published Drive labels) plus the vocabularies and the ref tables (through
 * app.v_entity / app.v_portco). Read-only: nothing here writes.
 */
import schema from "./labels_schema.json";
import { VOCAB, type VocabList } from "./vocab";

type FieldDef = { field_id: string; type: string; choices?: Record<string, string> };
type LabelDef = { label_id: string; title: string; fields: Record<string, FieldDef> };
const S = schema as unknown as Record<string, LabelDef>;

/** Who sets a field. "review" = the Review queue writes it today; "part2" = machine-set until CAT-WO-02 Part 2 (R-023) makes it app-editable; "machine" = catalog rules / labelling run only; "never" = Handling. */
export type Editable = "review" | "machine" | "never" | "part2";
interface FieldMeta { title: string; about: string; editable: Editable; vocab?: VocabList | "entity" | "portco" }

export const LABEL_ABOUT: Record<string, string> = {
  doc: "What the document is and who it belongs to.",
  exec: "Signing progress for documents that need signatures.",
  handling: "How carefully the file must be handled. Read-only in the app.",
  review: "Whether a person has checked the catalog's values.",
};

export const FIELD_META: Record<string, Record<string, FieldMeta>> = {
  doc: {
    kind: { title: "Kind", about: "The type of document.", editable: "part2", vocab: "kind" },
    entity: { title: "Entity", about: "The Allegis fund, GP or management company the document belongs to (one or more).", editable: "part2", vocab: "entity" },
    portco: { title: "Portco", about: "The portfolio company the document is about (one or more).", editable: "part2", vocab: "portco" },
    fiscal_year: { title: "Fiscal year", about: "The fiscal or tax year the document covers.", editable: "part2" },
    period: { title: "Period", about: "The part of the year the document covers.", editable: "part2", vocab: "period" },
    effective_date: { title: "Effective date", about: "The date the document takes effect or is dated.", editable: "part2" },
    workstream: { title: "Workstream", about: "The finance workstream the file was filed under.", editable: "machine", vocab: "workstream" },
    issuer: { title: "Issuer type", about: "What sort of party produced the document.", editable: "machine", vocab: "issuer" },
    catalog_id: { title: "Catalog ID", about: "The catalog's document number, linking the file to its catalog record.", editable: "machine" },
  },
  exec: {
    stage: { title: "Stage", about: "How far the signing has got.", editable: "review", vocab: "stage" },
    executed_date: { title: "Executed date", about: "The date the last party signed.", editable: "review" },
    evidence: { title: "Evidence", about: "What shows the document was signed.", editable: "machine", vocab: "evidence" },
  },
  handling: {
    tier: { title: "Tier", about: "Normal, Restricted, or Secret (never shown anywhere).", editable: "never", vocab: "tier" },
    contains: { title: "Contains", about: "Sensitive content flags.", editable: "never", vocab: "contains" },
  },
  review: {
    status: { title: "Status", about: "Needs review, Confirmed, or Wrong.", editable: "review", vocab: "review" },
    reviewed_by: { title: "Reviewed by", about: "The person who confirmed the values.", editable: "review" },
    note: { title: "Note", about: "A reviewer's note, for example what is wrong.", editable: "review" },
  },
};

const TYPE_WORDS: Record<string, string> = {
  selectionOptions: "pick list", integerOptions: "whole number", dateOptions: "date", textOptions: "text", userOptions: "person",
};

export interface PanelChoice { code: string; meaning: string }
export interface PanelField { key: string; title: string; about: string; type: string; multi: boolean; editable: Editable; choices: PanelChoice[] }
export interface PanelLabel { key: string; title: string; about: string; fields: PanelField[] }

const MULTI = new Set(["doc.entity", "doc.portco", "handling.contains"]);

export function buildLabelsPanel(names: { entity: Map<string, string>; portco: Map<string, string> }): PanelLabel[] {
  return Object.entries(S).map(([lk, L]) => ({
    key: lk,
    title: L.title,
    about: LABEL_ABOUT[lk] ?? "",
    fields: Object.entries(L.fields).map(([fk, F]) => {
      const m = FIELD_META[lk]?.[fk] ?? { title: fk, about: "", editable: "machine" as Editable };
      const codes = Object.keys(F.choices ?? {});
      const meaning = (code: string) =>
        m.vocab === "entity" ? names.entity.get(code) ?? code
        : m.vocab === "portco" ? names.portco.get(code) ?? code
        : m.vocab ? ((VOCAB[m.vocab] as Record<string, string>)[code] ?? code) : code;
      return {
        key: fk, title: m.title, about: m.about, type: TYPE_WORDS[F.type] ?? F.type, multi: MULTI.has(`${lk}.${fk}`), editable: m.editable,
        choices: codes.map((code) => ({ code, meaning: meaning(code) })),
      };
    }),
  }));
}
