from functools import lru_cache

from cryptography.fernet import Fernet
from pydantic import SecretStr, field_validator
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

    destination_encryption_key: SecretStr

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

    @field_validator("destination_encryption_key")
    @classmethod
    def validate_destination_encryption_key(
        cls,
        value: SecretStr,
    ) -> SecretStr:
        """Ensure the configured encryption key is a valid Fernet key."""

        try:
            Fernet(value.get_secret_value())
        except (ValueError, UnicodeError) as exc:
            raise ValueError(
                "DESTINATION_ENCRYPTION_KEY must be a valid Fernet key."
            ) from exc

        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
