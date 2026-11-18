"use client";
import { useEffect, useState } from "react";
import { api, type Row } from "./client";
import { maskNames } from "./bus";

type Party = { entity_code: string; partner_code: string; display_name: string; interest_kind: string; is_company_gp: boolean };
type Staff = { email: string; name: string };

/**
 * CAT-WO-03 R-026 · a document's Subject: roster code(s) (Subject code(s)) and/or a staff account (Subject (person)).
 * Codes are picked from the roster of the document's entities (never typed). The person picker searches the Workspace
 * directory; that search is the ONLY place the app asks Google for directory access (on first use).
 * lane = the Review "Match subject" lane (candidates first, plus "none").
 */
export function SubjectForm({ row, lane = false, onSaved }: { row: Row; lane?: boolean; onSaved: (patch: Partial<Row>) => void }) {
  const ents = [...new Set([...(row.entities ?? []), ...(row.issuing_entity ? [row.issuing_entity] : [])])];
  const [parties, setParties] = useState<Party[] | null>(null);
  const [codes, setCodes] = useState<string[]>(row.subject_codes ?? []);
  const [none, setNone] = useState(false);
  const [personQ, setPersonQ] = useState("");
  const [staff, setStaff] = useState<Staff[] | null>(null);
  const [person, setPerson] = useState<string | null | undefined>(undefined);   // undefined = unchanged
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  useEffect(() => {
    setCodes(row.subject_codes ?? []); setNone(false); setPerson(undefined); setStaff(null); setMsg(null);
    if (!ents.length) { setParties([]); return; }
    api<{ parties: Party[] }>(`/api/party?file_id=${encodeURIComponent(row.file_id)}`).then((r) => setParties(r.parties)).catch(() => setParties([]));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [row.file_id, (row.subject_codes ?? []).join(","), row.subject_person]);
  const nameOf = (c: string) => (maskNames() ? "" : parties?.find((p) => p.partner_code === c)?.display_name ?? "");
  const roster = [...new Map((parties ?? []).map((p) => [p.partner_code, p])).values()];
  const searchStaff = async () => {
    if (personQ.trim().length < 2) return;
    try { setStaff((await api<{ hits: Staff[] }>(`/api/subject/directory?q=${encodeURIComponent(personQ.trim())}&next=${lane ? "/review" : "/"}`)).hits); }
    catch (e) { setMsg((e as Error).message); }   // 409 consent_required: api() sends the user to Google once
  };
  const codesChanged = JSON.stringify(codes) !== JSON.stringify([...(row.subject_codes ?? [])].sort());
  const save = async () => {
    setBusy(true); setMsg(null);
    try {
      const r = await api<{ label_published: boolean }>("/api/subject", { method: "POST", body: JSON.stringify({
        file_id: row.file_id, source: lane ? "match_subject" : undefined,
        ...(none ? { none: true } : codesChanged ? { codes } : {}), ...(person !== undefined ? { person } : {}),
      }) });
      setMsg(r.label_published ? "Saved to Drive." : "Recorded in the catalog (the Subject fields aren't published on the label yet).");
      onSaved({ subject_codes: none ? [] : codesChanged ? codes : row.subject_codes, subject_person: person === undefined ? row.subject_person : person });
    } catch (e) {
      const b = (e as { body?: { error?: string; reason?: string } }).body;
      setMsg(`Not saved: ${b?.reason ?? b?.error ?? (e as Error).message}`);
    }
    setBusy(false);
  };
  const toggle = (c: string) => { setNone(false); setCodes((cs) => (cs.includes(c) ? cs.filter((x) => x !== c) : [...cs, c].sort())); };
  return (
    <div className="subject-box">
      <h3 className="cap">Subject {lane ? "· Match subject" : ""}</h3>
      {lane && row.subject_candidates?.length ? (
        <div className="opts" role="group" aria-label="Candidate partners">
          {row.subject_candidates.map((c) => (
            <label key={c} className="opt"><input type="checkbox" checked={codes.includes(c)} onChange={() => toggle(c)} /> <code>{c}</code> {nameOf(c)}</label>
          ))}
          <label className="opt"><input type="checkbox" checked={none} onChange={(e) => { setNone(e.target.checked); if (e.target.checked) setCodes([]); }} /> None of these (no roster subject)</label>
        </div>
      ) : null}
      <label className="small">Subject code(s) {roster.length ? "" : <span className="muted">(no Datum roster for this document&apos;s entities)</span>}
        <div className="multi">
          {codes.map((c) => <span key={c} className="chip"><code>{c}</code> {nameOf(c)}<button type="button" aria-label={`Remove ${c}`} onClick={() => toggle(c)}>×</button></span>)}
          {roster.length ? (
            <select className="input" value="" onChange={(e) => e.target.value && toggle(e.target.value)} aria-label="Add a roster partner">
              <option value="">+ add from the roster</option>
              {roster.filter((p) => !codes.includes(p.partner_code)).map((p) => <option key={p.partner_code} value={p.partner_code}>{p.partner_code}{maskNames() ? "" : ` · ${p.display_name}`}</option>)}
            </select>
          ) : null}
        </div>
      </label>
      <label className="small">Subject (person) <span className="muted">current staff only</span>
        <div className="row-inline">
          <input className="input" value={personQ} maxLength={60} onChange={(e) => setPersonQ(e.target.value)} placeholder={row.subject_person ?? "Search the staff directory"} onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); searchStaff(); } }} />
          <button type="button" className="btn" onClick={searchStaff}>Search</button>
          {row.subject_person || person ? <button type="button" className="btn" onClick={() => setPerson(null)}>Clear</button> : null}
        </div>
      </label>
      {staff ? <div className="opts">{staff.length ? staff.map((s) => (
        <label key={s.email} className="opt"><input type="radio" name="staff" checked={person === s.email} onChange={() => setPerson(s.email)} /> {maskNames() ? "" : s.name} <code>{s.email}</code></label>
      )) : <span className="muted small">No staff found.</span>}</div> : null}
      {person === null ? <p className="muted small">Subject (person) will be cleared.</p> : null}
      <div className="actions">
        <button className="btn primary" type="button" disabled={busy || (!none && !(codesChanged && codes.length) && person === undefined)} onClick={save}>Save subject</button>
      </div>
      {msg ? <p className={`status${msg.startsWith("Not saved") ? " error" : ""}`} role="status">{msg}</p> : null}
    </div>
  );
}
