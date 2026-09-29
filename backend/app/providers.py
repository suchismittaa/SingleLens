"""AI provider isolation. The rest of the app only calls get_ai_provider(...) and the AIProvider interface."""
import hashlib
import json
from abc import ABC, abstractmethod

import httpx
from pydantic import ValidationError

from .config import settings
from .schemas import AIResponseAnalysis


class ProviderError(Exception):
    def __init__(self, code: str, reason: str):
        super().__init__(f"{code}: {reason}")
        self.code, self.reason = code, reason


class AIProvider(ABC):
    name = "base"
    is_demo = False

    @abstractmethod
    async def generate_prompts(self, brand: str, product: str, category: str, n: int) -> list[str]: ...

    @abstractmethod
    async def analyze_prompt(self, prompt: str) -> AIResponseAnalysis: ...


DEMO_BRAND = "Minimalist"
DEMO_COMPETITORS = ["Aqualogica", "Dot & Key", "Lakmé Sun Expert", "Neutrogena", "La Shield", "Re'equil", "Derma Co"]
DEMO_TEMPLATES = [
    "best {c} for oily skin", "best {c} under ₹500", "best {c} without white cast", "best {c} for acne-prone skin",
    "best Indian {c} for sensitive skin", "lightweight SPF 50 {c}", "best fragrance-free {c}",
    "best {c} for daily use", "best matte finish {c} for oily skin", "best {c} under ₹300",
]


class DemoProvider(AIProvider):
    """Deterministic canned responses. Never a live measurement."""
    name, is_demo = "demo", True

    async def generate_prompts(self, brand, product, category, n):
        return [t.format(c=category.lower()) for t in DEMO_TEMPLATES][:n]

    async def analyze_prompt(self, prompt):
        h = int(hashlib.sha256(prompt.encode()).hexdigest(), 16)
        comps = [DEMO_COMPETITORS[(h + i * 3) % len(DEMO_COMPETITORS)] for i in range(4)]
        comps = list(dict.fromkeys(comps))
        low = prompt.lower()
        absent = "white cast" in low or "acne" in low or "300" in low
        order = comps[:3] if absent else comps[:2] + [DEMO_BRAND]
        if not absent:
            order.insert(h % 3, order.pop())
        brands = [{"brand_name": b, "mentioned": True, "position": i + 1, "reason": "Demo sample"} for i, b in enumerate(order)]
        attrs = [a for a in ["oily skin", "sensitive skin", "acne-prone skin", "no white cast", "lightweight", "spf 50", "fragrance-free"] if a.split()[-1].lower() in low or a in low]
        raw = "DEMO SAMPLE: " + "; ".join(f"{i + 1}. {b}" for i, b in enumerate(order))
        return AIResponseAnalysis(prompt=prompt, brands=brands, relevant_attributes=attrs, raw_response=raw)


class GeminiProvider(AIProvider):
    name = "gemini"
    URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    def __init__(self, api_key: str, model: str):
        self.api_key, self.model = api_key, model

    async def _json(self, text: str):
        body = {"contents": [{"parts": [{"text": text}]}], "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2}}
        try:
            async with httpx.AsyncClient(timeout=30) as c:
                r = await c.post(self.URL.format(model=self.model), json=body, headers={"x-goog-api-key": self.api_key})
        except httpx.TimeoutException:
            raise ProviderError("AI_REQUEST_FAILED", "API timeout")
        except httpx.HTTPError as e:
            raise ProviderError("AI_REQUEST_FAILED", f"Network error: {type(e).__name__}")
        if r.status_code == 429:
            raise ProviderError("AI_REQUEST_FAILED", "Rate limited or free quota exhausted")
        if r.status_code >= 400:
            raise ProviderError("AI_REQUEST_FAILED", f"Gemini returned HTTP {r.status_code}")
        try:
            out = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, ValueError):
            raise ProviderError("AI_REQUEST_FAILED", "Empty response")
        if not out.strip():
            raise ProviderError("AI_REQUEST_FAILED", "Empty response")
        try:
            return json.loads(out)
        except ValueError:
            raise ProviderError("FAILED_VALIDATION", "Response was not valid JSON")

    async def generate_prompts(self, brand, product, category, n):
        data = await self._json(
            f"Write {n} short, distinct questions a shopper might ask an AI assistant when looking for a {category} "
            f"(product type like: {product}). Do not name any brand. Return ONLY JSON: {{\"prompts\": [string]}}")
        if not isinstance(data, dict) or not isinstance(data.get("prompts"), list):
            raise ProviderError("FAILED_VALIDATION", "Expected {'prompts': [...]}")
        return [str(p) for p in data["prompts"]]

    async def analyze_prompt(self, prompt):
        data = await self._json(
            "Act as a shopping assistant answering the question below. Recommend up to 6 specific real brands, best first. "
            'Return ONLY JSON: {"raw_response": string, "brands": [{"brand_name": string, "mentioned": true, "position": int, "reason": string}], '
            '"relevant_attributes": [string]}. Question: ' + prompt)
        try:
            a = AIResponseAnalysis(prompt=prompt, **data)
        except (ValidationError, TypeError) as e:
            raise ProviderError("FAILED_VALIDATION", f"Schema validation failed: {str(e)[:200]}")
        if not a.brands:
            raise ProviderError("FAILED_VALIDATION", "No brands returned")
        return a


def get_ai_provider(name: str | None = None) -> AIProvider:
    name = (name or settings.AI_PROVIDER).lower()
    if name == "demo":
        return DemoProvider()
    if name == "gemini":
        if not settings.GEMINI_API_KEY:
            raise ProviderError("PROVIDER_UNAVAILABLE", "GEMINI_API_KEY is not set. Demo mode is available.")
        return GeminiProvider(settings.GEMINI_API_KEY, settings.GEMINI_MODEL)
    raise ProviderError("PROVIDER_UNAVAILABLE", f"Unknown provider '{name}'")
