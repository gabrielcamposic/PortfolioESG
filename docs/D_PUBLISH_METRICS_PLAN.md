# D_Publish Metrics Alignment — Implementation Plan

**Criado:** 2026-03-14  
**Status:** Aprovado para implementação  
**Referência:** docs/METRICS_REFERENCE.md (diagnóstico das inconsistências)

---

## Objetivo

Tornar todas as métricas do frontend consistentes: mesma fonte, mesmo universo de ativos, mesma metodologia, mesmo período. D_Publish.py é o consolidador único de dados para o frontend.

---

## Diagnóstico resumido

`_build_real_section()` em D_Publish.py popula `dashboard_latest.json → real.*` lendo `portfolio_diagnostics_history.csv`. Esse CSV é gerado por **A4_Analysis.py** usando retornos diários do portfólio **modelo** (pesos do GA aplicados a preços históricos), não do portfólio real. A seção inteira `real.portfolio` no dashboard é do modelo, exceto o `twr_total_return` que é um híbrido (valores modelo + cash flows reais do ledger).

Adicionalmente, `portfolio_history.csv` (gerado por B4) não rastreia todos os ativos do ledger (~81% de cobertura) devido a falhas de normalização de tickers.

Detalhes completos em `docs/METRICS_REFERENCE.md`.

---

## Pré-requisitos: Fix Ticker Normalization

### T1 — Fix B4_Portfolio_History.py

**Problema:** `normalize_symbol()` não reconhece variantes de ticker do broker:
- `"AXIA ENERGIAPNB N1"` (sem "EX") → não normaliza → venda de AXIA6 não registrada
- `"VULCABRAS ON EDS NM"` e `"VULCABRAS ON ED NM"` → podem não agrupar com `"VULCABRAS ON NM"`

**Fix:** Melhorar `normalize_symbol()` em B4 para lidar com variantes. Adicionar entradas no `tickers.txt → BrokerName` ou fazer matching mais robusto. Coverage sobe de ~81% → ~100%.

**Evidência:** Em `data/ledger.csv`:
- Linha 24: `AXIA ENERGIAPNB EX N1` (BUY) → normaliza OK via tickers.txt
- Linha 43: `AXIA ENERGIAPNB N1` (SELL) → **não normaliza** (falta "EX")
- Linhas 17-19: `VULCABRAS ON EDS NM` (SELL) → variante "EDS" pode não mapear
- Linha 28: `VULCABRAS ON ED NM` (BUY) → variante "ED" pode não mapear

### T2 — Fix B2_Consolidate_Ledger.py

**Problema:** Mesma falha de normalização → `ledger_positions.json` mostra AXIA6 com qty=5 (deveria ser 0 após venda) e VULC3 em 2 entries separadas (23 + 3 qty).

**Fix:** Compartilhar a mesma lógica de normalização corrigida entre B2 e B4. Idealmente extrair para `shared_tools/` como função reutilizável.

### T3 — Fix B4: Excluir weekends

**Problema:** `portfolio_history.csv` inclui sábados e domingos (preços repetidos de sexta). Isso cria dias com return=0 que diluem métricas anualizadas e desalinham com o benchmark (que só tem business days no `portfolio_timeseries.csv`).

**Fix:** No loop de `build_portfolio_history()`, pular dias que não são business days.

---

## Mudança 1 — Novo Step em D_Publish: Série diária real

### Output

**Arquivo:** `data/results/portfolio_real_daily.csv`  
**Symlink:** `html/data/portfolio_real_daily.csv`

### Colunas

| Coluna | Tipo | Descrição |
|---|---|---|
| `date` | str | Data (YYYY-MM-DD), apenas business days |
| `portfolio_value` | float | Valor de mercado do portfólio real nesse dia |
| `cost_basis` | float | Custo total investido acumulado nesse dia |
| `cash_flow` | float | Fluxo de caixa líquido nesse dia (+ = aporte, − = resgate). 0 se sem transação |
| `portfolio_return` | float | Retorno TWR diário: `(V_t − CF_t) / V_{t−1} − 1`. Vazio no primeiro dia |
| `benchmark_return` | float | Retorno diário do ^BVSP. Vazio no primeiro dia |

### O que NÃO incluir

- **Sem índices acumulados (base 100).** O frontend calcula os acumulados dinamicamente em função do período selecionado pelo usuário. Se o usuário quer ver "últimos 3M", o JS filtra as datas e compõe `∏(1 + return)` a partir da data início escolhida. Isso permite rebasar a qualquer sub-período sem mudanças no backend.
- **Sem métricas derivadas.** Apenas retornos diários. Métricas (sharpe, vol, etc.) ficam no `dashboard_latest.json`.

### Algoritmo

```
1. Carregar portfolio_history.csv → agrupar por date → {date: market_value, cost_basis}
2. Carregar ledger.csv → agrupar cash flows por date:
   - BUY: cash_flow = +total_cost
   - SELL: cash_flow = −total_cost
3. Carregar portfolio_timeseries.csv → {date: benchmark1_daily_return}
4. Filtrar: apenas business days (dates que existem no timeseries)
5. Para cada date (ordenado):
   - Se é o primeiro dia: portfolio_return = vazio, benchmark_return = vazio
   - Senão: portfolio_return = (V_t − CF_t) / V_{t−1} − 1
   - benchmark_return = benchmark1_daily_return do timeseries
6. Salvar CSV
7. Symlink para html/data/
```

### Nota sobre cash_flow

Usar os cash flows do `ledger.csv` (transações reais), NÃO a variação de cost_basis. A fórmula TWR é `r = (V_t − CF_t) / V_{t−1} − 1` onde CF_t vem direto do ledger.

Enquanto T1/T2 não estiverem implementados, o cash flow do ledger pode incluir transações de ativos não rastreados no portfolio_history (ex: AXIA6). Nesses casos, usar a variação de cost_basis como fallback para CF_t (ou seja: se a data tem cash_flow no ledger mas NÃO tem variação de cost_basis correspondente no portfolio_history, ignorar o cash_flow do ledger para essa data).

### Fontes de dados

```
portfolio_history.csv ──→ portfolio_value, cost_basis (por dia)
ledger.csv ─────────────→ cash_flow (por dia)
portfolio_timeseries.csv → benchmark_return (por dia)
```

---

## Mudança 2 — Computar métricas reais da série TWR

### Onde

Dentro de D_Publish.py, novo helper `_compute_real_metrics(daily_df)`.

### Métricas a computar

| Métrica | Fórmula |
|---|---|
| `total_return_twr` | `∏(1 + r_t) − 1` |
| `annual_return` | `(1 + total_return)^(252 / n_trading_days) − 1` |
| `volatility` | `std(r_t, ddof=1) × √252` |
| `sharpe` | `(annual_return − 0.1175) / volatility` |
| `sortino` | `(annual_return − 0.1175) / downside_dev` onde `downside_dev = std(min(r_t, 0)) × √252` |
| `max_drawdown` | max peak-to-trough do índice TWR (computar índice internamente: `idx_t = idx_{t-1} × (1+r_t)`) |
| `calmar` | `annual_return / max_drawdown` |
| `benchmark_total_return` | `∏(1 + bench_r_t) − 1` (mesmas datas) |
| `benchmark_annual_return` | `(1 + bench_total)^(252 / n) − 1` |
| `alpha_total` | `total_return_twr − benchmark_total_return` |
| `alpha_annual` | `annual_return − benchmark_annual_return` |
| `beta` | `cov(r_port, r_bench) / var(r_bench)` |
| `tracking_error` | `std(r_port − r_bench, ddof=1) × √252` |
| `information_ratio` | `alpha_annual / tracking_error` |
| `correlation` | `corr(r_port, r_bench)` |

### Input

A série `portfolio_real_daily.csv` gerada na Mudança 1 (colunas `portfolio_return` e `benchmark_return`).

---

## Mudança 3 — Reestruturar `dashboard_latest.json → real`

### Nova estrutura

```json
{
  "generated_at": "...",
  "model": { "..." },
  "real": {
    "meta": {
      "history_start": "2025-10-17",
      "history_end": "2026-03-12",
      "trading_days": 95,
      "coverage_pct": 81.0,
      "source": "portfolio_history.csv + ledger.csv"
    },
    "snapshot": {
      "total_market": 3748.92,
      "total_invested": 3427.61,
      "unrealized_pnl": 321.31,
      "simple_roi_pct": 9.37,
      "n_positions": 10
    },
    "twr": {
      "total_return": 0.2681,
      "annual_return": 0.2033,
      "volatility": 0.2152,
      "sharpe": 0.40,
      "sortino": 0.48,
      "max_drawdown": 0.49,
      "calmar": 0.41
    },
    "benchmark": {
      "ticker": "^BVSP",
      "total_return": 0.2362,
      "annual_return": 0.1520
    },
    "alpha": {
      "total": 0.0319,
      "annual": 0.0513
    },
    "relative": {
      "beta": 0.24,
      "tracking_error": 0.27,
      "information_ratio": 0.21,
      "correlation": 0.26
    },
    "structure": {
      "hhi": 0.4812,
      "top3": 0.9122,
      "top5": 1.0,
      "n_assets": 5
    },
    "performance": {
      "YTD":  { "portfolio": 0.35, "benchmark": 0.14 },
      "3M":   { "portfolio": 0.43, "benchmark": 0.16 },
      "6M":   { "portfolio": 0.73, "benchmark": 0.29 },
      "12M":  { "portfolio": 2.25, "benchmark": 0.48 },
      "24M":  { "portfolio": 4.69, "benchmark": 0.45 }
    }
  }
}
```

### Diferenças vs estrutura atual

| Campo | Antes | Depois |
|---|---|---|
| `real.portfolio.*` | Métricas do portfólio **modelo** | **Removido** |
| `real.snapshot` | Não existia | **Novo**: dados de `ledger_positions.json` |
| `real.twr` | Não existia | **Novo**: métricas TWR do portfólio **real** |
| `real.benchmark` | Não existia | **Novo**: benchmark mesmo período/método |
| `real.alpha` | Não existia | **Novo**: diferença TWR − benchmark |
| `real.relative` | Vinha de A4 (modelo) | **Recalculado** da série TWR real |
| `real.meta.coverage_pct` | Não existia | **Novo**: % do portfólio coberto pelo tracking |
| `real.performance` | Vinha de A4 (modelo) | **Recalculado** da série TWR real |

### Impacto nos consumidores atuais

As seções `html/sections/01_header.html` até `08_history.html` (construídas anteriormente) leem campos como `real.portfolio.sharpe`, `real.relative.beta`, etc. Esses caminhos mudam. Porém essas seções serão substituídas pelo novo frontend (`1_portfolio.html` e futuros), portanto a quebra é intencional.

---

## Mudança 4 — Frontend consome dados consistentes

### Cards (1_portfolio.html)

| Card | Campo JSON | Metodologia |
|---|---|---|
| Patrimônio | `real.snapshot.total_market` | Snapshot direto |
| Retorno (R$) | `real.snapshot.unrealized_pnl` | Snapshot direto |
| Retorno (%) | `real.snapshot.simple_roi_pct` | MWR (pnl / invested, intuitivo) |
| Retorno Anualizado | `real.twr.annual_return` | TWR real |
| Volatilidade | `real.twr.volatility` | TWR real |
| Sharpe | `real.twr.sharpe` | TWR real |
| Ibovespa | `real.benchmark.total_return` | Mesmo período/método que TWR |
| Alpha vs Ibovespa | `real.alpha.total` | TWR − benchmark |

### Gráfico (1_portfolio.html)

**Fonte:** `portfolio_real_daily.csv`

**Lógica no frontend (JS):**
1. Fetch `portfolio_real_daily.csv` via PapaParse
2. Determinar data início e data fim (do `real.meta` ou filtro do usuário)
3. Filtrar rows pelo período desejado
4. Computar índice base 100 no JS a partir da data início:
   ```js
   portfolio_index[0] = 100
   for (i = 1..N):
     portfolio_index[i] = portfolio_index[i-1] * (1 + portfolio_return[i])

   benchmark_index[0] = 100
   for (i = 1..N):
     benchmark_index[i] = benchmark_index[i-1] * (1 + benchmark_return[i])
   ```
5. Plotar ambas as linhas no Chart.js

**Vantagem:** O frontend pode recalcular a base 100 para qualquer sub-período sem depender do backend. Se amanhã quisermos um seletor "3M / 6M / 12M / All", basta filtrar as datas e recompor a partir da nova data início.

---

## Ordem de implementação

| Step | Tarefa | Tipo | Depende de |
|---|---|---|---|
| 1 | T1 + T2: Fix ticker normalization (B4 + B2) | Backend fix | — |
| 2 | T3: Excluir weekends de portfolio_history.csv | Backend fix | — |
| 3 | Rodar `run_all.sh` para gerar dados corrigidos | Validação | 1, 2 |
| 4 | Mudança 1: Novo step em D_Publish — série diária real | Backend | 3 |
| 5 | Mudança 2: Computar métricas reais | Backend | 4 |
| 6 | Mudança 3: Reestruturar dashboard_latest.json | Backend | 5 |
| 7 | Rodar `run_all.sh` para gerar novo dashboard | Validação | 6 |
| 8 | Mudança 4: Frontend consome nova estrutura | Frontend | 7 |
| 9 | Validação visual end-to-end | Validação | 8 |

---

## Critério de sucesso

Após implementação completa:

1. **Todos os cards TWR** (Anualizado, Vol, Sharpe, Ibovespa, Alpha) derivam da mesma série diária, mesmas datas, mesma fórmula
2. **O gráfico** usa a mesma série diária (`portfolio_real_daily.csv`) que originou as métricas dos cards
3. **O card "Retorno (%)"** é claramente MWR (snapshot), diferente mas complementar ao TWR
4. **Ibovespa card = gráfico Ibovespa** quando o período é o mesmo (mesmos dados, mesma metodologia)
5. **`coverage_pct`** documenta transparentemente a cobertura de ativos
6. **O frontend pode rebasar a qualquer sub-período** sem mudanças no backend

