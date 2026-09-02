"""
SBR Leads — API principal
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import text

from auth import NotAdminException, NotAuthenticatedException, TrocarSenhaException, hash_senha
from config import settings
from database import engine
from routers.admin import router as admin_router
from routers.api import router as api_router
from routers.auth_router import router as auth_router
from routers.dashboard import router as dashboard_router
from routers.frontend import router as frontend_router
from routers.navegacao import router as navegacao_router
from routers.rotas import router as rotas_router


def _bootstrap_usuarios():
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS usuario (
                id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
                email        VARCHAR(255) UNIQUE NOT NULL,
                nome         VARCHAR(100) NOT NULL,
                senha_hash   VARCHAR(200) NOT NULL,
                role         VARCHAR(10)  NOT NULL DEFAULT 'user'
                                          CHECK (role IN ('admin', 'user')),
                ativo        BOOLEAN      NOT NULL DEFAULT true,
                trocar_senha BOOLEAN      NOT NULL DEFAULT true,
                criado_em    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
            )
        """))
        # Migração: garante coluna em tabelas criadas antes desta versão
        conn.execute(text("""
            ALTER TABLE usuario
            ADD COLUMN IF NOT EXISTS trocar_senha BOOLEAN NOT NULL DEFAULT true
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS cliente_pedido_mobile (
                documento      VARCHAR(14) PRIMARY KEY,
                tipo_documento VARCHAR(4),
                razao_social   VARCHAR(200),
                nome_fantasia  VARCHAR(200),
                vendedor       VARCHAR(100),
                inativo        BOOLEAN DEFAULT FALSE,
                municipio      VARCHAR(100),
                uf             VARCHAR(2),
                atualizado_em  TIMESTAMP DEFAULT NOW()
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS pedido_mobile_sync (
                id             SERIAL PRIMARY KEY,
                iniciada_em    TIMESTAMP DEFAULT NOW(),
                concluida_em   TIMESTAMP,
                ultima_versao  BIGINT NOT NULL DEFAULT 0,
                total_clientes INTEGER,
                novos          INTEGER,
                atualizados    INTEGER,
                paginas        INTEGER,
                erro           VARCHAR(500)
            )
        """))
        # Migração: coluna de pedidos sincronizados (para bancos criados antes desta versão)
        conn.execute(text("""
            ALTER TABLE pedido_mobile_sync
            ADD COLUMN IF NOT EXISTS pedidos INTEGER
        """))
        conn.execute(text("""
            ALTER TABLE cliente_pedido_mobile
            ADD COLUMN IF NOT EXISTS ultima_compra_em DATE
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS pedido_mobile_config (
                chave VARCHAR(50) PRIMARY KEY,
                valor TEXT NOT NULL
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS pedido_mobile_pedido (
                pedido_numero     INTEGER PRIMARY KEY,
                cliente_documento VARCHAR(20) NOT NULL,
                vendedor          VARCHAR(100),
                representada      VARCHAR(200),
                tabela_preco      VARCHAR(100),
                plano_pagamento   VARCHAR(200),
                desconto1         DECIMAL(10,4) DEFAULT 0,
                desconto2         DECIMAL(10,4) DEFAULT 0,
                desconto3         DECIMAL(10,4) DEFAULT 0,
                emissao           DATE,
                entrega           DATE,
                situacao          VARCHAR(50),
                orcamento         BOOLEAN DEFAULT false,
                total_bruto       DECIMAL(12,2),
                total_liquido     DECIMAL(12,2),
                atualizado_em     TIMESTAMP DEFAULT NOW()
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS pedido_mobile_item (
                id                    SERIAL PRIMARY KEY,
                pedido_numero         INTEGER NOT NULL
                    REFERENCES pedido_mobile_pedido(pedido_numero) ON DELETE CASCADE,
                produto_codigo        VARCHAR(50),
                produto_descricao     VARCHAR(300),
                produto_unidade       VARCHAR(10),
                quantidade            DECIMAL(12,4),
                preco_unitario        DECIMAL(12,4),
                desconto              DECIMAL(10,4) DEFAULT 0,
                total_liquido         DECIMAL(12,2),
                informacoes_adicionais TEXT
            )
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_pm_pedido_cliente
            ON pedido_mobile_pedido(cliente_documento)
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_pm_item_pedido
            ON pedido_mobile_item(pedido_numero)
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS rota (
                id             SERIAL PRIMARY KEY,
                nome           TEXT NOT NULL,
                vendedor       TEXT NOT NULL,
                municipio      TEXT NOT NULL,
                uf             TEXT NOT NULL,
                criado_em      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                atualizado_em  TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS rota_parada (
                id          SERIAL PRIMARY KEY,
                rota_id     INTEGER NOT NULL REFERENCES rota(id) ON DELETE CASCADE,
                ordem       INTEGER NOT NULL,
                documento   TEXT NOT NULL,
                nome_cache  TEXT NOT NULL,
                eh_cliente  BOOLEAN NOT NULL DEFAULT FALSE,
                cep_cache   TEXT,
                lat_cache   DOUBLE PRECISION,
                lng_cache   DOUBLE PRECISION
            )
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_rota_parada_rota ON rota_parada(rota_id)
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_rota_vendedor ON rota(vendedor)
        """))
        conn.commit()

        count = conn.execute(text("SELECT COUNT(*) FROM usuario")).scalar()
        if count == 0:
            conn.execute(
                text("""
                    INSERT INTO usuario (email, nome, senha_hash, role)
                    VALUES ('admin@sbr.local', 'Administrador', :hash, 'admin')
                """),
                {"hash": hash_senha("admin123")},
            )
            conn.commit()
            print("\n" + "=" * 55)
            print("  ADMIN PADRÃO CRIADO")
            print("  E-mail : admin@sbr.local")
            print("  Senha  : admin123")
            print("  Altere a senha em /admin/usuarios após o login!")
            print("=" * 55 + "\n")


@asynccontextmanager
async def lifespan(app: FastAPI):
    _bootstrap_usuarios()
    yield


app = FastAPI(
    title="SBR Leads",
    version="0.3.0",
    description="Ferramenta de prospecção de leads via base pública da Receita Federal",
    lifespan=lifespan,
)


def _pagina_abra_no_gestao(url_gestao: str) -> str:
    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SBR Leads | Acesso</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  html,body{{height:100%}}
  body{{
    font-family:system-ui,-apple-system,'Segoe UI',sans-serif;
    background-color:#0f0f0f;color:#f0f0f0;
    display:flex;align-items:center;justify-content:center;
    text-align:center;padding:0 24px;
  }}
  .card{{max-width:420px}}
  h1{{font-size:28px;font-weight:800;color:#f97316;letter-spacing:0.5px;margin-bottom:12px}}
  p{{color:rgba(255,255,255,0.65);font-size:15px;line-height:1.5;margin-bottom:28px}}
  a.btn{{
    display:inline-block;padding:14px 32px;border-radius:8px;
    background:linear-gradient(135deg,#f97316 0%,#ea580c 100%);
    color:#fff;font-weight:700;text-decoration:none;letter-spacing:0.5px;
  }}
</style></head>
<body>
  <div class="card">
    <h1>Abra direto no Gestão SBR</h1>
    <p>O SBR Leads agora faz parte do Gestão SBR — acesse por lá, sem precisar logar de novo aqui.</p>
    <a class="btn" href="{url_gestao}">Abrir no Gestão SBR</a>
  </div>
</body></html>"""


@app.middleware("http")
async def abra_no_gestao(request: Request, call_next):
    """Regra: produto externo entra por dentro, não por link (PROTOCOLO-DE-
    ACOPLAMENTO.md, sbrgestao). Navegação de topo real de browser (fora do
    iframe do Gestão) mostra um aviso em vez de seguir o fluxo normal de
    login. Dentro do iframe o browser manda `Sec-Fetch-Dest: iframe`, não
    `document` — passa direto, inclusive num F5 dentro do iframe (o header
    reflete o destino da navegação, não como ela foi disparada). Só GET:
    o form de login deste app é um POST nativo (`<form method="post">`,
    também `Sec-Fetch-Dest: document`) e não pode ser bloqueado aqui.
    """
    if request.method == "GET" and request.headers.get("sec-fetch-dest") == "document":
        return HTMLResponse(_pagina_abra_no_gestao(settings.gestao_url_sbr_leads))
    return await call_next(request)


@app.middleware("http")
async def csp_frame_ancestors(request: Request, call_next):
    """CSP frame-ancestors do Protocolo de Acoplamento (gestao-sbr, §3 item 4).

    Aplicado globalmente, não só na rota de SSO: depois do redirect pós-login
    o navegador carrega `/` (ou o dashboard) dentro do mesmo iframe, e é essa
    resposta que precisa do header, não o handshake em si.

    `frame_ancestor` ausente = não seta header nenhum — mesmo comportamento
    honesto do 503 em /api/auth/sso quando falta configuração, em vez de
    bloquear embed nenhum por omissão.
    """
    response = await call_next(request)
    if settings.frame_ancestor:
        response.headers["Content-Security-Policy"] = f"frame-ancestors 'self' {settings.frame_ancestor}"
    return response


@app.exception_handler(NotAuthenticatedException)
async def not_authenticated_handler(request: Request, exc: NotAuthenticatedException):
    return RedirectResponse(url="/login", status_code=302)


@app.exception_handler(NotAdminException)
async def not_admin_handler(request: Request, exc: NotAdminException):
    return RedirectResponse(url="/", status_code=302)


@app.exception_handler(TrocarSenhaException)
async def trocar_senha_handler(request: Request, exc: TrocarSenhaException):
    return RedirectResponse(url="/trocar-senha", status_code=302)


app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(api_router)
app.include_router(dashboard_router)
app.include_router(navegacao_router)
app.include_router(rotas_router)
app.include_router(frontend_router)


@app.get("/health")
def health():
    try:
        with engine.connect() as conn:
            version = conn.execute(text("SELECT version()")).scalar()
        return {"status": "healthy", "database": "connected", "postgres_version": version}
    except Exception as e:
        return {"status": "unhealthy", "database": "disconnected", "error": str(e)}
