"""Serviço das Rotas de Visita.

Funções puras (haversine, ordenação por vizinho mais próximo, URLs do Google
Maps) são testáveis sem banco. Os helpers de banco (candidatos, risco, CRUD)
ficam mais abaixo no arquivo.
"""

import math
from urllib.parse import urlencode

from sqlalchemy import text
from sqlalchemy.orm import Session

from dashboard_filters import FiltrosDashboard  # noqa: F401  (usado pelos helpers de DB)
from service import ATALHOS, SEGMENTO_FIXO

# CNAEs do segmento fixo (farmácia) — a base só contém esse segmento.
CNAES_SEGMENTO = next(a["cnaes"] for a in ATALHOS if a["segmento"] == SEGMENTO_FIXO)

_MAPS_BASE = "https://www.google.com/maps/dir/"
_MAX_POR_TRECHO_PADRAO = 10


# --------------------------------------------------------------------------- puras

def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distância em km entre dois pontos (linha reta sobre a esfera)."""
    r = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2)
    return 2 * r * math.asin(math.sqrt(a))


def _tem_coords(p: dict) -> bool:
    return p.get("lat") is not None and p.get("lng") is not None


def ordenar_vizinho_mais_proximo(paradas: list[dict], partida_idx: int = 0) -> list[dict]:
    """Reordena as paradas pelo vizinho mais próximo (haversine) a partir de
    `partida_idx`. Paradas sem lat/lng vão para o fim, na ordem original.
    Não muta a entrada."""
    com = [p for p in paradas if _tem_coords(p)]
    sem = [p for p in paradas if not _tem_coords(p)]
    if len(com) <= 1:
        return com + sem

    # Localiza a partida entre as que têm coords; se inválida, usa a primeira.
    partida = paradas[partida_idx] if 0 <= partida_idx < len(paradas) else None
    if partida is None or not _tem_coords(partida):
        atual = com[0]
    else:
        atual = partida

    restantes = [p for p in com if p is not atual]
    ordenado = [atual]
    while restantes:
        prox = min(restantes, key=lambda p: haversine_km(atual["lat"], atual["lng"], p["lat"], p["lng"]))
        ordenado.append(prox)
        restantes.pop(next(j for j, x in enumerate(restantes) if x is prox))
        atual = prox
    return ordenado + sem


def _url_trecho(pontos: list[dict]) -> str:
    origem = pontos[0]
    destino = pontos[-1]
    meio = pontos[1:-1]
    params = {
        "api": "1",
        "origin": f'{origem["lat"]},{origem["lng"]}',
        "destination": f'{destino["lat"]},{destino["lng"]}',
        "travelmode": "driving",
    }
    if meio:
        params["waypoints"] = "|".join(f'{p["lat"]},{p["lng"]}' for p in meio)
    return _MAPS_BASE + "?" + urlencode(params)


def montar_urls_google_maps(paradas: list[dict],
                            max_por_trecho: int = _MAX_POR_TRECHO_PADRAO) -> list[str]:
    """URLs de direções do Google Maps na ordem das paradas. Quebra em trechos
    de até `max_por_trecho` pontos; cada trecho começa na última parada do
    anterior (continuidade). Ignora paradas sem coords. Vazio se < 2 pontos."""
    com = [p for p in paradas if _tem_coords(p)]
    if len(com) < 2:
        return []
    urls = []
    passo = max(1, max_por_trecho - 1)  # sobreposição de 1 ponto entre trechos
    i = 0
    while i < len(com) - 1:
        trecho = com[i:i + max_por_trecho]
        urls.append(_url_trecho(trecho))
        i += passo
    return urls
