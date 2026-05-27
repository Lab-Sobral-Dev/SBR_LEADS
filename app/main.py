"""
SBR Leads — API principal
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import text

from auth import NotAdminException, NotAuthenticatedException, TrocarSenhaException, hash_senha
from database import engine
from routers.admin import router as admin_router
from routers.api import router as api_router
from routers.auth_router import router as auth_router
from routers.dashboard import router as dashboard_router
from routers.frontend import router as frontend_router


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
app.include_router(frontend_router)


@app.get("/health")
def health():
    try:
        with engine.connect() as conn:
            version = conn.execute(text("SELECT version()")).scalar()
        return {"status": "healthy", "database": "connected", "postgres_version": version}
    except Exception as e:
        return {"status": "unhealthy", "database": "disconnected", "error": str(e)}
