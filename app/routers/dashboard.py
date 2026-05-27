import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import text
from sqlalchemy.orm import Session

from auth import require_login
from database import get_db

router = APIRouter()
templates = Jinja2Templates(directory="templates")

_F = "ped.orcamento = FALSE AND ped.situacao != 'Cancelado'"


def _get_dados(db: Session) -> dict:
    # KPIs
    k = db.execute(text(f"""
        SELECT
            (SELECT COUNT(*) FROM cliente_pedido_mobile WHERE inativo = FALSE) AS clientes_ativos,
            SUM(ped.total_liquido) AS receita_total,
            SUM(CASE WHEN date_trunc('month', emissao) = date_trunc('month', CURRENT_DATE)
                     THEN ped.total_liquido END) AS receita_mes,
            SUM(CASE WHEN date_trunc('month', emissao) = date_trunc('month', CURRENT_DATE) - INTERVAL '1 month'
                     THEN ped.total_liquido END) AS receita_mes_ant,
            COUNT(CASE WHEN date_trunc('month', emissao) = date_trunc('month', CURRENT_DATE) THEN 1 END) AS pedidos_mes,
            AVG(ped.total_liquido) AS ticket_medio
        FROM pedido_mobile_pedido ped WHERE {_F}
    """)).fetchone()

    r_mes = float(k.receita_mes or 0)
    r_ant = float(k.receita_mes_ant or 0)
    variacao = round((r_mes - r_ant) / r_ant * 100, 1) if r_ant else None

    kpis = {
        "clientes_ativos": int(k.clientes_ativos or 0),
        "receita_total": float(k.receita_total or 0),
        "receita_mes": r_mes,
        "receita_mes_ant": r_ant,
        "variacao_pct": variacao,
        "pedidos_mes": int(k.pedidos_mes or 0),
        "ticket_medio": float(k.ticket_medio or 0),
    }

    # Faturamento mensal — últimos 12 meses
    fat = db.execute(text(f"""
        SELECT
            TO_CHAR(date_trunc('month', emissao), 'MM/YYYY') AS mes,
            date_trunc('month', emissao) AS mes_dt,
            SUM(total_liquido) AS receita,
            COUNT(*) AS pedidos
        FROM pedido_mobile_pedido ped WHERE {_F}
          AND emissao >= date_trunc('month', CURRENT_DATE) - INTERVAL '11 months'
        GROUP BY date_trunc('month', emissao)
        ORDER BY date_trunc('month', emissao)
    """)).fetchall()
    faturamento = [
        {"mes": r.mes, "receita": float(r.receita or 0), "pedidos": int(r.pedidos)}
        for r in fat
    ]

    # Top 10 produtos por receita
    prods = db.execute(text(f"""
        SELECT
            pit.produto_codigo,
            MAX(pit.produto_descricao) AS descricao,
            SUM(pit.total_liquido) AS receita,
            SUM(pit.quantidade) AS qtde,
            COUNT(DISTINCT ped.pedido_numero) AS pedidos,
            COUNT(DISTINCT ped.cliente_documento) AS clientes
        FROM pedido_mobile_item pit
        JOIN pedido_mobile_pedido ped ON ped.pedido_numero = pit.pedido_numero
        WHERE {_F} AND pit.produto_codigo IS NOT NULL
        GROUP BY pit.produto_codigo
        ORDER BY receita DESC LIMIT 10
    """)).fetchall()
    top_produtos = [
        {
            "codigo": r.produto_codigo,
            "descricao": r.descricao or "",
            "receita": float(r.receita or 0),
            "qtde": float(r.qtde or 0),
            "pedidos": int(r.pedidos),
            "clientes": int(r.clientes),
        }
        for r in prods
    ]

    # Vendedores
    vends = db.execute(text(f"""
        SELECT
            COALESCE(NULLIF(TRIM(vendedor), ''), 'Sem vendedor') AS vendedor,
            SUM(total_liquido) AS receita,
            COUNT(*) AS pedidos,
            COUNT(DISTINCT cliente_documento) AS clientes,
            AVG(total_liquido) AS ticket_medio
        FROM pedido_mobile_pedido ped WHERE {_F}
        GROUP BY COALESCE(NULLIF(TRIM(vendedor), ''), 'Sem vendedor')
        ORDER BY receita DESC
    """)).fetchall()
    vendedores = [
        {
            "vendedor": r.vendedor,
            "receita": float(r.receita or 0),
            "pedidos": int(r.pedidos),
            "clientes": int(r.clientes),
            "ticket_medio": float(r.ticket_medio or 0),
        }
        for r in vends
    ]

    # Top 10 clientes por receita
    clis = db.execute(text(f"""
        SELECT
            ped.cliente_documento,
            COALESCE(NULLIF(TRIM(pm.nome_fantasia), ''), pm.razao_social, ped.cliente_documento) AS nome,
            COALESCE(NULLIF(TRIM(pm.vendedor), ''), '—') AS vendedor,
            SUM(ped.total_liquido) AS receita,
            COUNT(DISTINCT ped.pedido_numero) AS pedidos,
            MAX(ped.emissao) AS ultima_compra
        FROM pedido_mobile_pedido ped
        LEFT JOIN cliente_pedido_mobile pm ON pm.documento = ped.cliente_documento
        WHERE {_F}
        GROUP BY ped.cliente_documento, pm.nome_fantasia, pm.razao_social, pm.vendedor
        ORDER BY receita DESC LIMIT 10
    """)).fetchall()
    top_clientes = [
        {
            "nome": r.nome or "",
            "vendedor": r.vendedor,
            "receita": float(r.receita or 0),
            "pedidos": int(r.pedidos),
            "ultima_compra": r.ultima_compra.strftime("%d/%m/%Y") if r.ultima_compra else None,
        }
        for r in clis
    ]

    # Clientes em risco (top 25 por receita histórica)
    risco = db.execute(text(f"""
        SELECT
            COALESCE(NULLIF(TRIM(pm.nome_fantasia), ''), pm.razao_social, ped.cliente_documento) AS nome,
            COALESCE(NULLIF(TRIM(pm.vendedor), ''), '—') AS vendedor,
            MAX(ped.emissao) AS ultima_compra,
            (CURRENT_DATE - MAX(ped.emissao)) AS dias,
            COUNT(DISTINCT ped.pedido_numero) AS pedidos,
            SUM(ped.total_liquido) AS receita
        FROM pedido_mobile_pedido ped
        LEFT JOIN cliente_pedido_mobile pm ON pm.documento = ped.cliente_documento
        WHERE {_F} AND (pm.inativo = FALSE OR pm.inativo IS NULL)
        GROUP BY ped.cliente_documento, pm.nome_fantasia, pm.razao_social, pm.vendedor
        HAVING (CURRENT_DATE - MAX(ped.emissao)) >= 30
        ORDER BY receita DESC LIMIT 25
    """)).fetchall()
    clientes_risco = [
        {
            "nome": r.nome or "",
            "vendedor": r.vendedor,
            "ultima_compra": r.ultima_compra.strftime("%d/%m/%Y") if r.ultima_compra else None,
            "dias": int(r.dias or 0),
            "pedidos": int(r.pedidos),
            "receita": float(r.receita or 0),
        }
        for r in risco
    ]

    # Contagem real de clientes em risco (sem o LIMIT)
    rc = db.execute(text(f"""
        SELECT
            COUNT(*) FILTER (WHERE dias BETWEEN 30 AND 60) AS leve,
            COUNT(*) FILTER (WHERE dias BETWEEN 61 AND 90) AS medio,
            COUNT(*) FILTER (WHERE dias > 90) AS alto
        FROM (
            SELECT (CURRENT_DATE - MAX(ped.emissao)) AS dias
            FROM pedido_mobile_pedido ped
            LEFT JOIN cliente_pedido_mobile pm ON pm.documento = ped.cliente_documento
            WHERE {_F} AND (pm.inativo = FALSE OR pm.inativo IS NULL)
            GROUP BY ped.cliente_documento
            HAVING (CURRENT_DATE - MAX(ped.emissao)) >= 30
        ) sub
    """)).fetchone()
    risco_counts = {
        "leve": int(rc.leve or 0),
        "medio": int(rc.medio or 0),
        "alto": int(rc.alto or 0),
    }

    return {
        "kpis": kpis,
        "faturamento": faturamento,
        "top_produtos": top_produtos,
        "vendedores": vendedores,
        "top_clientes": top_clientes,
        "clientes_risco": clientes_risco,
        "risco_counts": risco_counts,
    }


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(
    request: Request,
    current_user: dict = Depends(require_login),
    db: Session = Depends(get_db),
):
    dados = _get_dados(db)
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "user": current_user,
        "dados": dados,
        "dados_json": json.dumps(dados, ensure_ascii=False, default=str),
    })
