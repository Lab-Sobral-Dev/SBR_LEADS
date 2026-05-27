from datetime import timedelta, timezone

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BRT = timezone(timedelta(hours=-3))


class Settings(BaseSettings):
    database_url: str
    app_env: str = "development"
    secret_key: str = "dev-insecure-change-me-in-production"

    pedido_mobile_base_url: str = "https://pedidomobile.com/webservice/v3"
    pedido_mobile_user: str | None = None
    pedido_mobile_password: str | None = None

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @model_validator(mode="after")
    def _validar_seguranca_producao(self) -> "Settings":
        if (
            self.app_env == "production"
            and self.secret_key == "dev-insecure-change-me-in-production"
        ):
            raise ValueError(
                "SECRET_KEY precisa ser definida com um valor seguro em produção. "
                "Defina SECRET_KEY no arquivo .env."
            )
        return self


settings = Settings()
