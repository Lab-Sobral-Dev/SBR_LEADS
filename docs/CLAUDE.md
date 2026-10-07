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
- **Escolhida:** Base pública de CNPJ da Receita Federal (download mensal em [arquivos.receitafederal.gov.br](https://arquivos.receitafederal.gov.br/index.php/s/YggdBLfdninEJX9))
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

**Etapa em andamento:** Etapas 1–5 concluídas; em evolução contínua (dashboards do Cockpit Comercial e Rotas). Roadmap histórico em [`ETAPAS.md`](ETAPAS.md).

**O que já está pronto:**

- **Etapa 1 (setup Docker)** — `docker-compose.yml`, FastAPI base, pgAdmin, `.env.example`
- **Etapa 2 (importação CNPJ)** — base da Receita Federal importada (segmento `farmacia` ativo: 120k estabelecimentos + 90k empresas, mês de referência 2026-09)
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

- **Dashboard de Recompra** (`GET /dashboard/recompra`, card no hub) — classifica cada cliente pelo PRÓPRIO ritmo de compra (mediana dos intervalos entre dias distintos de compra): 🟢 em dia (≤ mediana) · 🟡 atrasando (≤ p90) · 🔴 atrasado (> p90) · ⚪ sem padrão (<3 compras). KPIs por faixa + receita dos atrasados (soma do ticket médio dos 🔴) + tabela ordenada pelo índice (dias÷mediana). Filtros vendedor/UF/cidade/faixa, medição até hoje, cache por recorte. Compra efetiva = não-orçamento e situação≠Cancelado; pedidos no mesmo dia = uma compra. Novo `app/recompra_service.py` (`classificar_recompra` pura + `montar_recompra`/`opcoes_recompra`). Spec/plano em `docs/superpowers/{specs,plans}/2026-06-11-recompra*`

- **Fix do botão de sincronizar (Pedido Mobile)** — `frontend.py` chamava `_info_pedido_mobile` inexistente (movida no refactor de navegação 08/06) → 500 no `POST /sync-clientes`, sync parado desde 27/05. `info_pedido_mobile` centralizada em `pedido_mobile.py`; card passou a exibir total de pedidos + pedidos sincronizados na última sync.

**Próximas frentes:**
- **Recompra → Cross-sell (2ª etapa)** — produtos a oferecer por cliente (o que clientes parecidos compram e ele não; cesta/produtos comprados juntos). Spec própria, a desenhar.
- **Cockpit Comercial Fase 3** — Realizado vs. meta (exige cadastro de metas; dado/telas novos)
- **Etapa 6 (infra)** — Deploy VPS Hostinger (Caddy + cron mensal + backup)
- **Rotas de Visita — evoluções futuras** — login próprio de vendedor, histórico de visitas, autocomplete de município (hoje usa código IBGE)

## Roadmap

As Etapas 1–5 (setup, importação CNPJ, API REST, frontend, refinamento) estão **concluídas**
— o detalhamento histórico de cada uma está em [`ETAPAS.md`](ETAPAS.md) e o desenho técnico
em [`ARCHITECTURE.md`](ARCHITECTURE.md). As frentes ativas estão em **"Próximas frentes"**
acima (Cross-sell, Cockpit Fase 3). A única etapa de roadmap ainda pendente:

### Etapa 6 — Deploy VPS Hostinger
- `docker-compose.prod.yml` + `Caddyfile` já existem (HTTPS automático via Let's Encrypt).
- Falta: provisionar a VPS Hostinger, documentar o processo de deploy, configurar o cron
  mensal (`etl/update_monthly.py`) e o backup automático do Postgres.

## Convenções do Projeto

### Git
- Branch principal: `main` — commits vão direto na `main` (sem branches intermediárias)
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
