# Design — Cockpit do Gestor Comercial (Fase 1)

> Data: 2026-06-08
> Status: aprovado para implementação (pendente revisão final do usuário)
> Escopo: **somente a Fase 1**. As fases 2–4 estão resumidas no fim como roadmap, não como escopo deste documento.

## Objetivo

Transformar o dashboard atual — hoje uma visão **global e estática** — num **cockpit de gestão comercial fatiável**: o gestor escolhe um recorte (período, vendedor, representada, situação) e **todos os painéis reagem**, com indicadores comparados contra um período de referência à escolha. O foco é acompanhar o time, identificar quedas e clientes em risco, e direcionar ação.

Usuário primário: o gestor (perfil admin). Visão individual por vendedor fica para a Fase 4.

## Decisões de produto (validadas no brainstorming)

1. **Objetivo primário:** cockpit do gestor (comparar vendedores, ver quedas, clientes em risco). As demais visões viram fases seguintes.
2. **Período:** controle único colapsado ("Junho/2026 ▾") que abre atalhos (Hoje, 7d, Mês, Trimestre, Ano, YTD) **e** intervalo personalizado. Padrão ao abrir: **mês corrente**.
3. **Comparação:** controle dedicado, **temporal e livre**. Opções: mês anterior (padrão), mesmo mês do ano passado, trimestre anterior, período personalizado, ou sem comparação. Não há comparação "entre entidades" (A vs B) — a comparação entre vendedores é resolvida pelo **ranking**.
4. **Densidade:** layout enxuto — barra de filtros em uma linha, período e comparação colapsados. Sem régua de botões sempre visível.
5. **Faseamento:** uma fase por vez. Fase 1 entra em produção antes de iniciar a Fase 2.

## Arquitetura

Mantém o stack atual (FastAPI + HTMX + Jinja2 + SQL agregado em PostgreSQL). Sem JS pesado; comparação calculada no SQL.

- **Estado dos filtros na URL** (querystring). Ex.: `/dashboard?inicio=2026-06-01&fim=2026-06-30&cmp=mes_anterior&vendedor=Joao&representada=&situacao=confirmados`. Isso torna qualquer recorte compartilhável e recarregável.
- **HTMX re-renderiza** o miolo do dashboard ao mudar um filtro (swap parcial do container de painéis), com `hx-get` apontando para `/dashboard` e `hx-include` na barra de filtros. O `hx-push-url` mantém a URL sincronizada.
- **Cache por recorte:** o cache atual (TTL 180s) passa a ser indexado por uma **chave derivada da combinação de filtros + comparação**, em vez de um único slot global. Recortes diferentes têm caches independentes.

### Camadas / responsabilidades

- `app/routers/dashboard.py` — rota, parsing/validação dos filtros, orquestração e cache por chave.
- **Novo** `app/dashboard_service.py` — monta o `WHERE` dinâmico e executa as queries agregadas (KPIs, série temporal, ranking, risco, top representadas/produtos). Recebe um objeto de filtros e retorna dados puros (dicts). Isola SQL da rota e fica testável isoladamente.
- `app/templates/dashboard.html` — layout e barra de filtros.
- **Novos parciais** em `app/templates/partials/` — barra de filtros e o container de painéis (para o swap HTMX).

## Modelo de filtros

Objeto `FiltrosDashboard` (Pydantic), derivado da querystring:

- `inicio: date`, `fim: date` — intervalo do período (padrão: 1º dia do mês corrente → hoje).
- `comparacao: str` — `mes_anterior` (padrão) | `ano_anterior` | `trimestre_anterior` | `personalizado` | `nenhuma`.
- `cmp_inicio: date | None`, `cmp_fim: date | None` — usados só quando `comparacao = personalizado`. Para os demais modos, o intervalo de comparação é **derivado** do período atual.
- `vendedor: str | None` — valor exato de `pedido_mobile_pedido.vendedor` (lista vinda dos distintos).
- `representada: str | None` — idem para `representada`.
- `situacao: str` — `confirmados` (padrão: exclui cancelados e orçamentos) | `todos` | um status específico presente nos dados. Orçamentos entram só quando explicitamente escolhido.

As opções de `vendedor`, `representada` e `situacao` são populadas a partir dos valores distintos existentes na base (com `TRIM`/normalização), servidas pela própria rota.

## Painéis (container que reage aos filtros)

1. **KPIs (5)** com variação vs. período de comparação:
   - Faturamento (Δ%), Pedidos (Δ%), Ticket médio (Δ%), Clientes que compraram no período (Δ absoluto), **Clientes em risco** (contagem).
2. **Faturamento no período** — série temporal (barra) com a série do período comparado sobreposta (linha pontilhada). Granularidade automática conforme o tamanho do intervalo (dia/semana/mês).
3. **🏆 Ranking de vendedores** — tabela ordenável: vendedor, receita, Δ% vs. comparação, nº de pedidos, ticket médio, nº de clientes, % do total. É o instrumento de comparação entre pessoas. Respeita os demais filtros (ex.: filtrando por representada, o ranking mostra quem mais vende aquela marca).
4. **⚠️ Clientes em risco** — lista de ação: cliente, vendedor, dias sem comprar (faixas 30–60 / 61–90 / +90), receita histórica. Ordenada por receita. Respeita os filtros.
5. **Top representadas / produtos** — tabela com receita e % do total (concentração da carteira), alternável entre representadas e produtos.

> **Semântica temporal do "Clientes em risco":** "dias sem comprar" é sempre medido em relação a **hoje** (não ao fim do período filtrado) — risco é um estado atual. O período selecionado **não** recorta esse painel no tempo; mas os filtros de **vendedor** e **representada** continuam valendo (ex.: "clientes em risco da carteira do João"). Os KPIs e os demais painéis (1–4 de faturamento) são recortados pelo período normalmente.

## Fluxo de dados

1. Requisição chega em `/dashboard` com (ou sem) querystring de filtros.
2. A rota constrói `FiltrosDashboard` (aplica padrões quando ausente).
3. Calcula a chave de cache; se houver entrada válida (<180s), retorna.
4. Caso contrário, `dashboard_service` deriva o intervalo de comparação, monta o `WHERE` (sempre via parâmetros bindados — nunca interpolando valor de filtro na string SQL) e executa as queries.
5. Renderiza: requisição normal → página completa; requisição HTMX → apenas o parcial do container de painéis.

## Tratamento de erros e bordas

- **Sem dados no recorte:** painéis mostram estado vazio ("Nenhum pedido neste recorte"), KPIs zerados, sem quebrar.
- **Comparação sem base** (ex.: período comparado anterior ao início dos dados): variação exibida como "—" em vez de % enganoso ou divisão por zero.
- **Intervalo inválido** (`fim < inicio`): a rota normaliza/inverte ou cai no padrão do mês corrente, sem 500.
- **Valores de filtro inexistentes** (vendedor/representada que não existe mais): tratados como "sem resultados", não como erro.

## Melhorias pontuais no código existente (no escopo, pois mexemos nessas queries)

- **Corrigir duplicação por vendedor:** as queries atuais de top clientes / clientes em risco fazem `GROUP BY ... pm.vendedor`, o que duplica um cliente quando o vendedor da ficha difere do vendedor do pedido. Ao reescrever as queries com filtros, agrupar por `cliente_documento` e resolver nome/vendedor com agregação determinística (ex.: `MAX`), eliminando a duplicação.
- O filtro robusto de cancelados (`UPPER(TRIM(COALESCE(situacao,'')))`) já implementado é reaproveitado no novo `WHERE`.

## Testes

- **`dashboard_service` isolado:** dado um conjunto de filtros, valida o `WHERE` gerado e os números agregados contra dados de fixture conhecidos (período, comparação, vendedor, representada, situação).
- **Derivação de comparação:** mês/trimestre/ano anterior e personalizado retornam os intervalos corretos; `nenhuma` não calcula baseline.
- **Rota `/dashboard`:** requisição normal retorna 200 com a página; requisição HTMX retorna só o parcial; recorte vazio não quebra.
- **Cache:** recortes diferentes não colidem; o mesmo recorte reusa o cache.
- **Smoke autenticado** (como já fizemos): login → `/dashboard` com filtros na URL → 200 e marcadores dos painéis presentes.

## Fora de escopo nesta fase (roadmap)

- **Fase 2 — Visão analítica:** aprofundar produtos/representadas, mix, sazonalidade (reusa os filtros).
- **Fase 3 — Realizado vs. meta:** exige cadastro de metas (dado e telas novos).
- **Fase 4 — Painel do vendedor:** escopo individual por login de vendedor.
- Extras adiados do cockpit: clientes novos vs. recorrentes, mix de pagamento/desconto.
