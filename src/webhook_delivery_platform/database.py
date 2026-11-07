from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from webhook_delivery_platform.config import get_settings

settings = get_settings()

engine = create_engine(
    settings.app_database_url,
    pool_pre_ping=True,
)

SessionFactory = sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
)
