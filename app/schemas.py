from datetime import date

from pydantic import BaseModel


class UF(BaseModel):
    sigla: str
    nome: str


class Municipio(BaseModel):
    codigo: str
    descricao: str


class Cnae(BaseModel):
    codigo: str
    descricao: str


class AtalhosCnae(BaseModel):
    segmento: str
    descricao: str
    cnaes: list[str]


class BuscarRequest(BaseModel):
    uf: str | None = None
    municipio_codigo: str | None = None
    cnaes: list[str] | None = None
    segmento: str | None = None
    apenas_ativas: bool = True
    porte: str | None = None  # 01=MEI, 03=ME, 05=EPP, 99=Demais
    status_cliente: str | None = None  # None=todos, "cliente", "prospect"
    page: int = 1
    page_size: int = 50
    ordenar: str = "razao_social_asc"


class Lead(BaseModel):
    cnpj: str
    razao_social: str | None
    nome_fantasia: str | None
    cnae_principal: str | None
    cnae_descricao: str | None
    tipo_logradouro: str | None
    logradouro: str | None
    numero: str | None
    complemento: str | None
    bairro: str | None
    cep: str | None
    uf: str | None
    municipio: str | None
    ddd_1: str | None
    telefone_1: str | None
    ddd_2: str | None
    telefone_2: str | None
    email: str | None
    situacao: str | None
    porte: str | None
    capital_social: float | None
    eh_cliente: bool = False
    vendedor: str | None = None
    ultima_compra_em: date | None = None
    dias_sem_compra: int | None = None


class BuscarResponse(BaseModel):
    total: int
    page: int
    page_size: int
    pages: int
    items: list[Lead]


class Stats(BaseModel):
    total_estabelecimentos: int
    total_empresas: int
    ultima_importacao: str | None
    distribuicao_uf: list[dict]
