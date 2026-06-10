# Contexto do Projeto — Prospec Leads

> Este arquivo é lido automaticamente pelo **Claude Code** ao abrir o projeto.
> Ele contém o histórico de decisões, o estado atual e as próximas etapas.
> **Sempre consulte este arquivo antes de propor mudanças estruturais.**

## Resumo Executivo

**Objetivo:** Ferramenta web pessoal para listar leads (empresas) por cidade e segmento de atividade (CNAE), usando a base pública de CNPJs da Receita Federal — sem custos de API, hospedagem futura em VPS Hostinger.

**Usuário:** Uso pessoal, prospecção B2B em cidades brasileiras (foco inicial em Floriano-PI e região).

**Princípio guia:** Custo zero de API. Dados oficiais e gratuitos. Cache permanente local.

## Decisões Já Tomadas (Não Reabrir Sem Discussão)

### Fonte de Dados
- **Escolhida:** Base pública de CNPJ da Receita Federal (download mensal de [dados.gov.br](https://dados.gov.br/dados/conjuntos-dados/cadastro-nacional-da-pessoa-juridica---cnpj))
- **Descartadas:** Google Places API (custo por chamada), web scraping (frágil e ilegal), APIs CNPJ comerciais (planos gratuitos não permitem listar por cidade+CNAE)
- **Motivo:** Cobertura muito superior (todas as empresas formais, não só as cadastradas no Google), CNPJ disponível para cruzamento com base de clientes futura, zero custo, dados oficiais

### Stack Técnica
- **Backend:** Python 3.11 + FastAPI
- **Banco:** PostgreSQL 16 (SQLite foi descartado — não aguenta o volume de ~22M de estabelecimentos ativos)
- **Frontend:** HTMX + Jinja2 + TailwindCSS (monolito, servido pelo próprio FastAPI)
- **Mapa:** Leaflet com tiles OpenStreetMap (gratuito, sem API key)
- **Container:** Docker + Docker Compose
- **Proxy (produção):** Caddy (HTTPS automático via Let's Encrypt)

### Infraestrutura
- **Fase 1 (atual):** Desenvolvimento local em Windows + Docker Desktop + WSL2
- **Fase 2 (futura):** VPS Hostinger KVM 2 (8GB RAM, 100GB SSD) com mesmo stack
- **Princípio:** O `docker-compose.yml` da fase 1 é praticamente idêntico ao da fase 2; muda apenas o arquivo `.env` e adiciona-se o serviço Caddy em produção

### Abrangência da Base
- **Decisão do usuário:** Importar Brasil inteiro desde o início
- **Implicação:** ~5GB compactados, ~25GB descompactados, ~50-70GB no PostgreSQL após índices, 3-8h de importação
- **Filtro padrão recomendado:** Apenas estabelecimentos com situação cadastral "ATIVA" (reduz volume em ~50%)

### Integração Pedido Mobile
- **Escolhida:** Sync periódico (botão manual no UI) da base de clientes via `GET /clienteintegracao/versao` da API do Pedido Mobile
- **Motivo:** Permite cruzar leads da Receita com a base de clientes ativos dos vendedores e exibir badge "Cliente • <vendedor>" na listagem
- **Apenas leitura:** `app/pedido_mobile.py` jamais chama POST/PUT/DELETE na API
- **Versionamento incremental:** API expõe `ultimaVersao`; sync só baixa deltas
- **Credenciais:** apenas em `.env` (gitignored), nunca commitadas

### Geocodificação no mapa
- **Escolhida:** AwesomeAPI (`cep.awesomeapi.com.br/json/{cep}`) para CEP → lat/lng
- **Descartadas:** Nominatim/OpenStreetMap (CORS bloqueado no browser, rate limit de 1 req/s), BrasilAPI (não retorna coordenadas)
- **Tier gratuito da AwesomeAPI:** 1.000 consultas/dia/IP — suficiente porque o cache em `localStorage` evita refetch dos mesmos CEPs
- **Auto-zoom:** após geocode, `mapa.fitBounds()` enquadra todos os marcadores

### Funcionalidades do MVP
**INCLUI:**
- Filtros: estado, cidade, CNAE (com atalhos pré-definidos + autocomplete por descrição)
- Listagem dos leads com nome, endereço, telefone, e-mail, CNPJ, situação, porte, capital social
- Visualização em tabela e em mapa (Leaflet)
- Exportação CSV/Excel
- Cache permanente: a base local É o cache; consultas são instantâneas
- Atualização mensal automatizada (cron) quando a Receita publica novos dados

**NÃO INCLUI no MVP (deixar para versões futuras):**
- Cadastro de clientes próprios e cruzamento com leads
- Sistema multi-usuário / autenticação
- Enriquecimento de dados via scraping de sites das empresas
- Integração com CRM
- Dashboard de métricas

## Estado Atual do Projeto

**Etapa em andamento:** Etapa 5 — Refinamento (segurança, performance, integrações)

**O que já está pronto:**

- **Etapa 1 (setup Docker)** — `docker-compose.yml`, FastAPI base, pgAdmin, `.env.example`
- **Etapa 2 (importação CNPJ)** — base da Receita Federal importada (segmento `farmacia` ativo: 128k estabelecimentos + 97k empresas)
- **Etapa 3 (API REST)** — endpoints `/api/buscar`, `/api/exportar.csv`, `/api/exportar.xlsx`, `/api/ufs`, `/api/municipios`, `/api/cnaes`, `/api/stats`
- **Etapa 4 (frontend)** — HTMX + Jinja2 + TailwindCSS, mapa Leaflet, autocomplete CNAE, dark theme
- **Integração Pedido Mobile** — sync de clientes via API (`POST /sync-clientes`), badge "Cliente • <vendedor>" na listagem, filtro `status_cliente`, colunas extras nos exports
- **Refinamentos da Etapa 5 já feitos:**
  - Limite de 50k registros na exportação (CSV streaming + XLSX)
  - SRI nos CDNs (HTMX + Leaflet)
  - `app/service.py` consolidando lógica de busca (sem duplicação api.py/frontend.py)
  - Pydantic settings validando `DATABASE_URL` na startup
  - `docker-compose.prod.yml` + `Caddyfile` para deploy VPS
  - Geocode do mapa via AwesomeAPI (paralelo + cache localStorage), `fitBounds` automático
  - Fix do erro 404 do sync incremental do Pedido Mobile (sem clientes alterados)
  - Lock contra syncs simultâneos do Pedido Mobile
  - Escape XSS em popups do Leaflet e no `leads_json`

- **Cockpit Comercial (evolução do `/dashboard`):**
  - Fase 1 — Cockpit do gestor (KPIs comparados, ranking de vendedores, clientes em risco, top representadas) sobre uma fundação de filtros na URL + HTMX + cache por recorte
  - Fase 2 / A1 — Casca de navegação (menu lateral) + hub de Dashboards
  - Fase 2 / A2 — Separação de Busca e Mapa (filtros na querystring)
  - Fase 2 / B — **Dashboard de Análise de Vendas**: curvas ABC (Pareto) de produtos e representadas, critério selecionável receita/quantidade, cortes 50/30/20 · 70/20/10 · 80/15/5, em abas (resumo + Pareto + tabela com filtro por classe). Spec/plano em `docs/superpowers/{specs,plans}/2026-06-09-analise-vendas-abc*`

- **Rotas de Visita** (item "Rotas" no menu) — montagem de rotas de visita por vendedor (visão gestor): tela de 3 colunas (candidatos clientes+prospectos com selo de risco | mapa Leaflet | rota arrastável), ordenação por vizinho mais próximo (função pura no backend), handoff pro Google Maps com quebra em trechos (>10 paradas), rotas salvas/nomeadas (tabelas `rota`/`rota_parada`). Geocode por CEP client-side reusando o cache do Mapa. Novo `app/rotas_service.py` + `app/routers/rotas.py`. 23 testes no service (68 na suíte). Spec/plano em `docs/superpowers/{specs,plans}/2026-06-10-rotas-visita*`

**Próximas frentes:**
- **Cockpit Comercial Fase 3** — Realizado vs. meta (exige cadastro de metas; dado/telas novos)
- **Etapa 6 (infra)** — Deploy VPS Hostinger (Caddy + cron mensal + backup)
- **Rotas de Visita — evoluções futuras** — login próprio de vendedor, histórico de visitas, autocomplete de município (hoje usa código IBGE)

## Próximas Etapas

### Etapa 2 — Importação da Base da Receita Federal

**Objetivo:** Baixar, processar e importar a base completa do CNPJ no PostgreSQL local.

**Passos a implementar:**

1. Criar `etl/download.py` que baixa os arquivos mais recentes de https://arquivos.receitafederal.gov.br/CNPJ/dados_abertos_cnpj/ (são ~37 arquivos zip distribuídos em subpastas mensais)

2. Criar `etl/schema.sql` com o schema oficial das tabelas:
   - `empresa` (CNPJ básico, razão social, natureza jurídica, capital social, porte)
   - `estabelecimento` (CNPJ ordem + DV, matriz/filial, nome fantasia, situação, endereço completo, telefones, e-mail, CNAE principal, CNAEs secundários)
   - `socio` (sócios das empresas)
   - `simples` (opção pelo Simples Nacional e MEI)
   - `cnae` (tabela de referência: código + descrição)
   - `municipio` (tabela IBGE: código + nome + UF)
   - `pais`, `natureza_juridica`, `qualificacao_socio`, `motivo` (tabelas de domínio)

3. Criar `etl/importer.py` que:
   - Descompacta os ZIPs
   - Usa `COPY FROM STDIN` (psycopg2) em vez de INSERT (10-100x mais rápido)
   - Encoding ISO-8859-1 dos arquivos da Receita → converter para UTF-8
   - Separador `;` e quote `"`
   - Filtra apenas estabelecimentos ativos (situacao_cadastral = '02') por padrão (configurável)

4. Criar índices essenciais:
   ```sql
   CREATE INDEX idx_estab_uf_municipio ON estabelecimento(uf, municipio);
   CREATE INDEX idx_estab_cnae_principal ON estabelecimento(cnae_fiscal_principal);
   CREATE INDEX idx_estab_situacao ON estabelecimento(situacao_cadastral);
   CREATE INDEX idx_estab_cnpj_basico ON estabelecimento(cnpj_basico);
   CREATE INDEX idx_empresa_cnpj_basico ON empresa(cnpj_basico);
   ```

5. Criar `etl/update_monthly.py` para atualização incremental (rodar via cron mensalmente)

6. Implementar logs detalhados (qual arquivo está processando, quantos registros já inseriu, ETA)

**Referências de implementação:**
- Repositório de referência: https://github.com/aphonsoar/Receita_Federal_do_Brasil_-_Dados_Publicos_CNPJ
- Layout oficial dos arquivos: https://www.gov.br/receitafederal/dados/cnpj-metadados.pdf

### Etapa 3 — Backend Completo

**Endpoints a criar:**

- `GET /api/ufs` → lista de UFs (estática)
- `GET /api/municipios?uf=PI` → municípios de uma UF
- `GET /api/cnaes?q=farmacia` → autocomplete de CNAEs por descrição
- `GET /api/cnaes/atalhos` → categorias pré-definidas (farmácias, restaurantes, etc.)
- `POST /api/buscar` → recebe filtros (uf, municipio_id, cnae, situacao, porte, etc.) e retorna leads paginados
- `GET /api/exportar?...` → mesma busca em CSV/XLSX

**Dicionário de atalhos de CNAE (sugestão inicial):**
```python
ATALHOS_CNAE = {
    "farmacia": ["4771701", "4771702", "4771703"],
    "restaurante": ["5611201", "5611203", "5611204", "5611205"],
    "oficina_mecanica": ["4520001", "4520002", "4520003", "4520004", "4520005"],
    "supermercado": ["4711301", "4711302"],
    "padaria": ["1091102", "4721102"],
    "salao_beleza": ["9602501", "9602502"],
    "academia": ["9313100"],
    "clinica_medica": ["8630501", "8630502", "8630503"],
    "advocacia": ["6911701"],
    "contabilidade": ["6920601"],
    # ... expandir conforme necessidade
}
```

### Etapa 4 — Frontend

- Página única (`/`) com tela de busca
- Componentes: select UF, autocomplete cidade, atalhos CNAE + autocomplete CNAE
- Resultados em duas abas: Tabela e Mapa
- HTMX para atualização parcial sem reload
- TailwindCSS para estilo
- Leaflet para o mapa
- Botão de exportar CSV/XLSX

### Etapa 5 — Refinamento Local
- Testes com cidades reais
- Performance tuning das queries (EXPLAIN ANALYZE)
- Tratamento de casos extremos (cidades sem resultados, CNAEs raros)
- Melhoria de UX

### Etapa 6 — Deploy VPS Hostinger
- Criar `docker-compose.prod.yml` com Caddy
- Documentar processo de deploy via Git
- Configurar cron para atualização mensal automatizada
- Backup do banco

## Convenções do Projeto

### Git
- Branch principal: `main`
- Branches de feature: `feature/etapa-2-importacao`, `feature/etapa-3-api`, etc.
- Commits em português, formato: `tipo: descrição curta`
  - `feat:` nova funcionalidade
  - `fix:` correção
  - `docs:` documentação
  - `chore:` manutenção
  - `refactor:` refatoração

### Código
- **Python:** seguir PEP 8, type hints sempre que possível, docstrings em funções públicas
- **SQL:** queries em maiúsculas (SELECT, FROM, WHERE), nomes de tabelas/colunas em snake_case
- **Comentários:** em português

### Variáveis de Ambiente
- Todas em `.env` (nunca commitado)
- Template em `.env.example` (commitado, sem valores reais)
- Acesso via `os.getenv()` ou Pydantic Settings

## Restrições Importantes para o Claude Code

1. **Nunca commite o arquivo `.env`** — só o `.env.example` vai pro Git
2. **Nunca apague a pasta `data/`** sem confirmação explícita do usuário (contém o banco)
3. **Antes de mudar a stack** (ex: trocar PostgreSQL por outro banco), consulte com o usuário
4. **Sempre teste localmente** com `docker compose up` antes de propor PR
5. **A importação da base é cara** (3-8h) — não rodar à toa em testes

## Notas Operacionais

- O usuário está em **Windows com Docker Desktop + WSL2**
- O usuário tem **conhecimento básico de Docker**, mas confortável com terminal
- O projeto é hospedado em **GitHub** (público ou privado, decisão do usuário)
- A IDE de trabalho é **VS Code** com extensão Claude Code
- A linguagem da interface e mensagens deve ser **português brasileiro**
