# PortfolioESG — Metrics Reference

**Criado:** 2026-03-13  
**Atualizado:** 2026-03-14 (pós-implementação D_PUBLISH_METRICS_PLAN)  
**Objetivo:** Documentar a fórmula, fonte de dados e janela temporal de cada métrica exibida em `1_portfolio.html`.

---

## Status: ✅ Todas as inconsistências corrigidas

A implementação de `D_PUBLISH_METRICS_PLAN.md` (Steps 1-9) foi concluída em 2026-03-14.
Todas as 6 inconsistências originais (A–F) foram resolvidas. Veja [Inconsistências corrigidas](#inconsistências-corrigidas) para o antes/depois.

---

## Entendendo Simple ROI vs MWR vs TWR

Antes de ler as métricas, é essencial entender as três formas de medir retorno — elas respondem a perguntas diferentes.

### Analogia: a padaria

Imagine que você abre uma padaria:

1. **Mês 1:** Investiu R$ 1.000 → faturou R$ 1.200 (+20%)
2. **Mês 2:** Investiu mais R$ 5.000 (total R$ 6.200) → faturou R$ 6.400 (+3,2% no mês)

Fim: você tem **R$ 6.400**, investiu **R$ 6.000**.

| Método | Pergunta que responde | Resultado | Como calcula |
|---|---|---|---|
| **Simple ROI** | "Quanto ganhei sobre o dinheiro total que coloquei?" | **(6.400 − 6.000) / 6.000 = +6,7%** | Lucro ÷ capital investido. Ignora quando o dinheiro entrou. |
| **MWR** | "Qual foi minha experiência real em R$, considerando quando cada aporte entrou?" | **≈ +5,3%** | TIR (taxa que zera o fluxo de caixa). Penaliza se você aportou muito antes de um mês ruim. |
| **TWR** | "Quão bom é meu gestor/estratégia, independente dos aportes?" | **(1,20 × 1,032) − 1 = +23,8%** | Compõe os retornos de cada período. Remove completamente o efeito dos aportes. |

### Por que os números são tão diferentes?

- **Simple ROI (6,7%)** → você colocou R$ 6.000 e ganhou R$ 400. Simples assim.
- **TWR (23,8%)** → a *estratégia* foi excelente (20% + 3,2%), mas a maior parte do dinheiro só entrou no mês 2, quando o retorno foi menor. O TWR não se importa com isso.
- **MWR (5,3%)** → sua *experiência real* foi mais próxima dos 3,2% do mês 2, porque a maioria do capital viveu nesse período.

### Qual usar quando?

| Situação | Método | Por quê |
|---|---|---|
| "Quanto dinheiro ganhei?" | Simple ROI | Direto, intuitivo |
| "Minha estratégia é melhor que o Ibovespa?" | TWR | Permite comparação justa (mesma metodologia que índices) |
| "Tomei boas decisões de timing?" | MWR vs TWR | Se MWR < TWR, você aportou mais em períodos ruins |

### Neste portfólio

| Método | Valor | Interpretação |
|---|---|---|
| Simple ROI | +11,90% | R$ 322 de lucro sobre R$ 2.708 investidos |
| TWR | +26,37% | A seleção de ativos rendeu 26% — bom vs Ibovespa (+23,62%) |
| TWR > Simple ROI | Gap de ~14 p.p. | O investidor aportou a maior parte do capital mais tarde, quando o portfólio já tinha subido. Os primeiros R$ 988 (out/2025) tiveram retornos altos, mas representavam pouco capital. |

---

## Fluxo de dados (pós-correção)

```
ledger.csv ──→ B2_Consolidate_Ledger.py ──→ ledger_positions.json
                   (shared ticker norm)          ↓ snapshot cards (1,2,3)
                                                 ↓
ledger.csv ──→ B4_Portfolio_History.py  ──→ portfolio_history.csv
                   (shared ticker norm,           ↓
                    weekends excluded)             ↓
                                                  ↓
                   D_Publish.py (Step 4a) ◄───────┘
                       ↓
                   portfolio_real_daily.csv ──→ gráfico (base 100 no JS)
                       ↓
                   D_Publish.py (Step 4b)
                       ↓
                   dashboard_latest.json → real.twr.*     → cards 4,5,6
                                         → real.benchmark → card 7
                                         → real.alpha     → card 8
                                         → real.snapshot  → cards 1,2,3
```

**Princípio:** Cards 4–8 e o gráfico derivam da **mesma série** (`portfolio_real_daily.csv`), mesmas datas, mesma metodologia (TWR). Cards 1–3 são snapshot (Simple ROI), claramente diferenciados.

---

## Cards

### Layout

Two rows of 4 cards each:

**Row 1 — Snapshot do portfólio**
| Card | Fonte JSON | Metodologia |
|---|---|---|
| Patrimônio | `real.snapshot.total_market` | Valor direto |
| Retorno (R$) | `real.snapshot.unrealized_pnl` | Snapshot |
| Retorno (%) | `real.snapshot.simple_roi_pct` | Simple ROI |
| Retorno TWR | `real.twr.total_return` | TWR real |

**Row 2 — Comparação com benchmarks**
| Card | Fonte JSON | Metodologia |
|---|---|---|
| % do CDI | `real.twr.pct_cdi` | TWR / CDI × 100 |
| Volatilidade | `real.twr.volatility` | Desvio-padrão anualizado |
| Ibovespa | `real.benchmark.total_return` | TWR benchmark mesmo período |
| Alpha vs Ibov | `real.alpha.total` | TWR − benchmark |

---

### 1. Patrimônio

| Item | Valor |
|---|---|
| **Fórmula** | Valor direto |
| **Fonte** | `dashboard_latest.json → real.snapshot.total_market` |
| **Origem** | `ledger_positions.json → total_current_market` |
| **Composição** | Σ (qty × current_price) para **todos** os ativos ativos no ledger |
| **Nº de ativos** | 9 posições ativas (VULC3 unificado, AXIA6 vendido = 0 qty) |
| **Valor atual** | R$ 3.030,34 |
| **Sub-texto** | "investido R$ 2.707,97" |

### 2. Retorno (R$)

| Item | Valor |
|---|---|
| **Fórmula** | `total_current_market − total_invested_cash` |
| **Fonte** | `dashboard_latest.json → real.snapshot.unrealized_pnl` |
| **Composição** | **Todos** os ativos ativos no ledger |
| **Valor atual** | +R$ 322,37 |
| **Nota** | `total_invested_cash` inclui taxas e emolumentos das notas de negociação |

### 3. Retorno (%)

| Item | Valor |
|---|---|
| **Fórmula** | `unrealized_pnl / total_invested_cash × 100` |
| **Fonte** | `dashboard_latest.json → real.snapshot.simple_roi_pct` |
| **Metodologia** | **Simple ROI** — lucro bruto ÷ capital investido |
| **Valor atual** | +11,90% |
| **Janela temporal** | Desde a primeira compra até hoje (implícita) |
| **Sub-texto** | "MWR · snapshot" |
| **Nota** | Não ajusta pelo timing dos aportes. Diferente do TWR (card 4) — ver seção [Entendendo Simple ROI vs MWR vs TWR](#entendendo-simple-roi-vs-mwr-vs-twr). |

### 4. Retorno TWR

| Item | Valor |
|---|---|
| **Fórmula** | `∏(1 + r_t) − 1` onde `r_t = (V_t − CF_t) / V_{t−1} − 1` |
| **Fonte** | `dashboard_latest.json → real.twr.total_return` |
| **Origem no backend** | `D_Publish.py → _compute_real_metrics()` a partir de `portfolio_real_daily.csv` |
| **Dados de entrada** | Retornos diários TWR do portfólio **real** (portfolio_history.csv + ledger.csv) |
| **Composição** | Portfólio real — 12 ativos rastreados, 100% de cobertura |
| **Valor atual** | +26,37% |
| **Janela temporal** | 2025-10-17 → 2026-03-13 (68 pregões) |
| **Sub-texto** | Se `annualize_safe=true` (≥252 pregões): "anualiz. +X%". Senão: "desde out/25". |
| **Link com gráfico** | ✅ Corresponde exatamente ao endpoint da linha "Portfólio" (base 100 → 126,37) |
| **Nota** | O retorno anualizado (141%) é matematicamente correto mas enganoso com apenas 68 pregões. Por isso é suprimido do valor principal e só aparece como sub-texto quando a história alcançar 1 ano. |

### 5. % do CDI

| Item | Valor |
|---|---|
| **Fórmula** | `(twr_total_return / cdi_total_return) × 100` |
| **Fonte** | `dashboard_latest.json → real.twr.pct_cdi` |
| **CDI total** | Real: `∏(1 + r_LFTS11) − 1` a partir do ETF LFTS11.SA (It Now Tesouro Selic) baixado por A1_Download |
| **Valor atual** | 717% do CDI |
| **Sub-texto** | "CDI +3,68% no período" |
| **Nota** | Métrica padrão de lâminas de fundos brasileiros. O CDI é derivado do preço diário do LFTS11.SA (dados reais do yfinance), com fallback automático para SELIC flat rate se LFTS11 não estiver no StockDataDB. |

### 6. Volatilidade

| Item | Valor |
|---|---|
| **Fórmula** | `std(r_t, ddof=1) × √252` |
| **Fonte** | `dashboard_latest.json → real.twr.volatility` |
| **Origem no backend** | `D_Publish.py → _compute_real_metrics()` |
| **Dados de entrada** | Mesma série TWR diária que os cards 4 e 5 |
| **Valor atual** | 23,06% |
| **Sub-texto** | "sharpe 5,61" |

### 7. Ibovespa

| Item | Valor |
|---|---|
| **Fórmula** | `∏(1 + bench_r_t) − 1` para as mesmas datas da série TWR |
| **Fonte** | `dashboard_latest.json → real.benchmark.total_return` |
| **Origem no backend** | `D_Publish.py → _compute_real_metrics()` usando `portfolio_timeseries.csv → benchmark1_daily_return` |
| **Composição** | ^BVSP (Ibovespa) |
| **Valor atual** | +23,62% |
| **Janela temporal** | Mesmas datas que card 4 (2025-10-17 → 2026-03-13, 68 pregões) |
| **Sub-texto** | "mesmo período" |
| **Link com gráfico** | ✅ Corresponde exatamente ao endpoint da linha "Ibovespa" (base 100 → 123,62) |

### 8. Alpha vs Ibovespa

| Item | Valor |
|---|---|
| **Fórmula** | `twr.total_return − benchmark.total_return` = `26,37% − 23,62%` |
| **Fonte** | `dashboard_latest.json → real.alpha.total` |
| **Valor atual** | +2,75% |
| **Sub-texto** | "TWR − bench" |
| **Nota** | ✅ Ambos os lados usam TWR, mesmas datas, mesma metodologia. Comparação justa. |

---

## Gráfico (linha)

### Linha: Portfólio

| Item | Valor |
|---|---|
| **Fórmula** | `idx[0] = 100; idx[i] = idx[i−1] × (1 + portfolio_return[i])` — computado no JS |
| **Fonte** | `portfolio_real_daily.csv → portfolio_return` |
| **Composição** | 12 ativos rastreados pelo B4 (100% de cobertura) |
| **Valor final** | 126,37 (= +26,37% TWR) |
| **Janela temporal** | 2025-10-17 → 2026-03-13 (68 pregões, sem fins de semana) |
| **Link com cards** | ✅ Endpoint = card "Retorno TWR" (+26,37%) |

### Linha: Ibovespa

| Item | Valor |
|---|---|
| **Fórmula** | `idx[0] = 100; idx[i] = idx[i−1] × (1 + benchmark_return[i])` — computado no JS |
| **Fonte** | `portfolio_real_daily.csv → benchmark_return` |
| **Valor final** | 123,62 (= +23,62%) |
| **Janela temporal** | Mesmas datas que a linha Portfólio |
| **Link com cards** | ✅ Endpoint = card "Ibovespa" (+23,62%) |

### Linha: CDI

| Item | Valor |
|---|---|
| **Fórmula** | `idx[0] = 100; idx[i] = idx[i−1] × (1 + cdi_return[i])` — computado no JS |
| **Fonte** | `portfolio_real_daily.csv → cdi_return` |
| **CDI diário** | Real: retorno diário de LFTS11.SA (It Now Tesouro Selic ETF), baixado por A1_Download e armazenado em StockDataDB.csv |
| **Valor final** | 103,68 (= +3,68%) |
| **Cor** | Dourado (#fcc419), tracejado curto |
| **Nota** | Linha quase reta mas com leve variação real (vs. a versão sintética anterior que era perfeitamente reta). Serve como referência visual do "custo de oportunidade" da renda fixa. Fallback para SELIC flat rate se LFTS11 não estiver disponível. |

### Capacidade de rebase dinâmico

O CSV contém **apenas retornos diários** (sem índices acumulados). O JS compõe `∏(1 + r)` a partir da data início. Isso permite rebasar a qualquer sub-período (3M, 6M, YTD, etc.) sem mudanças no backend.

---

## Tabela de Performance por Janela

Abaixo do gráfico de linhas, uma tabela e um gráfico de barras horizontais comparam retornos em janelas temporais padronizadas.

| Janela | Portfólio | Ibovespa | CDI | % do CDI |
|---|---|---|---|---|
| YTD | +26,96% | +14,18% | +2,86% | ~943% |
| 3 meses | +26,96% | +14,18% | +2,86% | ~943% |
| 6 meses | +26,37% | +23,62% | +3,68% | ~717% |

**Nota:** Os valores de CDI agora vêm de dados reais do LFTS11.SA (diferem do SELIC flat anterior).

**Fonte:** `dashboard_latest.json → real.performance → {YTD, 3M, 6M, 12M, 24M}` — cada janela inclui `portfolio`, `benchmark`, `cdi`, e `pct_cdi`.

**Gráfico de barras:** Barras horizontais agrupadas (Portfólio azul, Ibovespa cinza, CDI dourado) para comparação visual imediata.

---

## Métricas adicionais em `dashboard_latest.json`

Além dos 8 cards, o backend computa e disponibiliza métricas extras na mesma série TWR:

| Métrica | Caminho JSON | Valor atual | Fórmula |
|---|---|---|---|
| % do CDI | `real.twr.pct_cdi` | 717% | `total_return / cdi_total × 100` |
| Risk-Free Annual | `real.twr.risk_free_annual` | 15,03% | CDI annualized (from LFTS11 real data) |
| Annualize Safe | `real.meta.annualize_safe` | false | `trading_days >= 252` |
| CDI Total Return | `real.cdi.total_return` | 3,68% | `∏(1 + r_LFTS11) − 1` (real data) |
| CDI Annual Rate | `real.cdi.annual_rate` | 15,03% | Annualized from LFTS11 real data |
| CDI Source | `real.cdi.source` | LFTS11.SA | Ticker used (or "SELIC flat rate (fallback)") |
| Sharpe | `real.twr.sharpe` | 5,47 | `(annual_return − rf) / volatility` |
| Sortino | `real.twr.sortino` | 9,23 | `(annual_return − rf) / downside_dev` |
| Max Drawdown | `real.twr.max_drawdown` | 5,85% | Max peak-to-trough do índice TWR |
| Calmar | `real.twr.calmar` | 24,15 | `annual_return / max_drawdown` |
| Beta | `real.relative.beta` | 0,86 | `cov(r_port, r_bench) / var(r_bench)` |
| Tracking Error | `real.relative.tracking_error` | 17,91% | `std(r_port − r_bench) × √252` |
| Information Ratio | `real.relative.information_ratio` | 0,60 | `alpha_annual / tracking_error` |
| Correlation | `real.relative.correlation` | 0,66 | `corr(r_port, r_bench)` |
| Benchmark Annual | `real.benchmark.annual_return` | 130,46% | `(1 + bench_total)^(252/n) − 1` |
| Alpha Annual | `real.alpha.annual` | 10,70% | `annual_return − benchmark_annual` |

---

## Fontes de dados

| Arquivo | O que contém | Universo | Gerado por |
|---|---|---|---|
| `ledger.csv` | Todas as 42 transações | **Todos** os ativos | B1 + B12 |
| `ledger_positions.json` | Snapshot atual: qty, invested, price, pnl por ativo | **Todos** os ativos ativos (9 posições) | B2 (v2.1.0, shared ticker norm) |
| `portfolio_history.csv` | Valor diário por ativo: date, symbol, qty, price, value | **Todos** os ativos (12 symbols, 100% cobertura) | B4 (v3.1.0, shared ticker norm, sem weekends) |
| `portfolio_real_daily.csv` | Retornos diários TWR + benchmark + CDI, só dias úteis | **Portfólio real** | D_Publish (v3.1.0, Step 4a) |
| `dashboard_latest.json` | Métricas consolidadas: model + real (TWR, CDI, snapshot, relative) | **Portfólio real** (seção `real`) | D_Publish (v3.1.0, Steps 4b/4c) |
| `portfolio_timeseries.csv` | Simulação modelo: portfolio_daily_return, benchmark1_daily_return | **Modelo** (5 ativos GA) | A4 |
| `StockDataDB.csv` | Preços diários de todos os tickers + benchmarks (incl. LFTS11.SA) | **Todos** + benchmarks | A1_Download |
| `parameters/benchmarks.txt` | Lista de benchmarks: ^BVSP (Ibovespa), LFTS11.SA (CDI proxy) | Config | Manual |

---

## Inconsistências corrigidas

| # | Problema original | Status | Como foi corrigido |
|---|---|---|---|
| **A** | Cards 4,5,6 usavam dados do portfólio **modelo** | ✅ Corrigido | `D_Publish._compute_real_metrics()` calcula de `portfolio_real_daily.csv` (portfólio real) |
| **B** | Alpha comparava MWR (card 3) com TWR (card 7) | ✅ Corrigido | Alpha agora = `twr.total_return − benchmark.total_return` (TWR em ambos os lados) |
| **C** | Gráfico usava universo diferente dos cards | ✅ Corrigido | Gráfico e cards TWR usam mesma série (`portfolio_real_daily.csv`) |
| **D** | `portfolio_history.csv` não rastreava todos os ativos | ✅ Corrigido | Shared ticker normalization (T1/T2): strip de modifiers EX/EDS/ED, cobertura 100% |
| **E** | Ibovespa: gráfico ≠ card (weekends diluíam retorno) | ✅ Corrigido | B4 exclui weekends (T3); gráfico e card usam mesmas datas |
| **F** | `twr_total_return` vinha do modelo | ✅ Corrigido | `real.twr.total_return` vem da série TWR real, não de A4 |

### Correções técnicas implementadas

| ID | Fix | Arquivo(s) | Versão |
|---|---|---|---|
| T1 | Shared ticker normalization (EX/EDS/ED modifier stripping) | `shared_tools/ticker_normalization.py`, `B4_Portfolio_History.py` | B4 v3.1.0 |
| T2 | Aggregate by resolved symbol (VULC3 merge, AXIA6 net-zero) | `B2_Consolidate_Ledger.py` | B2 v2.1.0 |
| T3 | Exclude weekends from portfolio_history.csv | `B4_Portfolio_History.py` | B4 v3.1.0 |
| M1 | New `portfolio_real_daily.csv` (daily TWR returns) | `D_Publish.py` Step 4a | D v3.0.0 |
| M2 | Compute real TWR metrics from daily series | `D_Publish.py` Step 4b | D v3.0.0 |
| M3 | Restructure `dashboard_latest.json → real` | `D_Publish.py` Step 4c | D v3.0.0 |
| M4 | Frontend consumes new structure + real daily CSV | `1_portfolio.html` | — |
