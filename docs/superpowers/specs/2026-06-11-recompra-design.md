# Dashboard de Recompra — Design

> Spec de design do dashboard "Recompra" do SBR Leads.
> Brainstorm em 2026-06-11. Parte da evolução do Cockpit Comercial.
> O **Cross-sell** é uma segunda etapa, com spec própria (fora deste documento).

## Objetivo

Mostrar, para cada cliente, se ele está **dentro ou fora do próprio ritmo de compra**, para o vendedor/gestor agir antes de perder a venda recorrente. Diferente do painel "clientes em risco" do cockpit (que usa um corte fixo de 30/60/90 dias), aqui cada cliente é julgado pela **régua dele mesmo** (o intervalo típico das compras dele).

## Decisões do brainstorm

1. **Unidade do ritmo:** **geral por cliente** (não por representada) — um ritmo único por cliente, somando todas as compras.
2. **Resumo do ritmo:** **mediana** dos intervalos entre compras (robusta a uma demora atípica).
3. **Três faixas**, pelo índice de atraso `= dias_sem_comprar ÷ mediana`, com fronteiras baseadas no comportamento do próprio cliente:
   - 🟢 **Em dia:** `dias_sem_comprar ≤ mediana`
   - 🟡 **Atrasando:** `mediana < dias_sem_comprar ≤ maior_intervalo_normal`
   - 🔴 **Atrasado:** `dias_sem_comprar > maior_intervalo_normal`
   - O **"maior intervalo normal"** = percentil ~90 dos intervalos do cliente (descarta uma demora excepcional isolada).
4. **Mínimo de histórico:** cliente precisa de **≥ 3 compras** (≥ 2 intervalos) para entrar nas faixas. Com **1 ou 2 compras** vai para a faixa ⚪ **"sem padrão"** (sem índice).
5. **O que conta como compra (compra efetiva):** `orçamento = não` **e** `situação ≠ Cancelado`. As situações válidas hoje são Enviado, Em processamento, Em carteira, Faturado (Cancelado é a única excluída; orçamentos são poucos).
6. **Filtros:** Vendedor, Cidade/UF e Faixa. **Medição sempre "até hoje"** (ignora período — atraso é sempre relativo a hoje).
7. **Layout:** KPIs por faixa no topo + tabela ordenada pelo índice (mais fora do próprio ritmo primeiro). Os "sem padrão" entram **na mesma tabela, no fim da listagem**.
8. **"Receita dos atrasados" (KPI):** soma do **ticket médio** (receita média por compra) dos clientes 🔴 — "quanto de faturamento por ciclo está parado".
9. **De quem é o cliente (filtro Vendedor):** o vendedor **atribuído ao cliente** no Pedido Mobile (`cliente_pedido_mobile.vendedor`) — "a carteira do vendedor".
10. **Atalho para Rotas** ("ver no mapa / adicionar à rota"): **fora deste primeiro corte** (evolução futura).

## Navegação e tela

- Novo card no hub **Dashboards** apontando para `/dashboard/recompra`.
- Rota **`GET /dashboard/recompra`** (irmã de `/dashboard/analise`), atrás de `require_login`. Resposta HTML completa ou parcial (HTMX), seguindo o padrão de `routers/dashboard.py`.
- **Tela única:**
  - **Linha de KPIs (5):** 🟢 Em dia, 🟡 Atrasando, 🔴 Atrasado, ⚪ Sem padrão (contagens), e **Receita dos atrasados** (R$).
  - **Tabela** de clientes, colunas: **Cliente · Vendedor · Última compra · Ritmo (mediana) · Dias sem comprar · Índice · Receita/compra · Faixa (selo)**.
  - Ordenação: por **índice decrescente** (atrasados no topo); clientes "sem padrão" (sem índice) sempre no **fim**.
  - Os KPIs sempre refletem **todas** as faixas; o filtro **Faixa** estreita apenas a tabela.

## Cálculo do ritmo — `app/recompra_service.py`

A matemática é uma **função pura testável** (sem banco), no espírito de `analise_service._classificar`.

```
classificar_recompra(datas_compra: list[date], hoje: date, *, receita_total: float) -> dict
```
Dado a lista ordenada de datas de compra efetiva de um cliente:
- `n_compras = len(datas)`. Se `n_compras < 3` → `faixa = "sem_padrao"`, sem `indice`/`mediana` (mas ainda devolve `ultima_compra`, `dias_sem_comprar`, `n_compras`, `ticket_medio`).
- `intervalos` = diferenças (em dias) entre compras consecutivas.
- `mediana` = mediana dos intervalos.
- `maior_intervalo_normal` = **percentil 90** dos intervalos, por interpolação linear sobre a lista ordenada (`rank = 0,9·(n−1)`, interpola entre os vizinhos). Determinístico, para testar com precisão.
- `dias_sem_comprar = (hoje − última compra).days`.
- `indice = dias_sem_comprar / mediana` (mediana ≥ 1; se mediana = 0 por compras no mesmo dia, tratar como 1 para evitar divisão por zero).
- **Faixa:** 🟢 `dias ≤ mediana` · 🟡 `mediana < dias ≤ p90` · 🔴 `dias > p90`. (p90 ≥ mediana sempre, então as faixas nunca se invertem.)
- `ticket_medio = receita_total / n_compras`.

Um agregador `montar_recompra(db, *, vendedor, cidade, uf, hoje)` busca os dados, roda a função pura por cliente, monta a lista ordenada e os KPIs (contagens por faixa + soma do ticket médio dos 🔴).

## Dados / query

Uma query agrega por cliente, sobre **compras efetivas**, com os filtros de vendedor/cidade/UF aplicados via `cliente_pedido_mobile`:

```sql
SELECT
    pm.documento,
    COALESCE(NULLIF(TRIM(pm.nome_fantasia), ''), pm.razao_social, pm.documento) AS nome,
    pm.vendedor, pm.municipio, pm.uf,
    array_agg(ped.emissao ORDER BY ped.emissao)              AS datas,
    COALESCE(SUM(ped.total_liquido), 0)                      AS receita_total
FROM cliente_pedido_mobile pm
JOIN pedido_mobile_pedido ped ON ped.cliente_documento = pm.documento
WHERE ped.orcamento = FALSE
  AND ped.situacao IS DISTINCT FROM 'Cancelado'
  AND ped.emissao IS NOT NULL
  AND (pm.inativo = FALSE OR pm.inativo IS NULL)
  -- + filtros opcionais: pm.vendedor = :vendedor, pm.uf = :uf, pm.municipio = :cidade
GROUP BY pm.documento, nome, pm.vendedor, pm.municipio, pm.uf
```

O Python roda `classificar_recompra` por linha. ~2,4k clientes / ~8k pedidos — volume tranquilo.

## Filtros e cache

- **Vendedor** (dropdown via `dashboard_service.opcoes_filtro`), **Cidade** e **UF** (texto/select de `cliente_pedido_mobile`), **Faixa** (todas / em dia / atrasando / atrasado / sem padrão) — todos na querystring (GET + HTMX), seguindo o padrão dos outros dashboards.
- **Medição até hoje:** `hoje = datetime.now(BRT).date()`; não há filtro de período.
- **Cache por recorte** com TTL (igual ao `_dados_cacheados` do dashboard): chave = `vendedor | cidade | uf | hoje`. O filtro **Faixa** é aplicado sobre o resultado já calculado/cacheado (os KPIs mostram a contagem total).

## Testes (pytest)

Função pura `classificar_recompra` (sem banco):
- mediana e p90 corretos para uma lista de intervalos conhecida;
- as 3 faixas exatamente nos limites: `dias = mediana` (🟢), `dias = p90` (🟡), `dias = p90 + 1` (🔴);
- `< 3 compras` → "sem padrão" (1 e 2 compras), sem índice;
- p90 robusto a outlier (uma demora excepcional não infla a faixa 🟡 indevidamente);
- `ticket_medio` correto; mediana 0 (compras no mesmo dia) não quebra.

Agregador `montar_recompra` (com fixture `db`):
- exclui orçamentos e cancelados da contagem;
- agrega datas por cliente e classifica;
- KPIs: contagens por faixa e soma do ticket médio dos 🔴;
- filtros de vendedor/cidade/UF aplicados.

## Fora de escopo (etapas futuras)

- **Cross-sell** (produtos a oferecer, cesta de compra) — segunda etapa, spec própria.
- **Atalho para Rotas** (ver no mapa / adicionar à rota a partir de um cliente atrasado).
- **Ritmo por representada** (hoje é geral por cliente).
- Configurar os cortes/percentil pela UI (ficam fixos nesta versão).
