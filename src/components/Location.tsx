"use client";
/**
 * CAT-WO-03.1 · Location: drive › folder path of the document's primary copy (the crawl's own path data, never a
 * label), truncated in the cell with the full path on hover, linking to the parent folder in Drive, "+N other
 * locations" when copies sit elsewhere. Rows only reach the browser after the live access check (as names); in
 * screenshot mode (?mask=1) the path is hidden like a name.
 */
import { useEffect, useState } from "react";
import { maskNames } from "./bus";
import { api } from "./client";

const FOLDER_ID = /^[A-Za-z0-9_-]{10,128}$/;
export const folderUrl = (id: string | null | undefined) => (id && FOLDER_ID.test(id) ? `https://drive.google.com/drive/folders/${id}` : null);
export function truncPath(s: string, n = 56): string { return s.length <= n ? s : "…" + s.slice(s.length - n + 1); }

export function LocationCell({ location, folderId, other = 0 }: { location: string | null | undefined; folderId?: string | null; other?: number | null }) {
  if (!location) return <span className="muted">-</span>;
  if (maskNames()) return <span className="muted">Location ••••{other ? ` · +${other}` : ""}</span>;
  const url = folderUrl(folderId);
  const text = truncPath(location);
  return (
    <span className="loc">
      {url ? <a href={url} target="_blank" rel="noopener noreferrer" title={location} onClick={(e) => e.stopPropagation()}>{text}</a> : <span title={location}>{text}</span>}
      {other ? <span className="muted small"> · +{other} other location{other > 1 ? "s" : ""}</span> : null}
    </span>
  );
}

type Loc = { file_id: string; location: string; folder_id: string | null; is_primary: boolean };

/** Side panel: every location of the document, each copy live-checked as the user (one it can't open is counted only). */
export function AllLocations({ fileId }: { fileId: string }) {
  const [d, setD] = useState<{ locations: Loc[]; not_shown: number } | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    setD(null); setErr(null);
    api<{ locations: Loc[]; not_shown: number }>(`/api/locations?file_id=${encodeURIComponent(fileId)}`).then(setD).catch((e) => setErr((e as Error).message));
  }, [fileId]);
  if (err) return <p className="muted small">Locations not loaded: {err}</p>;
  if (!d) return <p className="muted small">Loading locations…</p>;
  const masked = maskNames();
  return (
    <div className="locs">
      <div className="cap">Locations ({d.locations.length + d.not_shown})</div>
      <ul>
        {d.locations.map((l) => {
          const url = folderUrl(l.folder_id);
          const t = masked ? `Location ••••${l.file_id.slice(-4)}` : l.location;
          return <li key={l.file_id}>{url && !masked ? <a href={url} target="_blank" rel="noopener noreferrer">{t}</a> : t}{l.is_primary ? <span className="muted small"> · primary</span> : null}</li>;
        })}
      </ul>
      {d.not_shown ? <p className="muted small">{d.not_shown} more location{d.not_shown > 1 ? "s" : ""} you can&apos;t open (not shown).</p> : null}
    </div>
  );
}
