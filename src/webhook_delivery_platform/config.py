from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    postgres_db: str
    postgres_host: str = "127.0.0.1"
    postgres_port: int = 5432

    app_db_user: str
    app_db_password: SecretStr

    migration_db_user: str
    migration_db_password: SecretStr

    @property
    def app_database_url(self) -> URL:
        return URL.create(
            drivername="postgresql+psycopg",
            username=self.app_db_user,
            password=self.app_db_password.get_secret_value(),
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        )

    @property
    def migration_database_url(self) -> URL:
        return URL.create(
            drivername="postgresql+psycopg",
            username=self.migration_db_user,
            password=self.migration_db_password.get_secret_value(),
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
