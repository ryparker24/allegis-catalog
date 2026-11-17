/**
 * Worker logging: file IDs and codes ONLY. File names can carry LP names, so any key that is not on the
 * allow-list below is dropped, and string values that are not code-shaped are replaced.
 */
const ALLOWED_KEYS = new Set([
  "event", "file_id", "file_ids", "document_id", "status", "stage", "queue_reason", "labels", "count", "total",
  "dropped_no_access", "dropped_check_failed", "dropped_secret", "page", "page_size", "ms", "http_status",
  "drive_status", "reason", "route", "has_session", "can_write", "outcome",
]);
const CODE_SHAPED = /^[A-Za-z0-9_.:\-/()]{0,120}$/;

type Val = string | number | boolean | null | undefined | (string | number)[];

export function sanitize(fields: Record<string, unknown>): Record<string, Val> {
  const out: Record<string, Val> = {};
  for (const [k, v] of Object.entries(fields)) {
    if (!ALLOWED_KEYS.has(k)) continue;
    if (v == null || typeof v === "number" || typeof v === "boolean") out[k] = v as Val;
    else if (typeof v === "string") out[k] = CODE_SHAPED.test(v) ? v : "[redacted]";
    else if (Array.isArray(v)) out[k] = v.slice(0, 60).map((x) => (typeof x === "number" ? x : CODE_SHAPED.test(String(x)) ? String(x) : "[redacted]"));
  }
  return out;
}

export function logEvent(event: string, fields: Record<string, unknown> = {}): void {
  console.log(JSON.stringify(sanitize({ event, ...fields })));
}
