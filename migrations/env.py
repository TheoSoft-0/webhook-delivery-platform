from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from webhook_delivery_platform.config import get_settings
from webhook_delivery_platform.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = get_settings()

target_metadata = Base.metadata


def include_name(name, type_, parent_names):
    """Restrict database inspection to our application schema."""

    if type_ == "schema":
        return name == "webhook"

    return True


def run_migrations_offline() -> None:
    """Generate migration SQL without opening a database connection."""

    context.configure(
        url=settings.migration_database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_schemas=True,
        include_name=include_name,
        version_table_schema="webhook",
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations using a live database connection."""

    engine = create_engine(
        settings.migration_database_url,
        poolclass=pool.NullPool,
    )

    try:
        with engine.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                include_schemas=True,
                include_name=include_name,
                version_table_schema="webhook",
                compare_type=True,
            )

            with context.begin_transaction():
                context.run_migrations()

    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
