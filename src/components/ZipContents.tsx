"use client";
/**
 * CAT-WO-17 · R-062 · Side panel "Inside this zip": the zip's members (names, size), each marked "also on Drive" (same md5
 * as a catalog file; linked when the user can open it) or "only in this zip". Names are hidden in screenshot mode.
 */
import { useEffect, useState } from "react";
import { maskNames } from "./bus";
import { api } from "./client";

type Member = { parent_member: string; member_path: string; size_bytes: number | null; encrypted: boolean; on_drive: boolean; on_drive_file_id: string | null };
type Resp = { listed: boolean; status?: string; member_count?: number; members?: Member[]; truncated?: boolean };

export const isZipName = (name: string | null | undefined) => !!name && /\.zip$/i.test(name);
const kb = (n: number | null) => (n == null ? "" : n >= 1e6 ? `${(n / 1e6).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1e3))} KB`);

export function ZipContents({ fileId }: { fileId: string }) {
  const [d, setD] = useState<Resp | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    setD(null); setErr(null);
    api<Resp>(`/api/zip?file_id=${encodeURIComponent(fileId)}`).then(setD).catch((e) => setErr((e as Error).message));
  }, [fileId]);
  if (err) return <p className="muted small">Zip contents not loaded: {err}</p>;
  if (!d) return <p className="muted small">Loading zip contents…</p>;
  if (!d.listed) return <p className="muted small">Zip contents not listed yet.</p>;
  const ms = d.members ?? [];
  const masked = maskNames();
  const only = ms.filter((m) => !m.on_drive).length;
  return (
    <div className="locs">
      <div className="cap">Inside this zip ({ms.length}{d.truncated ? "+" : ""}) · {only} only in this zip{d.status === "encrypted" ? " · password-protected" : ""}</div>
      <ul>
        {ms.map((m, i) => {
          const t = masked ? `File ••••${String(i).padStart(4, "0")}` : (m.parent_member ? `${m.parent_member} › ` : "") + m.member_path;
          return (
            <li key={`${m.parent_member}|${m.member_path}`}>
              {t} <span className="muted small">{kb(m.size_bytes)}</span>
              {m.on_drive
                ? (m.on_drive_file_id
                  ? <a className="small" href={`https://drive.google.com/file/d/${m.on_drive_file_id}/view`} target="_blank" rel="noopener noreferrer"> · also on Drive</a>
                  : <span className="muted small"> · also on Drive</span>)
                : <span className="muted small"> · only in this zip</span>}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
