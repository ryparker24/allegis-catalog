"use client";
import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import { api } from "./client";
import { Icon } from "./icons";

type Choice = { code: string; meaning: string };
type Field = { key: string; title: string; about: string; type: string; multi: boolean; editable: "review" | "machine" | "never" | "part2"; choices: Choice[] };
type Label = { key: string; title: string; about: string; fields: Field[] };

const ED: Record<Field["editable"], [string, string, string]> = {
  review: ["ed-review", "Editable: Review queue", "The Review queue writes this field on the file, as you."],
  machine: ["ed-machine", "Machine-set", "Set by the catalog rules and the labelling run. Not editable in the app yet."],
  never: ["ed-never", "Read-only", "Never editable in the app."],
  part2: ["ed-part2", "Editable after Part 2", "Machine-set today. CAT-WO-02 Part 2 makes it editable in Find and Review (written on the file as you)."],
};

/** Item 3: the Labels side panel. Reads labels_schema.json + ref (via /api/labels); never edits. */
export function LabelsPanel({ onClose }: { onClose: () => void }) {
  const box = useRef<HTMLElement | null>(null);
  const [labels, setLabels] = useState<Label[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [q, setQ] = useState("");
  useEffect(() => { api<{ labels: Label[] }>("/api/labels").then((r) => setLabels(r.labels)).catch((e) => setErr((e as Error).message)); }, []);
  useEffect(() => {
    const k = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key !== "Tab" || !box.current) return; // keep focus inside the dialog
      const f = [...box.current.querySelectorAll<HTMLElement>("button, input, summary, [tabindex]:not([tabindex='-1'])")].filter((x) => x.offsetParent !== null);
      if (!f.length) return;
      const first = f[0], last = f[f.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    };
    document.addEventListener("keydown", k);
    return () => document.removeEventListener("keydown", k);
  }, [onClose]);

  const t = q.trim().toLowerCase();
  const shown = useMemo(() => (labels ?? []).map((L) => ({
    ...L,
    fields: L.fields.map((f) => {
      const hitField = !t || f.title.toLowerCase().includes(t) || L.title.toLowerCase().includes(t);
      const choices = hitField ? f.choices : f.choices.filter((c) => c.code.toLowerCase().includes(t) || c.meaning.toLowerCase().includes(t));
      return { ...f, choices, hit: hitField || choices.length > 0 };
    }).filter((f) => f.hit),
  })).filter((L) => L.fields.length), [labels, t]);

  return (
    <div className="drawer-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <aside ref={box} className="drawer" role="dialog" aria-modal="true" aria-labelledby="labels-title">
        <div className="drawer-head">
          <div style={{ flex: 1 }}>
            <div className="crumb">Allegis Capital · Catalog · Drive labels</div>
            <h2 id="labels-title">Labels</h2>
            <p>Every label the catalog puts on Drive files, each field in plain words, and every choice as code and meaning. This panel only reads.</p>
          </div>
          <button className="btn sm outline" onClick={onClose} aria-label="Close labels panel"><Icon name="x" /></button>
        </div>
        <div className="drawer-tools">
          <input className="input" type="search" placeholder="Find a field, code or meaning (e.g. k1)" value={q} onChange={(e) => setQ(e.target.value)} autoFocus />
        </div>
        <div className="drawer-body">
          {err ? <div className="error">Could not load the labels: {err}</div> : null}
          {!labels && !err ? <div className="muted">Loading…</div> : null}
          {labels && !shown.length ? <div className="muted">Nothing matches “{q}”.</div> : null}
          {shown.map((L) => (
            <section key={L.key} className="lbl-card">
              <header><h3>{L.title}</h3><p>{L.about}</p></header>
              {L.fields.map((f) => (
                <details key={f.key} className="lbl-field" open={!!t}>
                  <summary>
                    <Icon name="chevRight" className="chev" />
                    <span className="t">{f.title}</span>
                    <span className="ty">{f.type}{f.multi ? ", several allowed" : ""}{f.choices.length ? ` · ${f.choices.length} choice${f.choices.length === 1 ? "" : "s"}` : ""}</span>
                    <span className={`ed ed-tag ${ED[f.editable][0]}`} title={ED[f.editable][2]}>{ED[f.editable][1]}</span>
                  </summary>
                  <div className="about">{f.about}</div>
                  {f.choices.length ? (
                    <div className="lbl-choices">
                      {f.choices.map((c) => <Fragment key={c.code}><code>{c.code}</code><span>{c.meaning}</span></Fragment>)}
                    </div>
                  ) : null}
                </details>
              ))}
            </section>
          ))}
          {labels ? (
            <p className="small muted">
              Editable today: Signing stage and Executed date, plus the Catalog Review fields, through the Review queue. Part 2 of CAT-WO-02 makes Kind, Entity, Portco,
              Fiscal year, Period and Effective date editable in Find and Review, and adds the Parties label and a Status field. Handling stays read-only.
            </p>
          ) : null}
        </div>
      </aside>
    </div>
  );
}
