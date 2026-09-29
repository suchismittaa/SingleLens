const B = (import.meta as any).env?.VITE_API_URL ?? "http://localhost:8000";
export async function api(path: string, opts: any = {}) {
  const r = await fetch(B + path, { headers: { "Content-Type": "application/json" }, ...opts, body: opts.body ? JSON.stringify(opts.body) : undefined });
  const j = await r.json().catch(() => null);
  if (!r.ok) {
    const d = j?.detail;
    throw new Error(typeof d === "string" ? d : d?.reason ? `${d.code ?? "ERROR"}: ${d.reason}` : "Request failed");
  }
  return j;
}
