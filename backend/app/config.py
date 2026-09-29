import os


class Settings:
    DATABASE_URL = (os.getenv("DATABASE_URL", "postgresql+psycopg2://postgres:postgres@localhost:5432/signallens")
                    .replace("postgres://", "postgresql://", 1).replace("postgresql://", "postgresql+psycopg2://", 1))
    AI_PROVIDER = os.getenv("AI_PROVIDER", "demo").lower()
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    MAX_PROMPTS_PER_SCAN = int(os.getenv("MAX_PROMPTS_PER_SCAN", "10"))


settings = Settings()
