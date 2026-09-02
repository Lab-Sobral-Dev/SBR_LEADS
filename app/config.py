from datetime import timedelta, timezone

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BRT = timezone(timedelta(hours=-3))


class Settings(BaseSettings):
    database_url: str
    app_env: str = "development"
    secret_key: str = "dev-insecure-change-me-in-production"

    # Protocolo de Acoplamento com o gestao-sbr ("LABSRV-COLOSSUS"). Segredo
    # compartilhado, recebido fora do repositório. Ausente = /api/auth/sso
    # responde 503 honesto e o resto do app segue normal.
    docking_secret: str | None = None

    # Flag `Secure` do cookie de sessão — opt-in por variável própria, NÃO
    # derivada de `app_env`. Sobre HTTP interno o Secure faz o navegador
    # descartar o cookie e a pessoa entra em loop de login. Ligar só quando
    # servir atrás de TLS. Mesma lição paga no SBR-KPIs.
    session_cookie_secure: bool = False

    # Origem autorizada a embutir este app em iframe (CSP frame-ancestors).
    # Vazio = não permite embed de lugar nenhum.
    frame_ancestor: str | None = None

    # Pra onde redirecionar quem acessar este sistema direto (fora do iframe
    # do Gestão) — mostrado como aviso "Abra direto no Gestão SBR".
    gestao_url_sbr_leads: str = "https://gestao.laboratoriosobral.com.br/comercial/demandas/leads"

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
