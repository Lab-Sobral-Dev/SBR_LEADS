# Etapas do Projeto

> **Status geral (roadmap original):** Etapas 1–5 concluídas ✅ · Etapa 6 (deploy VPS)
> pendente 🔜. Além do roadmap, o projeto evoluiu com autenticação JWT, integração
> Pedido Mobile e os dashboards do Cockpit Comercial e Rotas de Visita — ver
> [`CLAUDE.md`](CLAUDE.md) para o estado vivo.

| Etapa | Status |
|---|---|
| 1 — Setup do ambiente local | ✅ Concluída |
| 2 — Importação da base CNPJ | ✅ Concluída |
| 3 — Backend / API REST | ✅ Concluída |
| 4 — Frontend | ✅ Concluída |
| 5 — Refinamento local | ✅ Concluída |
| 6 — Deploy VPS Hostinger | 🔜 Pendente (próxima) |

## Etapa 1 — Setup do Ambiente Local ✅ Concluída

**Objetivo:** Validar que o ambiente Docker está funcionando com Postgres + FastAPI base.

**Entregas:**
- `docker-compose.yml` com 3 serviços (postgres, app, pgadmin)
- `app/main.py` com endpoints `/`, `/health`, `/docs`
- `.env.example` template
- `.gitignore` configurado
- README com instruções

**Critérios de conclusão:**
- [x] `docker compose up -d --build` funciona sem erro
- [x] http://localhost:8000/health retorna `database: connected`
- [x] pgAdmin conecta ao Postgres pelo host `postgres`

---

## Etapa 2 — Importação da Base da Receita Federal ✅ Concluída

**Objetivo:** Trazer toda a base pública do CNPJ para o Postgres local.

**Pré-requisitos:**
- Etapa 1 concluída
- 80GB livres em disco
- ~6h disponíveis para a importação

**Entregas:**
- `etl/schema.sql` — DDL com todas as tabelas oficiais
- `etl/download.py` — baixa os arquivos mais recentes da Receita
- `etl/importer.py` — importa via COPY com encoding correto
- `etl/update_monthly.py` — atualização incremental
- Índices criados para performance de busca

**Implementação:**

### 2.1 — Download dos arquivos
A Receita disponibiliza em `https://arquivos.receitafederal.gov.br/CNPJ/dados_abertos_cnpj/`. A estrutura é:

```
dados_abertos_cnpj/
├── 2026-04/         # ano-mês mais recente
│   ├── Cnaes.zip
│   ├── Empresas0.zip ... Empresas9.zip
│   ├── Estabelecimentos0.zip ... Estabelecimentos9.zip
│   ├── Motivos.zip
│   ├── Municipios.zip
│   ├── Naturezas.zip
│   ├── Paises.zip
│   ├── Qualificacoes.zip
│   ├── Simples.zip
│   └── Socios0.zip ... Socios9.zip
```

O script identifica a pasta mais recente automaticamente.

### 2.2 — Schema do banco
Layout fiel à documentação oficial da Receita ([metadados.pdf](https://www.gov.br/receitafederal/dados/cnpj-metadados.pdf)):

```sql
CREATE TABLE empresa (
    cnpj_basico CHAR(8) PRIMARY KEY,
    razao_social VARCHAR(200),
    natureza_juridica CHAR(4),
    qualificacao_responsavel CHAR(2),
    capital_social NUMERIC(20,2),
    porte CHAR(2),
    ente_federativo_responsavel VARCHAR(100)
);

CREATE TABLE estabelecimento (
    cnpj_basico CHAR(8),
    cnpj_ordem CHAR(4),
    cnpj_dv CHAR(2),
    identificador_matriz_filial CHAR(1),
    nome_fantasia VARCHAR(200),
    situacao_cadastral CHAR(2),
    data_situacao_cadastral DATE,
    motivo_situacao_cadastral CHAR(2),
    nome_cidade_exterior VARCHAR(200),
    pais CHAR(3),
    data_inicio_atividade DATE,
    cnae_fiscal_principal CHAR(7),
    cnae_fiscal_secundaria TEXT,
    tipo_logradouro VARCHAR(20),
    logradouro VARCHAR(200),
    numero VARCHAR(20),
    complemento VARCHAR(200),
    bairro VARCHAR(200),
    cep CHAR(8),
    uf CHAR(2),
    municipio CHAR(4),
    ddd_1 VARCHAR(4),
    telefone_1 VARCHAR(15),
    ddd_2 VARCHAR(4),
    telefone_2 VARCHAR(15),
    ddd_fax VARCHAR(4),
    fax VARCHAR(15),
    correio_eletronico VARCHAR(200),
    situacao_especial VARCHAR(200),
    data_situacao_especial DATE,
    PRIMARY KEY (cnpj_basico, cnpj_ordem, cnpj_dv)
);

-- ... demais tabelas (socio, simples, cnae, municipio, etc.)
```

### 2.3 — Importação otimizada
Usar `psycopg2.cursor.copy_expert()` para `COPY FROM STDIN`:

```python
with open(arquivo_csv, 'rb') as f:
    cursor.copy_expert(
        sql=f"COPY estabelecimento FROM STDIN WITH (FORMAT csv, DELIMITER ';', HEADER false, ENCODING 'LATIN1', QUOTE '\"')",
        file=f
    )
```

### 2.4 — Índices
Após a carga (criar antes da carga deixa a importação mais lenta):

```sql
CREATE INDEX idx_estab_uf_municipio ON estabelecimento(uf, municipio);
CREATE INDEX idx_estab_cnae_principal ON estabelecimento(cnae_fiscal_principal);
CREATE INDEX idx_estab_situacao ON estabelecimento(situacao_cadastral);
CREATE INDEX idx_estab_cnpj_basico ON estabelecimento(cnpj_basico);
CREATE INDEX idx_empresa_cnpj_basico ON empresa(cnpj_basico);

-- GIN para autocomplete de CNAE por descrição
CREATE INDEX idx_cnae_descricao_gin ON cnae USING gin(to_tsvector('portuguese', descricao));
```

### 2.5 — Validação
Queries de teste após a importação:

```sql
-- Quantas empresas ativas no Brasil?
SELECT COUNT(*) FROM estabelecimento WHERE situacao_cadastral = '02';

-- Quantas farmácias em Floriano-PI?
SELECT COUNT(*) FROM estabelecimento e
JOIN municipio m ON e.municipio = m.codigo
WHERE e.uf = 'PI'
  AND m.descricao ILIKE 'FLORIANO'
  AND e.cnae_fiscal_principal IN ('4771701', '4771702', '4771703')
  AND e.situacao_cadastral = '02';
```

**Critério de conclusão:**
- Importação completa sem erros
- Queries de validação retornam números coerentes
- Tempo de busca por cidade+CNAE < 1s

---

## Etapa 3 — Backend Completo ✅ Concluída

**Objetivo:** Expor a busca via API REST.

**Endpoints:**

| Método | Rota | Descrição |
|--------|------|-----------|
| GET | `/api/ufs` | Lista todas as UFs |
| GET | `/api/municipios?uf=PI&q=flor` | Autocomplete de municípios |
| GET | `/api/cnaes?q=farmacia` | Autocomplete de CNAEs |
| GET | `/api/cnaes/atalhos` | Lista atalhos pré-definidos |
| POST | `/api/buscar` | Busca leads com filtros |
| GET | `/api/exportar.csv` | Exporta busca em CSV |
| GET | `/api/exportar.xlsx` | Exporta busca em Excel |
| GET | `/api/stats` | Estatísticas da base |

**Critério de conclusão:**
- Todos os endpoints respondem corretamente no Swagger UI
- Busca paginada funciona (page, page_size)
- Exportação CSV/XLSX baixa arquivo correto

---

## Etapa 4 — Frontend ✅ Concluída

**Objetivo:** Interface web amigável.

**Tela principal (`/`):**
- Cabeçalho com nome do app
- Card de filtros: UF (select), Município (autocomplete), CNAE (atalhos visuais + autocomplete), Situação (default: ativa), Porte (opcional)
- Botão "Buscar"
- Resultados em duas abas: 📋 Tabela | 🗺️ Mapa
- Paginação na tabela
- Botão "Exportar CSV" / "Exportar Excel"
- Contador "X resultados encontrados"

**Tecnologia:**
- Templates Jinja2 servidos pelo FastAPI
- HTMX para atualizações parciais (busca sem reload)
- TailwindCSS via CDN (sem build step)
- Leaflet via CDN para mapa

**Critério de conclusão:**
- Fluxo completo (selecionar filtros → ver resultados → exportar) funciona sem F5
- Mapa renderiza com pins clicáveis
- Responsivo (desktop + tablet)

---

## Etapa 5 — Refinamento Local ✅ Concluída

- Tratamento de erros e edge cases
- Mensagens claras quando busca não retorna resultados
- Performance tuning de queries lentas (EXPLAIN ANALYZE)
- Polimento de UX
- Testes manuais com várias cidades e segmentos
- Adicionar logs estruturados

---

## Etapa 6 — Deploy VPS Hostinger 🔜 Pendente (próxima)

**Pré-requisitos:**
- Etapas 1-5 concluídas ✅
- VPS Hostinger contratada (KVM 2 ou superior)
- Domínio próprio (opcional, mas recomendado)

**Passos:**

- [x] Criar `docker-compose.prod.yml` que adiciona o Caddy e remove a exposição do Postgres
- [x] Criar `Caddyfile` com configuração de HTTPS automático
- [x] Autenticação — já implementada (JWT via cookie HTTPOnly, papéis admin/usuário), superando a ideia original de HTTP Basic
- [ ] Provisionar a VPS Hostinger e fazer o primeiro deploy
- [ ] Documentar o processo de deploy em `docs/DEPLOY.md`
- [ ] Configurar cron na VPS para `etl/update_monthly.py`
- [ ] Configurar backup automático do Postgres

**Critério de conclusão:**
- [ ] Sistema acessível via `https://seu-dominio.com`
- [ ] HTTPS funcionando
- [ ] Atualização mensal automatizada
- [ ] Backup configurado
