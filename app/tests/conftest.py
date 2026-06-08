import re

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from config import settings


def _trocar_db(url: str, novo_nome: str) -> str:
    """Troca o nome do banco no final da URL de conexão."""
    return re.sub(r"/([^/?]+)(\?|$)", f"/{novo_nome}" + r"\2", url, count=1)


NOME_TESTE = "prospec_test"
TEST_URL = _trocar_db(settings.database_url, NOME_TESTE)

DDL = """
CREATE TABLE IF NOT EXISTS cliente_pedido_mobile (
    documento      VARCHAR(14) PRIMARY KEY,
    tipo_documento VARCHAR(4),
    razao_social   VARCHAR(200),
    nome_fantasia  VARCHAR(200),
    vendedor       VARCHAR(100),
    inativo        BOOLEAN DEFAULT FALSE,
    municipio      VARCHAR(100),
    uf             VARCHAR(2),
    ultima_compra_em DATE,
    atualizado_em  TIMESTAMP DEFAULT NOW()
);
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
    orcamento         BOOLEAN DEFAULT FALSE,
    total_bruto       DECIMAL(12,2),
    total_liquido     DECIMAL(12,2),
    atualizado_em     TIMESTAMP DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS pedido_mobile_item (
    id                SERIAL PRIMARY KEY,
    pedido_numero     INTEGER NOT NULL REFERENCES pedido_mobile_pedido(pedido_numero) ON DELETE CASCADE,
    produto_codigo    VARCHAR(50),
    produto_descricao VARCHAR(300),
    produto_unidade   VARCHAR(10),
    quantidade        DECIMAL(12,4),
    preco_unitario    DECIMAL(12,4),
    desconto          DECIMAL(10,4) DEFAULT 0,
    total_liquido     DECIMAL(12,2),
    informacoes_adicionais TEXT
);
"""


def _criar_banco_de_teste():
    """Cria o banco de teste se não existir (conecta no banco de manutenção)."""
    maint = _trocar_db(settings.database_url, "postgres")
    eng = create_engine(maint, isolation_level="AUTOCOMMIT")
    with eng.connect() as c:
        existe = c.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": NOME_TESTE}
        ).scalar()
        if not existe:
            c.execute(text(f'CREATE DATABASE "{NOME_TESTE}"'))
    eng.dispose()


@pytest.fixture(scope="session")
def engine():
    _criar_banco_de_teste()
    eng = create_engine(TEST_URL)
    with eng.begin() as c:
        for stmt in DDL.split(";"):
            if stmt.strip():
                c.execute(text(stmt))
    yield eng
    eng.dispose()


@pytest.fixture
def db(engine):
    """Sessão isolada: tudo é revertido ao fim de cada teste."""
    conn = engine.connect()
    trans = conn.begin()
    sess = sessionmaker(bind=conn)()
    try:
        yield sess
    finally:
        sess.close()
        trans.rollback()
        conn.close()
