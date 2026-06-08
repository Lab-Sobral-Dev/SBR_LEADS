# Design — Separar Busca e Mapa (Sub-projeto A2)

> Data: 2026-06-08
> Status: aprovado para implementação (pendente revisão final do usuário)
> Pré-requisito: A1 (casca de navegação) concluído. Escopo: **somente A2**. O dashboard de Análise (B) segue no roadmap.

## Objetivo

Separar a tela combinada de hoje (busca + mapa em abas) em **duas páginas** que **compartilham os filtros pela URL**: `/` (Busca, tabela) e `/mapa` (Mapa). As duas têm a **mesma barra de filtros** e os **mesmos cards de resumo**; muda só o conteúdo principal (tabela ↔ mapa). Botões cruzados ("Ver no mapa" / "Ver lista") levam os filtros atuais, sem refiltrar. O item **Mapa** entra no menu lateral.

## Decisões validadas (brainstorming)

1. **Filtros na URL (querystring, GET)** — abordagem (A). `/` e `/mapa` leem os mesmos parâmetros; recarregável e compartilhável por link.
2. **Botão "Buscar" manual** nas duas telas (não auto-filtra a cada mudança — a query roda sobre ~22M de registros).
3. **Cards de resumo** (estabelecimentos/empresas/clientes/prospectos) aparecem nas duas telas, calculados para o recorte atual.
4. **Controles do mapa** (satélite, expandir) vivem na página `/mapa`. Acaba o conceito de "abas".
5. **Item Mapa** entra no menu lateral (no A1 ele foi deixado de fora justamente até esta página existir).

## Arquitetura

Mantém o stack (FastAPI + Jinja2 + HTMX + Leaflet). A mudança é: **filtros como estado de URL** e **divisão da tela em duas rotas** que reaproveitam parciais.

- **Filtros → querystring.** O formulário passa de `hx-post="/buscar"` para `hx-get` apontando para a própria página (`/` ou `/mapa`), com `hx-push-url="true"` e `hx-target` no container de conteúdo. Submeter atualiza a URL e troca o conteúdo via HTMX. Em carga de página completa (link/refresh) com querystring, a rota renderiza já com os resultados.
- **`BuscarRequest` a partir da query.** Reaproveita o `_form_to_req` existente passando `request.query_params` (tem a mesma interface `.get` do form). Sem duplicar parsing.
- **Links cruzados no servidor.** "Ver no mapa" = `/mapa?{{ request.url.query }}`; "Ver lista" = `/?{{ request.url.query }}`. Como as duas rotas leem os mesmos parâmetros, basta repassar a querystring atual.
- **Parciais compartilhados.** A barra de filtros e os cards de resumo viram parciais incluídos pelas duas páginas, evitando divergência.

### Rotas

- **`GET /` (Busca):** lê filtros da query. Sem filtros → estado inicial (sem resultados). Com filtros → roda `buscar()` + `buscar_stats()` e renderiza tabela + cards. Requisição HTMX retorna só o parcial de resultados; requisição normal retorna a página inteira. (Substitui o atual `POST /buscar`.)
- **`GET /mapa` (Mapa):** lê os mesmos filtros, roda `buscar_para_mapa()` (até 5000) + `buscar_stats()` e renderiza o mapa + cards. Mesma lógica HTMX (parcial vs. página).

## Componentes

| Arquivo | Ação | Responsabilidade |
|---|---|---|
| `app/templates/partials/busca_filtros.html` | criar | Barra de filtros (extraída do `index.html`), com `hx-get` para a página alvo. |
| `app/templates/partials/busca_cards.html` | criar | Cards de resumo do recorte (extraídos do `resultados.html`). |
| `app/templates/partials/busca_resultados.html` | criar/renomear | Cabeçalho (contagem, ordenação, export) + tabela + botão "Ver no mapa". (Parte de tabela do atual `resultados.html`.) |
| `app/templates/partials/mapa_painel.html` | criar | Mapa Leaflet + controles (satélite/expandir) + botão "Ver lista". (Parte de mapa do atual `resultados.html`.) |
| `app/templates/partials/cliente_modal.html` | criar | Modal de detalhes do cliente + pedidos (JS compartilhado entre Busca e Mapa). |
| `app/templates/index.html` | modificar | Vira a página de Busca enxuta: filtros + cards + resultados (tabela). Form com `hx-get="/"`. |
| `app/templates/mapa.html` | criar | Página de Mapa: filtros + cards + mapa. Form com `hx-get="/mapa"`. |
| `app/routers/frontend.py` | modificar | `GET /` passa a aceitar filtros e renderizar resultados (substitui `POST /buscar`); adicionar `GET /mapa`. Reusa `_form_to_req`, `buscar`, `buscar_stats`, `buscar_para_mapa`. |
| `app/templates/partials/sidebar.html` | modificar | Adicionar o item **Mapa** (`/mapa`), ativo quando `path == '/mapa'`. |

## Fluxo de dados

1. Usuário ajusta filtros e clica **Buscar** → `hx-get` para a rota atual com `hx-push-url` → a rota lê `request.query_params`, monta `BuscarRequest`, executa a consulta e devolve o **parcial de conteúdo** (tabela ou mapa) + cards; a URL passa a refletir os filtros.
2. Usuário clica **"Ver no mapa"** → navega para `/mapa?<querystring atual>` → a página de mapa carrega já filtrada (mesmos cards).
3. **"Ver lista"** faz o caminho inverso para `/`.
4. Refresh ou link compartilhado com querystring → a página renderiza completa, já com resultados/mapa.

## Tratamento de erros e bordas

- **Sem filtros / sem resultados:** Busca mostra o estado inicial ("ajuste os filtros") e o Mapa mostra um mapa vazio com aviso; cards zerados; sem quebrar.
- **Paginação:** continua só na Busca (tabela). O Mapa não pagina — carrega marcadores até o limite (5000) e, se exceder, sinaliza que nem todos cabem (mensagem honesta, sem truncar silenciosamente).
- **Compatibilidade de filtros:** os dois usam exatamente o mesmo `BuscarRequest`/`build_where`, garantindo cards idênticos para o mesmo recorte.
- **JS compartilhado:** o modal de cliente/pedidos é incluído nas duas páginas (parcial único), evitando divergência; o JS específico de mapa só carrega em `/mapa`.

## Testes

- **`_form_to_req` com querystring (pytest):** dada uma `QueryParams` equivalente, produz o mesmo `BuscarRequest` que o form. (Cobre a conversão para estado de URL.)
- **Rota `/` (smoke autenticado):** sem querystring → 200 estado inicial; com querystring (ex.: `?uf=PI&segmento=farmacia`) → 200 com a tabela e os cards; requisição HTMX retorna só o parcial.
- **Rota `/mapa` (smoke autenticado):** com os mesmos filtros → 200 com o mapa e os cards; o botão "Ver lista" aponta para `/` com a mesma querystring.
- **Link cruzado:** a página de Busca contém `href="/mapa?..."` com a querystring atual (e vice-versa).
- **Menu:** o item Mapa aparece no sidebar e fica ativo em `/mapa`.
- **Não regredir:** exportações CSV/XLSX seguem funcionando; a suíte pytest existente (24) permanece verde.

## Fora de escopo (roadmap)

- **B — Dashboard de Análise de Vendas:** curva ABC, representadas, mix, sazonalidade (card "Disponível" no hub).
- Auto-filtro (busca a cada mudança) — mantido manual de propósito.
- Sincronização de filtros entre abas/janelas além do que a URL já oferece.
