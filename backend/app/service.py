from datetime import datetime, timezone

from sqlalchemy.orm import Session

from .analysis import (FAMILIES, average_position, build_findings, check_requirements, classify_prompt,
                       competitor_frequency, evaluate_response, extract_requirements, inclusion_rate, pct)
from .config import settings
from .models import AiResponse, Brand, Finding, Product, Prompt, Scan
from .providers import AIProvider, ProviderError
from .schemas import AIResponseAnalysis


def iso(d):
    return d.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z") if d else None


def validate_prompts(texts: list[str], product: Product, limit: int):
    clean, rejected, seen = [], [], set()
    words = {w for w in (product.category + " " + product.name).lower().split() if len(w) >= 4}
    for raw in texts:
        t = " ".join(str(raw).split())
        low = t.lower()
        if not t: reason = "empty"
        elif not 8 <= len(t) <= 200: reason = "length must be 8-200 characters"
        elif low in seen: reason = "duplicate"
        elif not any(w in low for w in words): reason = "not relevant to product/category"
        else:
            seen.add(low); clean.append(t); continue
        rejected.append({"text": t, "reason": reason})
    if len(clean) > limit:
        rejected += [{"text": t, "reason": f"over MAX_PROMPTS_PER_SCAN ({limit})"} for t in clean[limit:]]
        clean = clean[:limit]
    return clean, rejected


def product_ctx(db: Session, p: Product) -> dict:
    b = db.get(Brand, p.brand_id)
    return {"brand": b.name, "attributes": p.attributes or [], "price": p.price}


async def run_scan(db: Session, product: Product, texts: list[str], provider: AIProvider, kind="full") -> Scan:
    scan = Scan(product_id=product.id, status="RUNNING", kind=kind, provider=provider.name, trace=[])
    db.add(scan); db.commit()
    trace = []

    def step(name, status="ok", detail=None):
        trace.append({"step": name, "status": status, "detail": detail, "at": iso(datetime.now(timezone.utc))})

    prompts = []
    for t in texts:
        p = db.query(Prompt).filter_by(product_id=product.id, text=t).first()
        if not p:
            p = Prompt(product_id=product.id, text=t, category=classify_prompt(t)); db.add(p); db.flush()
        prompts.append(p)
    step("PROMPTS_GENERATED", detail=f"{len(prompts)} prompts")

    ctx = product_ctx(db, product)
    seen = set()
    for p in prompts:
        if p.id in seen:  # cost safety: never call the model twice for the same prompt in one scan
            continue
        seen.add(p.id)
        try:
            a = await provider.analyze_prompt(p.text)
            AIResponseAnalysis.model_validate(a.model_dump())
        except ProviderError as e:
            step(e.code, "failed", e.reason)
            step("PIPELINE", "failed", "No findings were generated from this step.")
            scan.status, scan.error, scan.trace, scan.completed_at = "FAILED", f"{e.code}: {e.reason}", trace, datetime.now(timezone.utc)
            db.commit(); return scan
        db.add(AiResponse(scan_id=scan.id, prompt_id=p.id, provider=provider.name, raw_response=a.raw_response,
                          structured_response=a.model_dump(), status="VALIDATED"))
    db.flush()
    step("AI_REQUEST_COMPLETED"); step("SCHEMA_VALIDATED"); step("BRAND_EXTRACTION"); step("ATTRIBUTE_EXTRACTION")

    records = build_records(db, scan, ctx, product)
    findings = build_findings(records, ctx)
    step("DETERMINISTIC_ANALYSIS")
    gaps = [f for f in findings if f["type"] == "ATTRIBUTE_GAP"]
    step("VISIBILITY_GAP_DETECTED", "warn" if gaps else "ok", f"{len(gaps)} attribute gap(s)")
    for f in findings:
        db.add(Finding(scan_id=scan.id, **f))
    step("FINDING_STORED", detail=f"{len(findings)} finding(s)")
    scan.status, scan.trace, scan.completed_at = "COMPLETED", trace, datetime.now(timezone.utc)
    db.commit()
    return scan


def build_records(db: Session, scan: Scan, ctx: dict, product: Product) -> list[dict]:
    rows = (db.query(AiResponse, Prompt).join(Prompt, Prompt.id == AiResponse.prompt_id)
            .filter(AiResponse.scan_id == scan.id, AiResponse.status == "VALIDATED").order_by(Prompt.id).all())
    out = []
    for r, p in rows:
        a = AIResponseAnalysis(**r.structured_response)
        mentioned, pos, comps = evaluate_response(a, ctx["brand"])
        checks = check_requirements(extract_requirements(p.text), ctx["attributes"], ctx["price"])
        out.append({"prompt_id": p.id, "text": p.text, "family": p.category, "mentioned": mentioned, "position": pos,
                    "competitors": comps, "checks": checks, "provider": r.provider, "raw_response": r.raw_response,
                    "ordered_brands": [b.brand_name for b in a.brands if b.mentioned], "relevant_attributes": a.relevant_attributes,
                    "time": iso(r.created_at), "status": "Validated"})
    return out


def compute_metrics(records: list[dict], findings: list, provider: str) -> dict:
    total = len(records)
    hit = [r for r in records if r["mentioned"]]
    gaps = [f for f in findings if f.type == "ATTRIBUTE_GAP"]
    top = max(gaps, key=lambda f: len(f.evidence["prompts"]), default=None)
    fam = {}
    for name in FAMILIES:
        rs = [r for r in records if r["family"] == name]
        fam[name] = {"rate": inclusion_rate(sum(r["mentioned"] for r in rs), len(rs)), "mentioned": sum(r["mentioned"] for r in rs), "total": len(rs)}
    return {
        "inclusion_rate": inclusion_rate(len(hit), total), "prompts_with_mention": len(hit), "total_prompts": total,
        "average_position": average_position([r["position"] for r in hit]), "missed": total - len(hit), "visibility_gaps": len(gaps),
        "top_gap": {"signal": top.evidence["required_signal"], "count": len(top.evidence["prompts"]), "finding_id": top.id} if top else None,
        "families": fam, "competitors": competitor_frequency(records),
        "surfaces": [{"surface": provider, "inclusion_rate": inclusion_rate(len(hit), total),
                      "average_position": average_position([r["position"] for r in hit]), "demo": provider == "demo"}],
        "is_demo": provider == "demo",
    }


def finding_out(f: Finding, scan: Scan) -> dict:
    ev = dict(f.evidence)
    ev["scan"] = {"id": scan.id, "time": iso(scan.completed_at), "provider": scan.provider, "status": "Validated" if scan.status == "COMPLETED" else scan.status}
    return {"id": f.id, "scan_id": f.scan_id, "prompt_id": f.prompt_id, "type": f.type, "severity": f.severity,
            "title": f.title, "description": f.description, "evidence": ev, "created_at": iso(f.created_at)}


def scan_detail(db: Session, scan: Scan) -> dict:
    product = db.get(Product, scan.product_id)
    ctx = product_ctx(db, product)
    records = build_records(db, scan, ctx, product)
    fs = db.query(Finding).filter_by(scan_id=scan.id).order_by(Finding.id).all()
    return {"id": scan.id, "product_id": scan.product_id, "status": scan.status, "kind": scan.kind, "provider": scan.provider,
            "is_demo": scan.provider == "demo", "error": scan.error, "started_at": iso(scan.started_at), "completed_at": iso(scan.completed_at),
            "trace": scan.trace, "records": records, "findings": [finding_out(f, scan) for f in fs],
            "metrics": compute_metrics(records, fs, scan.provider) if scan.status == "COMPLETED" else None}


def seed(db: Session):
    if db.query(Product).count():
        return
    b = Brand(name="Minimalist"); db.add(b); db.flush()
    p = Product(brand_id=b.id, name="SPF 50 Sunscreen", category="Sunscreen", price=499,
                attributes=["SPF 50", "PA++++", "Oily skin", "Fragrance-free", "Lightweight"], product_url="https://example.com/product")
    db.add(p); db.commit()
    from .providers import DemoProvider
    return p, DemoProvider()
