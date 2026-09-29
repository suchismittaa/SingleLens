"""Deterministic judge. Nothing in here calls an LLM."""
import re
from collections import Counter

# canonical key -> (aliases, kind)
LEXICON = {
    "oily skin": (["oily"], "skin"),
    "dry skin": (["dry skin"], "skin"),
    "sensitive skin": (["sensitive"], "skin"),
    "combination skin": (["combination skin"], "skin"),
    "acne-prone skin": (["acne"], "problem"),
    "no white cast": (["white cast"], "problem"),
    "fragrance-free": (["fragrance-free", "fragrance free", "unscented"], "feature"),
    "lightweight": (["lightweight", "light weight", "non-greasy", "non greasy"], "feature"),
    "spf 50": (["spf 50", "spf50"], "feature"),
    "pa++++": (["pa++++"], "feature"),
    "matte finish": (["matte"], "feature"),
    "water resistant": (["waterproof", "water resistant", "water-resistant"], "feature"),
}
PRICE_RE = re.compile(r"(?:under|below|less than|within|upto|up to)\s*(?:₹|rs\.?|inr)?\s*(\d[\d,]*)", re.I)
FAMILIES = ["GENERAL", "PRICE-SENSITIVE", "SKIN-TYPE", "PROBLEM-SPECIFIC", "FEATURE-SPECIFIC"]


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.lower().strip())


def canonical_keys(text: str) -> list[str]:
    t = norm(text)
    return [k for k, (al, _) in LEXICON.items() if k in t or any(a in t for a in al)]


def extract_requirements(prompt: str) -> list[dict]:
    reqs = [{"key": k, "kind": LEXICON[k][1]} for k in canonical_keys(prompt)]
    m = PRICE_RE.search(prompt)
    if m:
        limit = int(m.group(1).replace(",", ""))
        reqs.append({"key": f"under ₹{limit}", "kind": "price", "limit": limit})
    return reqs


def check_requirements(reqs: list[dict], attributes: list[str], price: float | None) -> list[dict]:
    have: set[str] = set()
    for a in attributes:
        have.add(norm(a))
        have.update(canonical_keys(a))
    out = []
    for r in reqs:
        ok = (price is not None and price <= r["limit"]) if r["kind"] == "price" else r["key"] in have
        out.append({"requirement": r["key"], "status": "MATCH" if ok else "MISSING"})
    return out


def classify_prompt(text: str) -> str:
    kinds = {r["kind"] for r in extract_requirements(text)}
    for kind, fam in [("price", "PRICE-SENSITIVE"), ("skin", "SKIN-TYPE"), ("problem", "PROBLEM-SPECIFIC"), ("feature", "FEATURE-SPECIFIC")]:
        if kind in kinds:
            return fam
    return "GENERAL"


def same_brand(a: str, b: str) -> bool:
    return norm(a) == norm(b)


def evaluate_response(analysis, brand: str):
    mine = [b for b in analysis.brands if b.mentioned and same_brand(b.brand_name, brand)]
    comps: list[str] = []
    for b in analysis.brands:
        if b.mentioned and not same_brand(b.brand_name, brand) and b.brand_name not in comps:
            comps.append(b.brand_name)
    return bool(mine), (mine[0].position if mine else None), comps


def pct(n: int, d: int):
    return round(100 * n / d, 1) if d else None


def inclusion_rate(mentioned: int, analyzed: int):
    return pct(mentioned, analyzed)


def average_position(positions):
    ps = [p for p in positions if p is not None]
    return round(sum(ps) / len(ps), 2) if ps else None


def competitor_frequency(records) -> list[dict]:
    c = Counter(name for r in records for name in r["competitors"])
    return [{"brand": b, "prompts": n} for b, n in sorted(c.items(), key=lambda x: (-x[1], x[0]))]


def attribute_coverage(checks: list[dict]):
    return pct(sum(1 for c in checks if c["status"] == "MATCH"), len(checks))


def severity_for_count(n: int) -> str:
    return "HIGH" if n >= 4 else "MEDIUM" if n >= 2 else "LOW"


def build_findings(records: list[dict], product: dict) -> list[dict]:
    """records: prompt_id,text,mentioned,position,competitors,checks. Returns finding dicts."""
    findings = []
    missed = [r for r in records if not r["mentioned"]]
    ctx = lambda rs: [{k: r[k] for k in ("prompt_id", "text", "mentioned", "position", "competitors", "checks")} for r in rs]
    base = {"product_attributes": product["attributes"], "product_price": product["price"]}

    for r in missed:
        findings.append({"type": "BRAND_NOT_MENTIONED", "severity": "LOW", "prompt_id": r["prompt_id"],
                         "title": "Brand absent from AI response",
                         "description": "The brand was not mentioned in this analyzed response.",
                         "evidence": {**base, "prompts": ctx([r])}})

    gaps: dict[str, list[dict]] = {}
    for r in missed:
        for c in r["checks"]:
            if c["status"] == "MISSING":
                gaps.setdefault(c["requirement"], []).append(r)
    for sig, rs in sorted(gaps.items(), key=lambda x: (-len(x[1]), x[0])):
        findings.append({"type": "ATTRIBUTE_GAP", "severity": severity_for_count(len(rs)), "prompt_id": rs[0]["prompt_id"],
                         "title": f'Missing product attribute: "{sig}"',
                         "description": f'"{sig}" appears in {len(rs)} buyer prompt(s) where the brand was not mentioned, '
                                        "and is not explicitly represented in the product information. "
                                        "This is a potential visibility gap and may be a contributing signal; causation is not established.",
                         "evidence": {**base, "required_signal": sig, "observed_in_product": False, "prompts": ctx(rs)}})

    rate = inclusion_rate(len(records) - len(missed), len(records))
    if rate is not None and rate < 70:
        findings.append({"type": "LOW_PROMPT_COVERAGE", "severity": "HIGH" if rate < 50 else "MEDIUM", "prompt_id": None,
                         "title": f"Low prompt coverage ({rate}% inclusion)",
                         "description": f"The brand appeared in {len(records) - len(missed)} of {len(records)} analyzed prompts.",
                         "evidence": {**base, "prompts": ctx(missed)}})

    for cf in competitor_frequency(missed):
        if cf["prompts"] >= 3:
            rs = [r for r in missed if cf["brand"] in r["competitors"]]
            findings.append({"type": "COMPETITOR_DOMINANCE", "severity": "HIGH" if cf["prompts"] >= 5 else "MEDIUM", "prompt_id": None,
                             "title": f'{cf["brand"]} appears in {cf["prompts"]} prompts where the brand does not',
                             "description": "Observation of co-occurrence only. This is not a quality ranking.",
                             "evidence": {**base, "competitor": cf["brand"], "prompts": ctx(rs)}})
    return findings
