import asyncio
import os

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["AI_PROVIDER"] = "demo"

import pytest
from fastapi.testclient import TestClient

from app import service
from app.analysis import (attribute_coverage, average_position, build_findings, check_requirements, extract_requirements, inclusion_rate)
from app.main import app
from app.providers import AIProvider, GeminiProvider, ProviderError, get_ai_provider
from app.schemas import AIResponseAnalysis


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_inclusion_rate():
    assert inclusion_rate(3, 5) == 60.0


def test_average_position_ignores_missing():
    assert average_position([1, 2, 3]) == 2
    assert average_position([1, None, 3]) == 2
    assert average_position([None]) is None


def test_attribute_match():
    r = check_requirements(extract_requirements("best sunscreen for oily skin"), ["Oily skin"], 499)
    assert r == [{"requirement": "oily skin", "status": "MATCH"}]
    assert attribute_coverage(r) == 100.0


def test_price_match_and_gap_finding():
    checks = check_requirements(extract_requirements("sunscreen without white cast under ₹500"), ["SPF 50"], 499)
    assert {c["requirement"]: c["status"] for c in checks} == {"no white cast": "MISSING", "under ₹500": "MATCH"}
    rec = [{"prompt_id": 1, "text": "x", "mentioned": False, "position": None, "competitors": ["A"], "checks": checks}]
    f = build_findings(rec, {"attributes": ["SPF 50"], "price": 499})
    gap = [x for x in f if x["type"] == "ATTRIBUTE_GAP"][0]
    assert gap["evidence"]["required_signal"] == "no white cast" and gap["evidence"]["observed_in_product"] is False
    assert "causation is not established" in gap["description"]


def test_duplicate_prompts_rejected(client):
    p = client.get("/api/products").json()[0]
    from app.db import SessionLocal
    from app.models import Product
    with SessionLocal() as db:
        clean, rej = service.validate_prompts(["best sunscreen for oily skin", "Best Sunscreen for oily skin", "hi", "best shoes for running"], db.get(Product, p["id"]), 10)
    assert clean == ["best sunscreen for oily skin"]
    assert {r["reason"] for r in rej} >= {"duplicate", "not relevant to product/category"}


def test_invalid_llm_output_is_failed_validation():
    with pytest.raises(Exception):
        AIResponseAnalysis(prompt="p", brands=[{"brand_name": "A", "mentioned": False, "position": 2}], raw_response="x")

    class Bad(GeminiProvider):
        async def _json(self, text):
            return {"brands": "nope"}
    with pytest.raises(ProviderError) as e:
        asyncio.run(Bad("k", "m").analyze_prompt("best sunscreen"))
    assert e.value.code == "FAILED_VALIDATION"


def test_failed_scan_creates_no_findings(client):
    class Failing(AIProvider):
        name = "gemini"
        async def generate_prompts(self, *a): return []
        async def analyze_prompt(self, prompt): raise ProviderError("AI_REQUEST_FAILED", "API timeout")
    from app.db import SessionLocal
    from app.models import Finding, Product
    with SessionLocal() as db:
        p = db.query(Product).first()
        scan = asyncio.run(service.run_scan(db, p, ["best sunscreen for oily skin"], Failing()))
        assert scan.status == "FAILED" and "API timeout" in scan.error
        assert db.query(Finding).filter_by(scan_id=scan.id).count() == 0
        assert any(t["step"] == "AI_REQUEST_FAILED" for t in scan.trace)


def test_gemini_without_key_is_unavailable():
    with pytest.raises(ProviderError):
        get_ai_provider("gemini")


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_seeded_demo_metrics_traceable(client):
    p = client.get("/api/products").json()[0]
    assert p["is_demo"]
    m = client.get(f"/api/products/{p['id']}/metrics").json()
    assert m["is_demo"] and m["provider"] == "demo"
    assert m["inclusion_rate"] == round(100 * m["prompts_with_mention"] / m["total_prompts"], 1)
    scan = client.get(f"/api/scans/{m['scan_id']}").json()
    assert sum(r["mentioned"] for r in scan["records"]) == m["prompts_with_mention"]
    assert scan["trace"][-1]["step"] == "FINDING_STORED"


def test_scan_endpoint_validation(client):
    p = client.get("/api/products").json()[0]
    assert client.post("/api/scans", json={"product_id": p["id"], "prompts": ["", "hi"]}).status_code == 422
    assert client.post("/api/scans", json={"product_id": 999, "prompts": ["x"]}).status_code == 404
    assert client.post("/api/scans", json={"product_id": p["id"], "prompts": ["best sunscreen"], "mode": "gemini"}).status_code == 400
