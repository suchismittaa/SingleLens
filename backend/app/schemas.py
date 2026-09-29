from pydantic import BaseModel, Field, HttpUrl, model_validator


class BrandMention(BaseModel):
    brand_name: str = Field(min_length=1)
    mentioned: bool
    position: int | None = Field(default=None, ge=1)
    reason: str | None = None

    @model_validator(mode="after")
    def _pos(self):
        if not self.mentioned and self.position is not None:
            raise ValueError("position set on a brand that is not mentioned")
        return self


class AIResponseAnalysis(BaseModel):
    prompt: str
    brands: list[BrandMention]
    relevant_attributes: list[str] = []
    raw_response: str = Field(min_length=1)


class ProductIn(BaseModel):
    brand: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=200)
    category: str = Field(min_length=1, max_length=100)
    price: float | None = Field(default=None, ge=0)
    product_url: str | None = None
    attributes: list[str] = []


class ProductOut(ProductIn):
    id: int
    is_demo: bool = False


class GenerateIn(BaseModel):
    product_id: int
    mode: str | None = None


class PromptIn(BaseModel):
    text: str


class AnalyzeIn(BaseModel):
    mode: str | None = None


class ScanIn(BaseModel):
    product_id: int
    prompts: list[str]
    mode: str | None = None
