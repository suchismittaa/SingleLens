import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from . import service
from .config import settings
from .db import SessionLocal, engine, get_db
from .models import Base, Brand, Finding, Product, Prompt, Scan
from .providers import DemoProvider, ProviderError, get_ai_provider
from .schemas import AnalyzeIn, GenerateIn, ProductIn, ProductOut, PromptIn, ScanIn
from .analysis import classify_prompt


@asynccontextmanager
async def lifespan(app):
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        s = service.seed(db)
        if s:  # demo scan runs through the normal pipeline using DemoProvider only
            p, prov = s
            texts = await prov.generate_prompts("Minimalist", p.name, p.category, settings.MAX_PROMPTS_PER_SCAN)
            await service.run_scan(db, p, texts, prov)
    yield


app = FastAPI(title="SignalLens", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")], allow_methods=["*"], allow_headers=["*"])


def provider_for(mode):
    try:
        return get_ai_provider(mode)
    except ProviderError as e:
        raise HTTPException(400, {"code": e.code, "reason": e.reason})


def get_product(db: Session, pid: int) -> Product:
    p = db.get(Product, pid)
    if not p:
        raise HTTPException(404, "Product not found")
    return p


def product_out(db, p):
    b = db.get(Brand, p.brand_id)
    demo = p.product_url == "https://example.com/product" and b.name == "Minimalist"
    return ProductOut(id=p.id, brand=b.name, name=p.name, category=p.category, price=p.price, product_url=p.product_url, attributes=p.attributes, is_demo=demo)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/config")
def config():
    return {"default_provider": settings.AI_PROVIDER, "gemini_available": bool(settings.GEMINI_API_KEY), "max_prompts": settings.MAX_PROMPTS_PER_SCAN}


@app.get("/api/products", response_model=list[ProductOut])
def list_products(db: Session = Depends(get_db)):
    return [product_out(db, p) for p in db.query(Product).order_by(Product.id).all()]


@app.post("/api/products", response_model=ProductOut, status_code=201)
def create_product(body: ProductIn, db: Session = Depends(get_db)):
    b = db.query(Brand).filter_by(name=body.brand.strip()).first() or Brand(name=body.brand.strip())
    db.add(b); db.flush()
    attrs = list(dict.fromkeys(a.strip() for a in body.attributes if a.strip()))
    p = Product(brand_id=b.id, name=body.name.strip(), category=body.category.strip(), price=body.price, attributes=attrs, product_url=body.product_url)
    db.add(p); db.commit()
    return product_out(db, p)


@app.get("/api/products/{pid}", response_model=ProductOut)
def read_product(pid: int, db: Session = Depends(get_db)):
    return product_out(db, get_product(db, pid))


@app.post("/api/prompts/generate")
async def generate_prompts(body: GenerateIn, db: Session = Depends(get_db)):
    p = get_product(db, body.product_id)
    prov = provider_for(body.mode)
    brand = db.get(Brand, p.brand_id).name
    try:
        raw = await prov.generate_prompts(brand, p.name, p.category, settings.MAX_PROMPTS_PER_SCAN)
    except ProviderError as e:
        raise HTTPException(502, {"code": e.code, "reason": e.reason})
    clean, rejected = service.validate_prompts(raw, p, settings.MAX_PROMPTS_PER_SCAN)
    return {"provider": prov.name, "is_demo": prov.is_demo, "prompts": [{"text": t, "category": classify_prompt(t)} for t in clean], "rejected": rejected}


@app.get("/api/products/{pid}/prompts")
def list_prompts(pid: int, db: Session = Depends(get_db)):
    get_product(db, pid)
    return [{"id": r.id, "text": r.text, "category": r.category} for r in db.query(Prompt).filter_by(product_id=pid).order_by(Prompt.id)]


@app.post("/api/products/{pid}/prompts", status_code=201)
def create_prompt(pid: int, body: PromptIn, db: Session = Depends(get_db)):
    p = get_product(db, pid)
    clean, rej = service.validate_prompts([body.text], p, 1)
    if not clean:
        raise HTTPException(422, rej[0]["reason"])
    r = db.query(Prompt).filter_by(product_id=pid, text=clean[0]).first()
    if not r:
        r = Prompt(product_id=pid, text=clean[0], category=classify_prompt(clean[0])); db.add(r); db.commit()
    return {"id": r.id, "text": r.text, "category": r.category}


@app.post("/api/prompts/{prompt_id}/analyze")
async def analyze_prompt(prompt_id: int, body: AnalyzeIn, db: Session = Depends(get_db)):
    pr = db.get(Prompt, prompt_id)
    if not pr:
        raise HTTPException(404, "Prompt not found")
    scan = await service.run_scan(db, get_product(db, pr.product_id), [pr.text], provider_for(body.mode), kind="single")
    return service.scan_detail(db, scan)


@app.post("/api/scans", status_code=201)
async def create_scan(body: ScanIn, db: Session = Depends(get_db)):
    p = get_product(db, body.product_id)
    prov = provider_for(body.mode)
    clean, rejected = service.validate_prompts(body.prompts, p, settings.MAX_PROMPTS_PER_SCAN)
    if not clean:
        raise HTTPException(422, {"code": "INVALID_INPUT", "reason": "No valid prompts", "rejected": rejected})
    scan = await service.run_scan(db, p, clean, prov)
    d = service.scan_detail(db, scan)
    d["rejected_prompts"] = rejected
    return d


@app.get("/api/scans/{sid}")
def read_scan(sid: int, db: Session = Depends(get_db)):
    s = db.get(Scan, sid)
    if not s:
        raise HTTPException(404, "Scan not found")
    return service.scan_detail(db, s)


@app.get("/api/products/{pid}/scans")
def list_scans(pid: int, db: Session = Depends(get_db)):
    get_product(db, pid)
    out = []
    for s in db.query(Scan).filter_by(product_id=pid, kind="full").order_by(Scan.id.desc()):
        d = service.scan_detail(db, s)
        out.append({"id": s.id, "status": s.status, "provider": s.provider, "is_demo": d["is_demo"], "started_at": d["started_at"],
                    "error": s.error, "metrics": d["metrics"], "gaps": d["metrics"]["visibility_gaps"] if d["metrics"] else None})
    return out


def latest_scan(db, pid):
    return db.query(Scan).filter_by(product_id=pid, kind="full", status="COMPLETED").order_by(Scan.id.desc()).first()


@app.get("/api/products/{pid}/metrics")
def metrics(pid: int, db: Session = Depends(get_db)):
    get_product(db, pid)
    s = latest_scan(db, pid)
    if not s:
        raise HTTPException(404, "No completed scans yet")
    d = service.scan_detail(db, s)
    return {"scan_id": s.id, "provider": s.provider, "scan_time": d["completed_at"], **d["metrics"]}


@app.get("/api/products/{pid}/findings")
def findings(pid: int, scan_id: int | None = None, severity: str | None = None, db: Session = Depends(get_db)):
    get_product(db, pid)
    s = db.get(Scan, scan_id) if scan_id else latest_scan(db, pid)
    if not s:
        return []
    q = db.query(Finding).filter_by(scan_id=s.id)
    if severity:
        q = q.filter_by(severity=severity.upper())
    return [service.finding_out(f, s) for f in q.order_by(Finding.id)]
