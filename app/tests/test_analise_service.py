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
