import type { AppEnv } from "@/lib/env";

export const SECRET = "test-secret-0123456789-abcdefghijklmnopqrstuvwxyz";
export const ENV: AppEnv = {
  APP_ORIGIN: "http://localhost:3000",
  ALLOWED_HD: "allegiscapital.com",
  ALLOWLIST: "ryan@allegiscapital.com",
  GOOGLE_CLIENT_ID: "test-client.apps.googleusercontent.com",
  GOOGLE_CLIENT_SECRET: "test-client-secret",
  SESSION_SECRET: SECRET,
  ACCESS_MODE: "local-dev",
};

/** Builds a multipart/mixed Drive batch response. */
export function batchResponse(parts: { status: number; body: unknown }[], boundary = "batch_TEST"): Response {
  const text = parts
    .map((p, i) =>
      `--${boundary}\r\nContent-Type: application/http\r\nContent-ID: <response-item${i}>\r\n\r\n` +
      `HTTP/1.1 ${p.status} ${p.status === 200 ? "OK" : "Error"}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n${JSON.stringify(p.body)}\r\n`)
    .join("") + `--${boundary}--\r\n`;
  return new Response(text, { status: 200, headers: { "content-type": `multipart/mixed; boundary=${boundary}` } });
}
