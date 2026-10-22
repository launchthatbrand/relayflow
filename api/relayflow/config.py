from urllib.parse import quote

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str | None = None
    celery_broker_url: str | None = None
    celery_result_backend: str = "redis://localhost:6379/0"
    postgres_password: str | None = None
    rabbitmq_password: str | None = None
    webhook_secret: str = "dev-webhook-secret"
    retry_base_seconds: float = Field(default=1, validation_alias="RELAY_RETRY_BASE_SECONDS")

    @model_validator(mode="after")
    def fill_urls(self):
        if not self.database_url:
            if self.postgres_password:
                password = quote(self.postgres_password, safe="")
                self.database_url = f"postgresql+psycopg://relay:{password}@relayflow-postgres:5432/relayflow"
            else:
                self.database_url = "postgresql+psycopg://relay:relay@localhost:5432/relayflow"
        if not self.celery_broker_url:
            if self.rabbitmq_password:
                password = quote(self.rabbitmq_password, safe="")
                self.celery_broker_url = f"amqp://relay:{password}@relayflow-rabbitmq:5672//"
            else:
                self.celery_broker_url = "amqp://guest:guest@localhost:5672//"
        return self


settings = Settings()
