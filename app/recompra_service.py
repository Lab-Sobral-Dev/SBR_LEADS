"""Serviço do dashboard de Recompra.

A matemática (datas de compra + hoje -> ritmo e faixa) é função pura, testável
sem banco — no espírito de analise_service. Os helpers de banco ficam abaixo.

Cada cliente é julgado pela régua DELE mesmo: a mediana dos intervalos entre as
compras define o ritmo; o percentil 90 dos intervalos define até onde um atraso
ainda é "normal" para ele.
"""
from datetime import date

from sqlalchemy import text  # usado por montar_recompra (query de agregação)
from sqlalchemy.orm import Session

from database import valores_distintos

FAIXA_EM_DIA = "em_dia"
FAIXA_ATRASANDO = "atrasando"
FAIXA_ATRASADO = "atrasado"
FAIXA_SEM_PADRAO = "sem_padrao"
MIN_COMPRAS = 3

# Fonte única de verdade da apresentação de cada faixa (emoji, rótulo, cor do
# texto e fundo/borda do card de KPI). Os templates (select, cards e tabela)
# consomem daqui — adicionar/renomear faixa é uma mudança em um lugar só.
FAIXAS = {
    FAIXA_EM_DIA:     {"emoji": "🟢", "label": "Em dia",     "cor": "text-green-400",  "card": "bg-[#16241a] border border-[#2a4a2a]"},
    FAIXA_ATRASANDO:  {"emoji": "🟡", "label": "Atrasando",  "cor": "text-yellow-400", "card": "bg-[#241f10] border border-[#4a4424]"},
    FAIXA_ATRASADO:   {"emoji": "🔴", "label": "Atrasado",   "cor": "text-red-400",    "card": "bg-[#241010] border border-[#4a2424]"},
    FAIXA_SEM_PADRAO: {"emoji": "⚪", "label": "Sem padrão", "cor": "text-[#9ca3af]",  "card": "bg-[#1a1a1a] border border-[#333]"},
}


def _mediana(xs: list[float]) -> float:
    s = sorted(xs)
    n = len(s)
    if n == 0:
        return 0.0
    meio = n // 2
    if n % 2:
        return float(s[meio])
    return (s[meio - 1] + s[meio]) / 2


def _percentil(xs: list[float], p: float) -> float:
    """Percentil por interpolação linear (p em [0,1]); rank = p*(n-1)."""
    s = sorted(xs)
    n = len(s)
    if n == 0:
        return 0.0
    if n == 1:
        return float(s[0])
    rank = p * (n - 1)
    lo = int(rank)
    frac = rank - lo
    if lo + 1 >= n:
        return float(s[-1])
    return s[lo] + frac * (s[lo + 1] - s[lo])


def classificar_recompra(datas: list[date], hoje: date, *, receita_total: float = 0.0) -> dict:
    """Classifica um cliente pelo próprio ritmo de compra.

    Devolve sempre: n_compras, ultima_compra, dias_sem_comprar, ticket_medio, faixa.
    Para >= MIN_COMPRAS adiciona mediana, maior_intervalo_normal e indice.
    Datas repetidas (vários pedidos no mesmo dia) contam como uma única ocasião de compra.
    """
    datas = sorted(set(datas))  # dias distintos: vários pedidos no mesmo dia = uma compra
    n = len(datas)
    ultima = datas[-1] if n else None
    dias_sem_comprar = (hoje - ultima).days if ultima else None
    ticket_medio = (receita_total / n) if n else 0.0

    resultado = {
        "n_compras": n,
        "ultima_compra": ultima,
        "dias_sem_comprar": dias_sem_comprar,
        "ticket_medio": round(ticket_medio, 2),
        "mediana": None,
        "maior_intervalo_normal": None,
        "indice": None,
        "faixa": FAIXA_SEM_PADRAO,
    }
    if n < MIN_COMPRAS:
        return resultado

    # Como datas são distintas (sorted(set(...))), todo intervalo é >= 1 dia,
    # logo mediana >= 1 e a divisão do índice nunca é por zero.
    intervalos = [(datas[i] - datas[i - 1]).days for i in range(1, n)]
    mediana = _mediana(intervalos)
    p90 = _percentil(intervalos, 0.9)
    indice = dias_sem_comprar / mediana

    if dias_sem_comprar <= mediana:
        faixa = FAIXA_EM_DIA
    elif dias_sem_comprar <= p90:
        faixa = FAIXA_ATRASANDO
    else:
        faixa = FAIXA_ATRASADO

    resultado.update({
        "mediana": round(mediana, 1),
        "maior_intervalo_normal": round(p90, 1),
        "indice": round(indice, 2),
        "faixa": faixa,
    })
    return resultado


# ----------------------------------------------------------------- helpers de DB

# "Compra efetiva" = mesma régua do resto do cockpit (dashboard_service._NAO_CANCELADO):
# situação comparada sem sensibilidade a caixa/espaços, senão um 'CANCELADO' cru da
# origem entraria como compra aqui e ficaria de fora nos outros dashboards.
# Recompra ainda exige emissao NOT NULL — a matemática do ritmo depende da data.
_FILTRO_COMPRA = (
    "ped.orcamento = FALSE "
    "AND UPPER(TRIM(COALESCE(ped.situacao, ''))) <> 'CANCELADO' "
    "AND ped.emissao IS NOT NULL"
)

# Cliente elegível ao dashboard: não inativo. Universo dos resultados = clientes
# ativos COM ao menos uma compra efetiva (o JOIN + _FILTRO_COMPRA cuidam do resto).
_CLIENTE_ATIVO = "(pm.inativo = FALSE OR pm.inativo IS NULL)"


def montar_recompra(db: Session, *, vendedor: str | None, cidade: str | None,
                    uf: str | None, hoje: date) -> dict:
    """Agrega compras efetivas por cliente, classifica pelo ritmo individual e
    devolve {clientes: [...ordenados...], kpis: {...}}.

    O KPI `receita_atrasados` soma o **ticket médio** (receita média por compra) dos clientes 🔴 — uma estimativa do faturamento por ciclo que está parado, não a receita histórica total."""
    # Compara com TRIM nos dois lados: as opções dos selects vêm TRIM-adas, então
    # um valor gravado com espaço à toa ('SP ') ainda casa com a opção ('SP').
    cond = [_CLIENTE_ATIVO]
    params: dict = {}
    if vendedor:
        cond.append("TRIM(pm.vendedor) = :vendedor")
        params["vendedor"] = vendedor
    if cidade:
        cond.append("TRIM(pm.municipio) = :cidade")
        params["cidade"] = cidade
    if uf:
        cond.append("TRIM(pm.uf) = :uf")
        params["uf"] = uf
    where = " AND ".join(cond)

    # Clientes sem nenhum pedido efetivo são naturalmente excluídos pelo JOIN.
    rows = db.execute(text(f"""
        SELECT
            pm.documento,
            COALESCE(NULLIF(TRIM(pm.nome_fantasia), ''), pm.razao_social, pm.documento) AS nome,
            pm.vendedor, pm.municipio, pm.uf,
            array_agg(ped.emissao ORDER BY ped.emissao)  AS datas,
            COALESCE(SUM(ped.total_liquido), 0)          AS receita_total
        FROM cliente_pedido_mobile pm
        JOIN pedido_mobile_pedido ped ON ped.cliente_documento = pm.documento
        WHERE {where} AND {_FILTRO_COMPRA}
        GROUP BY pm.documento,
                 COALESCE(NULLIF(TRIM(pm.nome_fantasia), ''), pm.razao_social, pm.documento),
                 pm.vendedor, pm.municipio, pm.uf
    """), params).fetchall()

    clientes = []
    for r in rows:
        info = classificar_recompra(list(r.datas), hoje, receita_total=float(r.receita_total or 0))
        info.update({
            "documento": r.documento,
            "nome": r.nome,
            "vendedor": r.vendedor,
            "municipio": r.municipio,
            "uf": r.uf,
        })
        clientes.append(info)

    # Ordena por índice desc; "sem padrão" (índice None) sempre no fim.
    clientes.sort(key=lambda c: (c["indice"] is not None, c["indice"] if c["indice"] is not None else 0.0), reverse=True)

    return {"clientes": clientes, "kpis": calcular_kpis(clientes)}


def calcular_kpis(clientes: list[dict]) -> dict:
    """Contagem por faixa + receita dos atrasados sobre a lista dada.

    Recebe a lista já no recorte desejado — quando a tela filtra por faixa, os
    KPIs devem refletir o mesmo conjunto exibido na tabela (não o total geral).
    """
    return {
        "em_dia":    sum(1 for c in clientes if c["faixa"] == FAIXA_EM_DIA),
        "atrasando": sum(1 for c in clientes if c["faixa"] == FAIXA_ATRASANDO),
        "atrasado":  sum(1 for c in clientes if c["faixa"] == FAIXA_ATRASADO),
        "sem_padrao": sum(1 for c in clientes if c["faixa"] == FAIXA_SEM_PADRAO),
        "receita_atrasados": round(
            sum(c["ticket_medio"] for c in clientes if c["faixa"] == FAIXA_ATRASADO), 2
        ),
    }


def opcoes_recompra(db: Session) -> dict:
    """Listas para os selects de filtro (vendedor, UF, cidade).

    Escopadas ao MESMO universo dos resultados — clientes ativos com ao menos
    uma compra efetiva — para que nenhuma opção do dropdown leve a um recorte
    vazio. Valores são TRIM-ados (casam com a comparação TRIM de montar_recompra).
    """
    origem = "cliente_pedido_mobile pm JOIN pedido_mobile_pedido ped ON ped.cliente_documento = pm.documento"
    filtro = f"{_CLIENTE_ATIVO} AND {_FILTRO_COMPRA}"
    return {
        "vendedores": list(valores_distintos(db, "pm.vendedor", origem=origem, filtro=filtro)),
        "ufs": list(valores_distintos(db, "pm.uf", origem=origem, filtro=filtro)),
        "cidades": list(valores_distintos(db, "pm.municipio", origem=origem, filtro=filtro)),
    }
