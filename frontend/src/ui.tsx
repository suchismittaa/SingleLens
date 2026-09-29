import { useEffect, useState } from "react";
import { Check, X as XIcon } from "lucide-react";

export const Logo = ({ size = 32 }) => (
  <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden><rect width="32" height="32" fill="#050505" stroke="#242424" />
    <path d="M23 10H12a3 3 0 0 0 0 6h8a3 3 0 0 1 0 6H9" fill="none" stroke="#FFD600" strokeWidth="3.5" strokeLinecap="square" /></svg>
);

export function useCountUp(target: number | null, ms = 600) {
  const [v, setV] = useState(0);
  useEffect(() => {
    if (target == null) return;
    let raf = 0; const t0 = performance.now();
    const tick = (t: number) => { const k = Math.min(1, (t - t0) / ms); setV(target * k); if (k < 1) raf = requestAnimationFrame(tick); };
    raf = requestAnimationFrame(tick); return () => cancelAnimationFrame(raf);
  }, [target]);
  return v;
}

export const DemoTag = ({ text = "DEMO ANALYSIS" }) => (
  <span className="inline-block border border-sig text-sig text-[10px] font-semibold tracking-widest px-2 py-0.5">{text}</span>
);

export const Sev = ({ s }: { s: string }) => (
  <span className={`text-[10px] font-bold tracking-widest px-2 py-0.5 ${s === "HIGH" ? "bg-sig text-bg" : s === "MEDIUM" ? "border border-sig text-sig" : "border border-[#333] text-t2"}`}>{s}</span>
);

export const Mark = ({ ok }: { ok: boolean }) => ok ? <Check size={14} className="text-sig inline" /> : <XIcon size={14} className="text-t3 inline" />;

export const Loading = ({ label = "ANALYZING PROMPTS" }) => (
  <div className="card" role="status">
    <div className="lbl mb-3">{label}</div>
    <div className="relative h-1 bg-[#1a1a1a] overflow-hidden"><div className="absolute top-0 h-1 w-2/5 bg-sig" style={{ animation: "slide 1.2s linear infinite" }} /></div>
    <p className="text-t2 text-sm mt-3">Waiting for the provider. Results are validated before anything is stored.</p>
  </div>
);

export const Empty = ({ title, body, action, onAction }: any) => (
  <div className="card text-center py-12">
    <div className="lbl mb-2">{title}</div><p className="text-t2 max-w-md mx-auto mb-5">{body}</p>
    {action && <button className="btn" onClick={onAction}>{action}</button>}
  </div>
);

export const Stat = ({ label, value, suffix = "", decimals = 0, raw }: any) => {
  const v = useCountUp(typeof value === "number" ? value : null);
  return (
    <div className="card">
      <div className="lbl">{label}</div>
      <div className="text-4xl font-extrabold mt-2 tracking-tight">{raw ?? (value == null ? "—" : v.toFixed(decimals) + suffix)}</div>
    </div>
  );
};

export function Evidence({ item, onClose }: any) {
  const ev = item.evidence, sc = ev.scan;
  return (
    <div className="fixed inset-0 bg-black/80 z-50 overflow-y-auto p-4" onClick={onClose}>
      <div className="max-w-3xl mx-auto bg-bg2 border border-line p-6 space-y-6" onClick={(e) => e.stopPropagation()}>
        <div className="flex justify-between items-start gap-4">
          <div><Sev s={item.severity} /><h2 className="text-xl font-extrabold mt-2">{item.title}</h2><p className="text-t2 text-sm mt-1">{item.description}</p></div>
          <button className="btn2" onClick={onClose} aria-label="Close">Close</button>
        </div>
        {ev.prompts.slice(0, 8).map((p: any) => (
          <div key={p.prompt_id} className="border border-line p-4 space-y-3">
            <div><div className="lbl">Prompt</div><div>{p.text}</div></div>
            <div><div className="lbl">AI observation</div><div>{p.mentioned ? `Your brand was mentioned at #${p.position ?? "?"}.` : "Your brand was not mentioned."}</div></div>
            <div><div className="lbl">Competitors observed</div><div className="text-t2">{p.competitors.join(", ") || "None"}</div></div>
            <div><div className="lbl">Deterministic check</div>
              {p.checks.length === 0 && <div className="text-t2 text-sm">No known requirements extracted from this prompt.</div>}
              {p.checks.map((c: any) => (
                <div key={c.requirement} className="flex items-center gap-2 text-sm py-0.5"><Mark ok={c.status === "MATCH"} />
                  <span>{c.requirement}</span><span className="text-t3">→ {c.status === "MATCH" ? "found in product data" : "NOT FOUND in product data"}</span></div>))}
            </div>
          </div>))}
        {ev.prompts.length > 8 && <p className="text-t3 text-sm">Showing 8 of {ev.prompts.length} prompts.</p>}
        <div><div className="lbl">Product data</div><div className="text-t2 text-sm">{ev.product_attributes.join(" · ") || "No attributes"}{ev.product_price != null && ` · ₹${ev.product_price}`}</div></div>
        <div className="grid grid-cols-3 gap-4 text-sm">
          <div><div className="lbl">Scan time</div>{sc.time ? new Date(sc.time).toUTCString().slice(5, 22) + " UTC" : "—"}</div>
          <div><div className="lbl">Provider</div>{sc.provider}{sc.provider === "demo" && <> <DemoTag text="DEMO" /></>}</div>
          <div><div className="lbl">Analysis status</div>{sc.status}</div>
        </div>
      </div>
    </div>
  );
}
