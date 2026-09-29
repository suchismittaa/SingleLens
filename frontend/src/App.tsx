import { useCallback, useEffect, useState } from "react";
import { Bar, BarChart, Cell, ResponsiveContainer, XAxis, YAxis } from "recharts";
import { AlertTriangle, History, LayoutGrid, Menu, Package, Search, X } from "lucide-react";
import { api } from "./api";
import { DemoTag, Empty, Evidence, Loading, Logo, Mark, Sev, Stat } from "./ui";

type Page = "dashboard" | "explorer" | "findings" | "history" | "product";
const NAV: [Page, string, any][] = [["dashboard", "Dashboard", LayoutGrid], ["explorer", "Prompt Explorer", Search], ["findings", "Findings", AlertTriangle], ["history", "Scan History", History]];

export default function App() {
  const [page, setPage] = useState<Page>("dashboard");
  const [open, setOpen] = useState(false);
  const [product, setProduct] = useState<any>(null);
  const [cfg, setCfg] = useState<any>({ gemini_available: false, max_prompts: 10 });
  const [mode, setMode] = useState("demo");
  const [ev, setEv] = useState<any>(null);
  const [err, setErr] = useState("");
  const [version, setVersion] = useState(0);

  useEffect(() => {
    api("/api/config").then(setCfg).catch(() => setErr("Backend unreachable. Start it on port 8000."));
    api("/api/products").then((ps) => ps[0] && setProduct(ps[0])).catch(() => {});
  }, []);
  const go = (p: Page) => { setPage(p); setOpen(false); };
  const bump = useCallback(() => setVersion((v) => v + 1), []);
  const props = { product, mode, cfg, setEv, go, version, bump };

  return (
    <div className="min-h-screen md:flex">
      <button className="md:hidden fixed top-3 right-3 z-40 btn2" onClick={() => setOpen(!open)} aria-label="Menu">{open ? <X size={18} /> : <Menu size={18} />}</button>
      <aside className={`${open ? "block" : "hidden"} md:block fixed md:sticky top-0 h-screen w-64 shrink-0 bg-bg2 border-r border-line p-5 z-30 overflow-y-auto`}>
        <div className="flex items-center gap-3 mb-8"><Logo /><span className="font-extrabold tracking-tight text-lg">SignalLens</span></div>
        <div className="lbl mb-2">Overview</div>
        {NAV.map(([k, label, Icon]) => (
          <button key={k} onClick={() => go(k)} className={`flex items-center gap-3 w-full text-left px-3 py-2 text-sm transition duration-200 ${page === k ? "text-sig border-l-2 border-sig bg-card" : "text-t2 border-l-2 border-transparent hover:text-white"}`}><Icon size={16} />{label}</button>))}
        <div className="lbl mt-6 mb-2">Data</div>
        <button onClick={() => go("product")} className={`flex items-center gap-3 w-full text-left px-3 py-2 text-sm transition duration-200 ${page === "product" ? "text-sig border-l-2 border-sig bg-card" : "text-t2 border-l-2 border-transparent hover:text-white"}`}><Package size={16} />Product</button>
        <div className="mt-8 border border-line p-3">
          <div className="lbl mb-2">AI mode</div>
          {["demo", "gemini"].map((m) => (
            <label key={m} className={`flex items-center gap-2 text-sm py-1 ${m === "gemini" && !cfg.gemini_available ? "text-t3" : "cursor-pointer"}`}>
              <input type="radio" className="accent-[#FFD600]" checked={mode === m} disabled={m === "gemini" && !cfg.gemini_available} onChange={() => setMode(m)} />{m === "demo" ? "Demo" : "Gemini"}</label>))}
          {!cfg.gemini_available && <p className="text-t3 text-xs mt-1">Set GEMINI_API_KEY on the backend to enable Gemini.</p>}
          {mode === "demo" && <div className="mt-2"><DemoTag text="DEMO MODE" /></div>}
        </div>
      </aside>
      <main className="flex-1 min-w-0 p-5 md:p-10 max-w-6xl">
        {err && <div className="card mb-4 text-sig">{err}</div>}
        {!product ? <Empty title="No product" body="Create a product profile to start." action="Create product" onAction={() => go("product")} />
          : page === "dashboard" ? <Dashboard {...props} />
          : page === "explorer" ? <Explorer {...props} />
          : page === "findings" ? <Findings {...props} />
          : page === "history" ? <HistoryPage {...props} /> : null}
        {page === "product" && <ProductPage product={product} setProduct={setProduct} bump={bump} />}
      </main>
      {ev && <Evidence item={ev} onClose={() => setEv(null)} />}
    </div>
  );
}

function useLoad(path: string | null, dep: any[]) {
  const [d, setD] = useState<any>(null); const [e, setE] = useState(""); const [l, setL] = useState(true);
  useEffect(() => { if (!path) return; setL(true); api(path).then((x) => { setD(x); setE(""); }).catch((x) => { setD(null); setE(x.message); }).finally(() => setL(false)); }, [path, ...dep]);
  return { d, e, l };
}

const Bars = ({ data, k, label }: any) => (
  <div style={{ height: 34 * data.length + 20 }}>
    <ResponsiveContainer><BarChart data={data} layout="vertical" margin={{ left: 10, right: 30 }}>
      <XAxis type="number" domain={[0, 100]} hide /><YAxis type="category" dataKey={label} width={130} tick={{ fill: "#A3A3A3", fontSize: 11 }} axisLine={false} tickLine={false} />
      <Bar dataKey={k} fill="#FFD600" background={{ fill: "#1a1a1a" }} isAnimationActive animationDuration={400}>{data.map((_: any, i: number) => <Cell key={i} fill="#FFD600" />)}</Bar>
    </BarChart></ResponsiveContainer>
  </div>
);

function Dashboard({ product, go, setEv, version }: any) {
  const m = useLoad(`/api/products/${product.id}/metrics`, [version]);
  const f = useLoad(`/api/products/${product.id}/findings`, [version]);
  if (m.l) return <Loading label="LOADING METRICS" />;
  if (m.e || !m.d) return <Empty title="No scans yet" body="Run your first visibility scan to understand how AI systems respond to your product." action="Run first scan" onAction={() => go("explorer")} />;
  const d = m.d; const gap = f.d?.find((x: any) => x.id === d.top_gap?.finding_id);
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div><div className="lbl">AI commerce visibility</div><h1 className="text-3xl md:text-4xl font-extrabold tracking-tight mt-1">Understand how AI systems see your product.</h1>
          <p className="text-t2 mt-2">{product.brand} {product.name} {d.is_demo && <DemoTag />}</p></div>
        <button className="btn" onClick={() => go("explorer")}>Run new scan →</button>
      </div>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="AI inclusion" value={d.inclusion_rate} suffix="%" />
        <Stat label="Prompt coverage" raw={`${d.prompts_with_mention} / ${d.total_prompts}`} />
        <Stat label="Average position" value={d.average_position} decimals={1} />
        <Stat label="Visibility gaps" value={d.visibility_gaps} />
      </div>
      <div className="card border-sig">
        <div className="lbl text-sig">Why am I invisible?</div>
        <p className="text-2xl font-extrabold mt-2">Your brand was missed in {d.missed} / {d.total_prompts} buyer prompts.</p>
        {d.top_gap ? (<><div className="lbl mt-4">Most common potential gap</div><div className="text-3xl font-extrabold text-sig">"{d.top_gap.signal}"</div>
          <p className="text-t2 mt-2 max-w-xl">This requirement appeared in {d.top_gap.count} missed buyer prompt(s) and is not explicitly represented in your product attributes. It may be a contributing signal, not a proven cause.</p>
          {gap && <button className="btn mt-4" onClick={() => setEv(gap)}>View evidence →</button>}</>)
          : <p className="text-t2 mt-2">No attribute gaps were detected in missed prompts.</p>}
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <div className="card overflow-x-auto"><div className="lbl mb-3">AI surface breakdown</div>
          <table className="w-full text-sm"><thead><tr className="text-t3 text-left"><th className="py-1">Surface</th><th>Inclusion</th><th>Avg position</th></tr></thead>
            <tbody>{d.surfaces.map((s: any) => <tr key={s.surface} className="border-t border-line"><td className="py-2 capitalize">{s.surface} {s.demo && <DemoTag text="DEMO DATA" />}</td><td>{s.inclusion_rate}%</td><td>{s.average_position ?? "—"}</td></tr>)}</tbody></table>
          <p className="text-t3 text-xs mt-3">Only surfaces actually scanned are listed.</p></div>
        <div className="card"><div className="lbl mb-2">Inclusion by prompt family</div>
          <Bars label="name" k="rate" data={Object.entries(d.families).filter(([, v]: any) => v.total).map(([name, v]: any) => ({ name, rate: v.rate }))} /></div>
      </div>
      <div className="card"><div className="lbl mb-3">Competitor frequency</div>
        <p className="text-t3 text-xs mb-3">Counts of appearances across analyzed prompts. An observation, not a ranking.</p>
        {d.competitors.slice(0, 6).map((c: any) => <div key={c.brand} className="flex justify-between border-t border-line py-2 text-sm"><span>{c.brand}</span><span className="text-t2">{c.prompts} prompts</span></div>)}</div>
    </div>
  );
}

function Explorer({ product, mode, cfg, go, bump, setEv }: any) {
  const [text, setText] = useState("best sunscreen for oily skin under ₹500");
  const [res, setRes] = useState<any>(null);
  const [prompts, setPrompts] = useState<string[]>([]);
  const [busy, setBusy] = useState(""); const [err, setErr] = useState(""); const [note, setNote] = useState("");
  const run = async (label: string, fn: () => Promise<void>) => { setBusy(label); setErr(""); try { await fn(); } catch (e: any) { setErr(e.message + (mode === "gemini" ? " Switching to Demo Mode is available." : "")); } finally { setBusy(""); } };
  const analyze = () => run("ANALYZING PROMPTS", async () => {
    const p = await api(`/api/products/${product.id}/prompts`, { method: "POST", body: { text } });
    setRes(await api(`/api/prompts/${p.id}/analyze`, { method: "POST", body: { mode } }));
  });
  const generate = () => run("GENERATING PROMPTS", async () => {
    const g = await api("/api/prompts/generate", { method: "POST", body: { product_id: product.id, mode } });
    setPrompts(g.prompts.map((p: any) => p.text)); setNote(g.rejected.length ? `${g.rejected.length} candidate(s) rejected by validation.` : "");
  });
  const scan = () => run("RUNNING VISIBILITY SCAN", async () => {
    const s = await api("/api/scans", { method: "POST", body: { product_id: product.id, prompts, mode } });
    if (s.status === "FAILED") throw new Error(s.error); bump(); go("dashboard");
  });
  const r = res?.records?.[0];
  return (
    <div className="space-y-6">
      <div><div className="lbl">Prompt Explorer</div><h1 className="text-3xl font-extrabold tracking-tight mt-1">Ask what a buyer would ask.</h1></div>
      <div className="card space-y-3"><textarea className="inp text-lg h-24" value={text} onChange={(e) => setText(e.target.value)} aria-label="Buyer prompt" />
        <button className="btn" disabled={!!busy || !text.trim()} onClick={analyze}>Analyze prompt →</button></div>
      {busy && <Loading label={busy} />}
      {err && <div className="card border-sig text-sig">{err}</div>}
      {res?.status === "FAILED" && <div className="card border-sig"><div className="lbl text-sig">AI_REQUEST_FAILED</div><p className="mt-2">{res.error}</p><p className="text-t2 text-sm">Pipeline: FAILED. No findings were generated from this step.</p></div>}
      {r && (
        <div className="card space-y-4">
          <div className="flex justify-between"><div><div className="lbl">Prompt</div>{r.text}</div>{res.is_demo && <DemoTag text="DEMO ANALYSIS" />}</div>
          <div><div className="lbl mb-1">AI response</div>{r.ordered_brands.map((b: string, i: number) => <div key={b} className={b.toLowerCase() === product.brand.toLowerCase() ? "text-sig font-bold" : "text-t2"}>{i + 1}. {b}</div>)}</div>
          <div><div className="lbl">Your brand</div><div className={`text-xl font-extrabold ${r.mentioned ? "text-sig" : ""}`}>{r.mentioned ? `✓ MENTIONED · #${r.position ?? "?"}` : "✕ NOT MENTIONED"}</div></div>
          <div><div className="lbl mb-1">Buyer requirements vs product data</div>{r.checks.length ? r.checks.map((c: any) => <div key={c.requirement} className="text-sm"><Mark ok={c.status === "MATCH"} /> {c.requirement}</div>) : <span className="text-t2 text-sm">None recognized</span>}</div>
          {res.findings.filter((f: any) => f.type === "ATTRIBUTE_GAP")[0] && <button className="btn2" onClick={() => setEv(res.findings.filter((f: any) => f.type === "ATTRIBUTE_GAP")[0])}>View evidence →</button>}
        </div>)}
      <div className="card space-y-3">
        <div className="flex flex-wrap justify-between items-center gap-2"><div className="lbl">Buyer prompts (max {cfg.max_prompts})</div><button className="btn2" disabled={!!busy} onClick={generate}>Generate buyer prompts</button></div>
        {note && <p className="text-t3 text-xs">{note}</p>}
        {prompts.map((p, i) => (<div key={i} className="flex gap-2"><input className="inp" value={p} onChange={(e) => setPrompts(prompts.map((x, j) => (j === i ? e.target.value : x)))} aria-label={`Prompt ${i + 1}`} />
          <button className="btn2" onClick={() => setPrompts(prompts.filter((_, j) => j !== i))} aria-label="Delete prompt"><X size={14} /></button></div>))}
        {prompts.length > 0 && <button className="btn" disabled={!!busy} onClick={scan}>Run visibility scan →</button>}
      </div>
    </div>
  );
}

function Findings({ product, setEv, version, go }: any) {
  const [sev, setSev] = useState("ALL");
  const f = useLoad(`/api/products/${product.id}/findings`, [version]);
  if (f.l) return <Loading label="LOADING FINDINGS" />;
  const list = (f.d ?? []).filter((x: any) => sev === "ALL" || x.severity === sev);
  return (
    <div className="space-y-6"><h1 className="text-3xl font-extrabold tracking-tight">Findings</h1>
      <div className="flex gap-2">{["ALL", "HIGH", "MEDIUM", "LOW"].map((s) => <button key={s} onClick={() => setSev(s)} className={`px-3 py-1 text-xs font-semibold tracking-widest border transition duration-200 ${sev === s ? "bg-sig text-bg border-sig" : "border-[#333] text-t2"}`}>{s}</button>)}</div>
      {!f.d?.length ? <Empty title="No findings" body="Run a scan to generate evidence-backed findings." action="Run first scan" onAction={() => go("explorer")} /> :
        list.map((x: any) => (<div key={x.id} className="card flex flex-wrap justify-between gap-3 items-center">
          <div><Sev s={x.severity} /> <span className="lbl ml-2">{x.type.replace(/_/g, " ")}</span><div className="font-bold mt-2">{x.title}</div>
            <div className="text-t2 text-sm">Found in {x.evidence.prompts.length} prompt(s)</div></div>
          <button className="btn2" onClick={() => setEv(x)}>View evidence →</button></div>))}
    </div>
  );
}

function HistoryPage({ product, version, go }: any) {
  const h = useLoad(`/api/products/${product.id}/scans`, [version]);
  const [sel, setSel] = useState<number | null>(null);
  const s = useLoad(sel ? `/api/scans/${sel}` : null, [sel]);
  if (h.l) return <Loading label="LOADING SCANS" />;
  if (!h.d?.length) return <Empty title="No scans yet" body="Run your first visibility scan to understand how AI systems respond to your product." action="Run first scan" onAction={() => go("explorer")} />;
  return (
    <div className="space-y-6"><h1 className="text-3xl font-extrabold tracking-tight">Scan History</h1>
      {h.d.map((x: any) => (<div key={x.id} className="card flex flex-wrap justify-between items-center gap-3">
        <div><div className="lbl">Scan #{x.id} {x.is_demo && <DemoTag />}</div><div className="font-bold">{new Date(x.started_at).toUTCString().slice(5, 22)} UTC · {x.provider}</div>
          <div className="text-t2 text-sm">{x.status === "COMPLETED" ? `${x.metrics.total_prompts} prompts · ${x.metrics.prompts_with_mention} mentions · ${x.metrics.inclusion_rate}% inclusion · ${x.gaps} gaps` : `FAILED · ${x.error}`}</div></div>
        <button className="btn2" onClick={() => setSel(x.id)}>View scan →</button></div>))}
      {sel && s.d && (<div className="card space-y-4"><div className="lbl">Pipeline trace · scan #{s.d.id}</div>
        <div className="font-mono text-sm space-y-1">{s.d.trace.map((t: any, i: number) => (<div key={i}><span className="text-sig">[{t.status === "ok" ? "✓" : t.status === "warn" ? "!" : "✕"}]</span> {t.step} <span className="text-t3">{t.at?.slice(11, 19)} {t.detail && `· ${t.detail}`}</span></div>))}</div>
        {s.d.status === "FAILED" && <p className="text-sig text-sm">Reason: {s.d.error}. No findings were generated from this step.</p>}
        <div className="overflow-x-auto"><table className="w-full text-sm"><thead><tr className="text-t3 text-left"><th className="py-1">Prompt</th><th>Family</th><th>Mentioned</th><th>Pos</th></tr></thead>
          <tbody>{s.d.records.map((r: any) => <tr key={r.prompt_id} className="border-t border-line"><td className="py-2 pr-3">{r.text}</td><td className="text-t2">{r.family}</td><td><Mark ok={r.mentioned} /></td><td>{r.position ?? "—"}</td></tr>)}</tbody></table></div></div>)}
    </div>
  );
}

function ProductPage({ product, setProduct, bump }: any) {
  const blank = { brand: "", name: "", category: "", price: "", product_url: "", attributes: [] as string[] };
  const [f, setF] = useState<any>(blank); const [chip, setChip] = useState(""); const [err, setErr] = useState("");
  const addChip = () => { if (chip.trim()) setF({ ...f, attributes: [...f.attributes, chip.trim()] }); setChip(""); };
  const save = async () => {
    try { const p = await api("/api/products", { method: "POST", body: { ...f, price: f.price === "" ? null : Number(f.price), product_url: f.product_url || null } }); setProduct(p); setF(blank); setErr(""); bump(); }
    catch (e: any) { setErr(e.message); }
  };
  return (
    <div className="space-y-6 mt-10 md:mt-0"><h1 className="text-3xl font-extrabold tracking-tight">Product</h1>
      {product && <div className="card"><div className="lbl">Active product {product.is_demo && <DemoTag />}</div><div className="text-xl font-bold mt-1">{product.brand} · {product.name}</div>
        <div className="text-t2 text-sm">{product.category} · ₹{product.price ?? "—"}</div>
        <div className="flex flex-wrap gap-2 mt-3">{product.attributes.map((a: string) => <span key={a} className="border border-[#333] px-2 py-1 text-xs">{a}</span>)}</div></div>}
      <div className="card space-y-3"><div className="lbl">Create a product profile</div>
        {(["brand", "name", "category", "price", "product_url"] as const).map((k) => <input key={k} className="inp" placeholder={k.replace("_", " ")} value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} aria-label={k} />)}
        <div className="flex gap-2"><input className="inp" placeholder="attribute, e.g. no white cast" value={chip} onChange={(e) => setChip(e.target.value)} onKeyDown={(e) => e.key === "Enter" && addChip()} /><button className="btn2" onClick={addChip}>Add</button></div>
        <div className="flex flex-wrap gap-2">{f.attributes.map((a: string, i: number) => <button key={i} className="border border-sig text-sig px-2 py-1 text-xs" onClick={() => setF({ ...f, attributes: f.attributes.filter((_: any, j: number) => j !== i) })}>{a} ×</button>)}</div>
        {err && <p className="text-sig text-sm">{err}</p>}
        <button className="btn" disabled={!f.brand || !f.name || !f.category} onClick={save}>Save product →</button></div>
    </div>
  );
}
