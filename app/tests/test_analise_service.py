import analise_service as svc


# ---- parsing de cortes ----

def test_cortes_canonico_valido():
    assert svc.cortes_canonico("70-20-10") == "70-20-10"


def test_cortes_canonico_invalido_volta_ao_padrao():
    assert svc.cortes_canonico("abc") == "50-30-20"
    assert svc.cortes_canonico(None) == "50-30-20"
    assert svc.cortes_canonico("") == "50-30-20"


def test_parse_cortes_retorna_tupla_a_b():
    assert svc.parse_cortes("50-30-20") == (50, 30)
    assert svc.parse_cortes("70-20-10") == (70, 20)
    assert svc.parse_cortes("80-15-5") == (80, 15)


def test_parse_cortes_invalido_usa_padrao():
    assert svc.parse_cortes("xpto") == (50, 30)
    assert svc.parse_cortes(None) == (50, 30)


# ---- parsing de critério ----

def test_parse_criterio_normaliza():
    assert svc.parse_criterio("receita") == "receita"
    assert svc.parse_criterio("QUANTIDADE") == "quantidade"
    assert svc.parse_criterio(" Quantidade ") == "quantidade"


def test_parse_criterio_invalido_usa_receita():
    assert svc.parse_criterio("xpto") == "receita"
    assert svc.parse_criterio(None) == "receita"


# ---- classificação ABC (math pura) ----

def _itens(*pares):
    """Helper: cria itens a partir de (nome, receita, quantidade)."""
    return [{"codigo": n, "nome": n, "receita": float(r), "quantidade": float(q)}
            for n, r, q in pares]


def test_classificar_por_receita_50_30_20():
    # Receitas: 50, 30, 15, 5 (total 100). Corte 50/30/20.
    # Acumulado ANTES de cada item: 0, 50, 80, 95.
    #   item1 (antes 0  < 50) -> A
    #   item2 (antes 50 < 80) -> B
    #   item3 (antes 80 -> não <80) -> C
    #   item4 (antes 95) -> C
    itens = _itens(("P1", 50, 1), ("P2", 30, 1), ("P3", 15, 1), ("P4", 5, 1))
    saida, resumo = svc._classificar(itens, "receita", (50, 30))
    classes = {i["nome"]: i["classe"] for i in saida}
    assert classes == {"P1": "A", "P2": "B", "P3": "C", "P4": "C"}
    assert saida[0]["pct"] == 50.0
    assert saida[0]["pct_acumulado"] == 50.0
    assert saida[1]["pct_acumulado"] == 80.0
    assert resumo["A"]["itens"] == 1
    assert resumo["A"]["receita"] == 50.0
    assert resumo["A"]["pct"] == 50.0
    assert resumo["C"]["itens"] == 2
    assert resumo["total_itens"] == 4
    assert resumo["total_receita"] == 100.0


def test_classificar_ordena_e_muda_com_criterio_quantidade():
    # Por quantidade a ordem muda: P2 (qtd 90) vira o líder.
    itens = _itens(("P1", 90, 10), ("P2", 10, 90))
    saida, _ = svc._classificar(itens, "quantidade", (50, 30))
    assert [i["nome"] for i in saida] == ["P2", "P1"]
    assert saida[0]["classe"] == "A"  # P2: acumulado antes = 0 < 50
    assert saida[1]["classe"] == "C"  # P1: acumulado antes = 90 -> >= 80


def test_classificar_item_unico_eh_A():
    saida, resumo = svc._classificar(_itens(("UNICO", 123, 7)), "receita", (50, 30))
    assert saida[0]["classe"] == "A"
    assert saida[0]["pct_acumulado"] == 100.0
    assert resumo["A"]["itens"] == 1


def test_classificar_vazio_nao_quebra():
    saida, resumo = svc._classificar([], "receita", (50, 30))
    assert saida == []
    assert resumo["total_itens"] == 0
    assert resumo["total_receita"] == 0.0
    assert resumo["A"]["pct"] == 0.0


def test_classificar_total_zero_vira_tudo_C():
    saida, resumo = svc._classificar(_itens(("Z1", 0, 0), ("Z2", 0, 0)), "receita", (50, 30))
    assert all(i["classe"] == "C" for i in saida)
    assert all(i["pct"] == 0.0 for i in saida)
