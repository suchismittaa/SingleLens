from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from .config import settings

kw = {}
if settings.DATABASE_URL.startswith("sqlite"):
    kw = {"connect_args": {"check_same_thread": False}, "poolclass": StaticPool}
engine = create_engine(settings.DATABASE_URL, **kw)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
