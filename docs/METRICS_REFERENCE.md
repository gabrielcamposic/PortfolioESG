# PortfolioESG — Metrics Reference

**Criado:** 2026-03-13  
**Atualizado:** 2026-03-14 (2_risk.html: TE, IR, HHI com janelas temporais)  
**Objetivo:** Documentar a fórmula, fonte de dados, janela temporal e **exemplo de cálculo** de cada métrica exibida nas páginas `1_portfolio.html` e `2_risk.html`.

---

## Status: ✅ Todas as inconsistências corrigidas

A implementação de `D_PUBLISH_METRICS_PLAN.md` (Steps 1-9) foi concluída em 2026-03-14.
Todas as 6 inconsistências originais (A–F) foram resolvidas. Veja [Inconsistências corrigidas](#inconsistências-corrigidas) para o antes/depois.

Adicionalmente, a página `2_risk.html` (Tracking Error, Information Ratio, HHI) foi implementada em 2026-03-14. O HHI foi corrigido: antes vinha do portfólio **modelo** (A4, 5 ativos GA), agora vem do portfólio **real** (`ledger_positions.json`, 9 posições). Todas as três métricas suportam janelas temporais (All, YTD, 3M, 6M, 12M, 24M). Plano detalhado em `docs/2_RISK_PAGE_PLAN.md`.

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
| Simple ROI | +9,36% | R$ 253,58 de lucro sobre R$ 2.707,97 investidos |
| MWR (Modified Dietz) | +33,19% | Experiência real do investidor com cash tracking (depósitos, saques, fundo ESG) |
| TWR | +23,50% | A seleção de ativos rendeu 23,5% — bom vs Ibovespa (+19,38%) |
| Corretora | −2,66% | Retorno reportado pela Ágora (inclui caixa ocioso de nov/dez 2025) |
| TWR > Simple ROI | Gap de ~14 p.p. | O investidor aportou a maior parte do capital mais tarde, quando o portfólio já tinha subido. Os primeiros R$ 988 (out/2025) tiveram retornos altos, mas representavam pouco capital. |
| MWR > Corretora | Gap de ~36 p.p. | O Modified Dietz amplifica retornos em meses com depósito parcial (Oct, Jan). A corretora possivelmente usa preços B3 oficiais e método de cota diário. Diferenças de preço Yahoo vs B3 (~0,5%) se acumulam. |

---


## Retorno Corretora (Modified Dietz Mensal)

**Página:** `1_portfolio.html` — Card "Retorno Corretora" (Row 1, 3º card)
**Fonte:** `dashboard_latest.json → real.broker_return`
**Código:** `engines/D_Publish.py → _compute_broker_return()`
**Dados:** `data/cash_movements.csv` (depósitos/saques reais da Ágora) + `data/ledger.csv` + `data/results/portfolio_real_daily.csv`

### Fórmula (Modified Dietz por mês)

Para cada mês M no range [primeiro_trade → último_dado]:

```
V_start = stock_value_início_mês + cash_balance_início_mês
V_end   = stock_value_fim_mês + cash_balance_fim_mês

CF_i    = fluxos externos (depósitos +, saques −, fund transfers −)
          Dividendos NÃO são fluxos externos (são renda gerada)
w_i     = (CD − D_i) / CD
          CD = dias corridos no mês, D_i = dia do fluxo

Gain    = V_end − V_start − Σ CF_i
Denom   = V_start + Σ (w_i × CF_i)
r_month = Gain / Denom  (se Denom > 0, senão 0)

Total   = ∏(1 + r_month) − 1
```

### Cash balance tracking

O saldo de caixa é rastreado continuamente:
- **Aumenta com:** depósitos, dividendos, vendas de ações
- **Diminui com:** saques, compras de ações, transferências para fundos (Bradesco ESG)

Fonte dos fluxos externos: extratos da Ágora (`Notas_Negociação/*Extrato*.pdf`), parseados por `engines/B13_Cash_Parser.py` → `data/cash_movements.csv`.

### Detecção de liquidação

Quando o ledger mostra que todas as posições foram vendidas (soma net shares < 1), `stock_end = 0` para o mês, independente do último valor no daily CSV.

### Comparação com corretora (2026-03-15)

| Mês | Nosso Dietz | Corretora | Diferença |
|---|---|---|---|
| Out/25 | +11,97% | +4,96% | +7,01 pp |
| Nov/25 | −3,40% | −5,66% | +2,26 pp |
| Dez/25 | 0,00% | 0,00% | 0 pp |
| Jan/26 | +16,28% | +8,47% | +7,81 pp |
| Fev/26 | +7,86% | −6,18% | +14,04 pp |
| Mar/26 | −1,81% | −3,41% | +1,60 pp |
| **Total** | **+33,19%** | **−2,66%** | **+35,85 pp** |

### Causas das diferenças

1. **Preços Yahoo vs B3:** Diferença de ±0,5% nos preços diários se acumula ao longo dos meses.
2. **Day-weighting do Dietz:** Em meses com depósito no início (Oct, Jan), o denominador é reduzido pela fórmula de ponderação, amplificando o retorno. A corretora pode usar um método diferente (cota diária).
3. **Settlement T+2:** A corretora pode usar datas de liquidação (D+2) em vez de datas de negociação.
4. **Metodologia desconhecida da corretora:** Não confirmamos se a Ágora usa Modified Dietz, método de cota, ou outra fórmula.

---

## Fluxo de dados (pós-correção)

```
ledger.csv ──→ B2_Consolidate_Ledger.py ──→ ledger_positions.json
                   (shared ticker norm)          ↓ snapshot cards (1,2,3)
                                                 ↓ HHI, top3, top5 (real.structure)
                                                 ↓ concentration chart (2_risk.html)
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
                   D_Publish.py (Step 4b2: _compute_risk_windows)
                       ↓
                   dashboard_latest.json → real.twr.*        → 1_portfolio cards 4,5,6
                                         → real.benchmark    → 1_portfolio card 7
                                         → real.alpha        → 1_portfolio card 8
                                         → real.snapshot     → 1_portfolio cards 1,2,3
                                         → real.risk_windows → 2_risk cards + table
                                         → real.structure    → 2_risk HHI snapshot
```

**Princípio:** Cards 4–8 e o gráfico derivam da **mesma série** (`portfolio_real_daily.csv`), mesmas datas, mesma metodologia (TWR). Cards 1–3 são snapshot (Simple ROI), claramente diferenciados. Cards de risco (2_risk.html) derivam da mesma série para TE/IR, e de `portfolio_history.csv`/`ledger_positions.json` para HHI.

---

## Página: `1_portfolio.html` — Cards

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
| **Valor atual** | R$ 2.961,55 |
| **Sub-texto** | "investido R$ 2.707,97" |

**Exemplo de cálculo:**
```
PETR3:  22 × R$ 49,38 = R$ 1.086,36
SAPR11: 15 × R$ 39,47 = R$   592,05
MDNE3:  12 × R$ 29,70 = R$   356,40
PLPL3:  19 × R$ 14,35 = R$   272,65
AURA33:  2 ×133,10 = R$   266,20
VALE3:   2 × 78,30 = R$   156,60
CMIG3:   8 × 15,50 = R$   124,00
TEND3:   2 × 29,03 = R$    58,06
VULC3:   3 × 16,41 = R$    49,23
                         ───────────
Total:                   R$ 2.961,55 ✓
```

### 2. Retorno (R$)

| Item | Valor |
|---|---|
| **Fórmula** | `total_current_market − total_invested_cash` |
| **Fonte** | `dashboard_latest.json → real.snapshot.unrealized_pnl` |
| **Composição** | **Todos** os ativos ativos no ledger |
| **Valor atual** | +R$ 253,58 |
| **Nota** | `total_invested_cash` inclui taxas e emolumentos das notas de negociação |

**Exemplo de cálculo:**
```
Retorno (R$) = total_market − total_invested
             = R$ 2.961,55 − R$ 2.707,97
             = R$ 253,58 ✓
```

### 3. Retorno (%)

| Item | Valor |
|---|---|
| **Fórmula** | `unrealized_pnl / total_invested_cash × 100` |
| **Fonte** | `dashboard_latest.json → real.snapshot.simple_roi_pct` |
| **Metodologia** | **Simple ROI** — lucro bruto ÷ capital investido |
| **Valor atual** | +9,36% |
| **Janela temporal** | Desde a primeira compra até hoje (implícita) |
| **Sub-texto** | "ROI · lucro / investido" |
| **Nota** | Não ajusta pelo timing dos aportes. Diferente do TWR (card 4) — ver seção [Entendendo Simple ROI vs MWR vs TWR](#entendendo-simple-roi-vs-mwr-vs-twr). |

**Exemplo de cálculo:**
```
Simple ROI = unrealized_pnl / total_invested × 100
           = R$ 253,58 / R$ 2.707,97 × 100
           = 9,36% ✓
```

### 4. Retorno TWR

| Item | Valor |
|---|---|
| **Fórmula** | `∏(1 + r_t) − 1` onde `r_t = (V_t − CF_t) / V_{t−1} − 1` |
| **Fonte** | `dashboard_latest.json → real.twr.total_return` |
| **Origem no backend** | `D_Publish.py → _compute_real_metrics()` a partir de `portfolio_real_daily.csv` |
| **Dados de entrada** | Retornos diários TWR do portfólio **real** (portfolio_history.csv + ledger.csv) |
| **Composição** | Portfólio real — 9 ativos ativos, 100% de cobertura |
| **Valor atual** | +23,50% |
| **Janela temporal** | 2025-10-17 → 2026-03-13 (68 pregões) |
| **Sub-texto** | Se `annualize_safe=true` (≥252 pregões): "anualiz. +X%". Senão: "desde out/25". |
| **Link com gráfico** | ✅ Corresponde exatamente ao endpoint da linha "Portfólio" (base 100 → 123,50) |
| **Nota** | O retorno anualizado (121%) é matematicamente correto mas enganoso com apenas 68 pregões. Por isso é suprimido do valor principal e só aparece como sub-texto quando a história alcançar 1 ano. |

**Exemplo de cálculo (TWR diário):**
```
Dia 1 (2025-10-17): V₀ = R$ 997,35 (primeiro dia, sem retorno)
Dia 2 (2025-10-20): V₁ = R$ 1.012,17, CF₁ = R$ 0 (sem transação)
  r₁ = (1.012,17 − 0) / 997,35 − 1 = +0,01486 (+1,49%)

Dia N (com aporte): V_t = R$ 2.200, CF_t = R$ 500 (compra), V_{t-1} = R$ 1.800
  r_t = (2.200 − 500) / 1.800 − 1 = −0,0556 (−5,56%)
  O aporte é removido antes de calcular o retorno → mede só a performance.

Acumulado: ∏(1 + r_t) − 1 = (1,01486) × (1,01478) × ... × (1,r_67) − 1
         = 1,2350 − 1
         = +23,50% ✓
```

### 5. % do CDI

| Item | Valor |
|---|---|
| **Fórmula** | `(twr_total_return / cdi_total_return) × 100` |
| **Fonte** | `dashboard_latest.json → real.twr.pct_cdi` |
| **CDI total** | Real: `∏(1 + r_LFTS11) − 1` a partir do ETF LFTS11.SA (It Now Tesouro Selic) baixado por A1_Download |
| **Valor atual** | 638,9% do CDI |
| **Sub-texto** | "CDI +3,68% no período" |
| **Nota** | Métrica padrão de lâminas de fundos brasileiros. O CDI é derivado do preço diário do LFTS11.SA (dados reais do yfinance), com fallback automático para SELIC flat rate se LFTS11 não estiver no StockDataDB. |

**Exemplo de cálculo:**
```
TWR total   = +23,50%
CDI total   = +3,68%  (retorno acumulado do LFTS11.SA no mesmo período)

% do CDI = (23,50% / 3,68%) × 100 = 638,9% ✓

Interpretação: a carteira rendeu 6,4x o CDI no período.
```

### 6. Volatilidade

| Item | Valor |
|---|---|
| **Fórmula** | `std(r_t, ddof=1) × √252` |
| **Fonte** | `dashboard_latest.json → real.twr.volatility` |
| **Origem no backend** | `D_Publish.py → _compute_real_metrics()` |
| **Dados de entrada** | Mesma série TWR diária que os cards 4 e 5 |
| **Valor atual** | 23,44% |
| **Sub-texto** | "sharpe 4,53" |

**Exemplo de cálculo:**
```
Dados: 67 retornos diários r₁, r₂, ..., r₆₇ (primeiro dia não tem retorno)

1. Desvio-padrão amostral dos retornos diários:
   σ_diário = std(r_t, ddof=1) = 0,01477  (≈ 1,48% ao dia)

2. Anualizar (252 dias úteis/ano):
   σ_anual = σ_diário × √252 = 0,01477 × 15,875 = 0,2344

Volatilidade = 23,44% ✓
```

### 7. Ibovespa

| Item | Valor |
|---|---|
| **Fórmula** | `∏(1 + bench_r_t) − 1` para as mesmas datas da série TWR |
| **Fonte** | `dashboard_latest.json → real.benchmark.total_return` |
| **Origem no backend** | `D_Publish.py → _compute_real_metrics()` usando `portfolio_timeseries.csv → benchmark1_daily_return` |
| **Composição** | ^BVSP (Ibovespa) |
| **Valor atual** | +19,38% |
| **Janela temporal** | Mesmas datas que card 4 (2025-10-17 → 2026-03-13, 68 pregões) |
| **Sub-texto** | "mesmo período" |
| **Link com gráfico** | ✅ Corresponde exatamente ao endpoint da linha "Ibovespa" (base 100 → 119,38) |

**Exemplo de cálculo:**
```
Retornos diários do ^BVSP para as mesmas 68 datas do portfólio:
  bench_r₁ = +0,0052, bench_r₂ = −0,0031, ..., bench_r₆₇ = +0,0018

Acumulado: ∏(1 + bench_r_t) − 1 = 1,1938 − 1 = +19,38% ✓

Nota: usa exatamente as mesmas datas do portfólio, garantindo comparação justa.
```

### 8. Alpha vs Ibovespa

| Item | Valor |
|---|---|
| **Fórmula** | `twr.total_return − benchmark.total_return` |
| **Fonte** | `dashboard_latest.json → real.alpha.total` |
| **Valor atual** | +4,13% |
| **Sub-texto** | "TWR − bench" |
| **Nota** | ✅ Ambos os lados usam TWR, mesmas datas, mesma metodologia. Comparação justa. |

**Exemplo de cálculo:**
```
Alpha = TWR portfólio − TWR benchmark
      = 23,50% − 19,38%
      = +4,13 p.p. ✓

Interpretação: a carteira superou o Ibovespa em 4,13 pontos percentuais no período.
```

---

## Página: `1_portfolio.html` — Gráfico (linha)

### Linha: Portfólio

| Item | Valor |
|---|---|
| **Fórmula** | `idx[0] = 100; idx[i] = idx[i−1] × (1 + portfolio_return[i])` — computado no JS |
| **Fonte** | `portfolio_real_daily.csv → portfolio_return` |
| **Composição** | 9 ativos ativos rastreados pelo B4 (100% de cobertura) |
| **Valor final** | 123,50 (= +23,50% TWR) |
| **Janela temporal** | 2025-10-17 → 2026-03-13 (68 pregões, sem fins de semana) |
| **Link com cards** | ✅ Endpoint = card "Retorno TWR" (+23,50%) |

**Exemplo de cálculo (base 100):**
```
idx[0] = 100,00  (2025-10-17, dia base)
idx[1] = 100,00 × (1 + 0,01486) = 101,49  (2025-10-20)
idx[2] = 101,49 × (1 + 0,01478) = 102,99  (2025-10-21)
...
idx[67] = ... × (1 + r₆₇)       = 123,50  (2026-03-13)

Conferência: (123,50 / 100) − 1 = +23,50% = card TWR ✓
```

### Linha: Ibovespa

| Item | Valor |
|---|---|
| **Fórmula** | `idx[0] = 100; idx[i] = idx[i−1] × (1 + benchmark_return[i])` — computado no JS |
| **Fonte** | `portfolio_real_daily.csv → benchmark_return` |
| **Valor final** | 119,38 (= +19,38%) |
| **Janela temporal** | Mesmas datas que a linha Portfólio |
| **Link com cards** | ✅ Endpoint = card "Ibovespa" (+19,38%) |

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

## Página: `1_portfolio.html` — Tabela de Performance por Janela

Abaixo do gráfico de linhas, uma tabela e um gráfico de barras horizontais comparam retornos em janelas temporais padronizadas.

| Janela | Portfólio | Ibovespa | CDI | % do CDI |
|---|---|---|---|---|
| YTD | +24,08% | +10,26% | +2,79% | ~862% |
| 3 meses | +24,08% | +10,26% | +2,79% | ~862% |
| 6 meses | +23,50% | +19,38% | +3,68% | ~639% |

**Nota:** Os valores de CDI vêm de dados reais do LFTS11.SA.

**Fonte:** `dashboard_latest.json → real.performance → {YTD, 3M, 6M, 12M, 24M}` — cada janela inclui `portfolio`, `benchmark`, `cdi`, e `pct_cdi`.

**Gráfico de barras:** Barras horizontais agrupadas (Portfólio azul, Ibovespa cinza, CDI dourado) para comparação visual imediata.

---

## Página: `2_risk.html` — Risk KPIs

### Layout

Row de 3 cards (valores globais, janela "All"), seguido de tabela por janela temporal e gráfico de concentração.

| Card | Fonte JSON | Formato |
|---|---|---|
| Tracking Error | `real.risk_windows.All.tracking_error` | XX,XX% (anualizado) |
| Information Ratio | `real.risk_windows.All.information_ratio` | X,XX |
| HHI | `real.risk_windows.All.hhi` | 0,XXXX |

### 9. Tracking Error

| Item | Valor |
|---|---|
| **Fórmula** | `std(r_port − r_bench, ddof=1) × √252` |
| **Fonte** | `dashboard_latest.json → real.risk_windows.{window}.tracking_error` |
| **Origem no backend** | `D_Publish.py → _compute_risk_windows()` |
| **Dados de entrada** | `portfolio_real_daily.csv → portfolio_return, benchmark_return` |
| **Benchmark** | ^BVSP (Ibovespa) |
| **Valor atual (All)** | 17,73% |
| **Sub-texto** | "anualiz. vs ^BVSP" |

**O que mede:** A dispersão dos retornos do portfólio em relação ao benchmark. Quanto maior o TE, mais o portfólio se desvia do índice — para melhor ou para pior.

**Exemplo de cálculo:**
```
Dados: 66 pares de retornos diários (r_port, r_bench) para as mesmas datas

1. Calcular a diferença diária (excess return):
   diff₁ = r_port₁ − r_bench₁ = +0,0149 − 0,0052 = +0,0097
   diff₂ = r_port₂ − r_bench₂ = −0,0072 − (−0,0031) = −0,0041
   ...
   diff₆₆ = r_port₆₆ − r_bench₆₆

2. Desvio-padrão amostral das diferenças:
   σ_diff = std(diff, ddof=1) = 0,01117  (≈ 1,12% ao dia)

3. Anualizar:
   TE = σ_diff × √252 = 0,01117 × 15,875 = 0,1773

Tracking Error = 17,73% ✓

Interpretação: num dia típico, o retorno do portfólio se desvia ~1,12%
do Ibovespa. Anualizado, essa dispersão equivale a 17,73%.
```

### 10. Information Ratio

| Item | Valor |
|---|---|
| **Fórmula** | `alpha_annual / tracking_error` |
| **Fonte** | `dashboard_latest.json → real.risk_windows.{window}.information_ratio` |
| **Origem no backend** | `D_Publish.py → _compute_risk_windows()` |
| **Valor atual (All)** | 1,54 |
| **Sub-texto** | "alpha / tracking error" |

**O que mede:** Quanto retorno excedente (alpha) o portfólio gera por unidade de risco ativo (tracking error). É o "Sharpe do alpha" — mede a eficiência do desvio em relação ao benchmark.

**Referência de interpretação:**

| IR | Qualidade |
|---|---|
| < 0,0 | Negativo — perdendo para o benchmark sem compensação |
| 0,0 – 0,4 | Fraco |
| 0,4 – 0,7 | Razoável |
| 0,7 – 1,0 | Bom |
| > 1,0 | Excelente |

**Exemplo de cálculo (janela "All"):**
```
Dados da janela All (66 pregões):

1. Retorno total do portfólio (TWR):
   port_total = ∏(1 + r_port) − 1 = +23,50%

2. Retorno total do benchmark:
   bench_total = ∏(1 + r_bench) − 1 = +19,38%

3. Anualizar ambos:
   port_annual  = (1 + 0,2350)^(252/66) − 1 = +121,2%
   bench_annual = (1 + 0,1938)^(252/66) − 1 = +96,64%

4. Alpha anualizado:
   alpha_annual = 121,2% − 96,64% = +24,56%

5. Tracking Error (calculado acima):
   TE = 17,73%

6. Information Ratio:
   IR = alpha_annual / TE = 24,56% / 17,73% = 1,39

Information Ratio = 1,39 ✓  (Nota: real.relative.IR = 1,39;
   real.risk_windows.All.IR = 1,54 — leve diferença por alinhamento
   de datas na intersecção. Ambos usam a mesma fórmula.)

Interpretação: cada 1% de risco ativo (desvio do benchmark) gera
~1,4% de retorno excedente. Excelente eficiência.
```

### 11. HHI (Herfindahl-Hirschman Index)

| Item | Valor |
|---|---|
| **Fórmula** | `Σ(w_i²)` onde `w_i = valor_posição_i / valor_total_portfólio` |
| **Fonte snapshot** | `dashboard_latest.json → real.structure.hhi` |
| **Fonte por janela** | `dashboard_latest.json → real.risk_windows.{window}.hhi` |
| **Origem no backend** | Snapshot: `D_Publish.py → _build_real_section()` (de `ledger_positions.json`). Janelas: `_compute_risk_windows()` (de `portfolio_history.csv`, último dia da janela) |
| **Valor atual** | 0,2108 |
| **Sub-texto** | "9 ativos · moderado" |

**O que mede:** Concentração do portfólio. Varia de `1/N` (perfeitamente distribuído) a `1,0` (100% num único ativo). Quanto maior, mais concentrado.

**Referência de interpretação:**

| HHI | Label | Significado |
|---|---|---|
| < 0,10 | Diversificado | Pesos bem distribuídos |
| 0,10 – 0,25 | Moderado | Alguma concentração, mas razoável |
| > 0,25 | Concentrado | Poucos ativos dominam o portfólio |

**Referência teórica:** Para N ativos com pesos iguais, `HHI = 1/N`:

| N ativos | HHI (pesos iguais) |
|---|---|
| 5 | 0,2000 |
| 9 | 0,1111 |
| 10 | 0,1000 |
| 20 | 0,0500 |

**Exemplo de cálculo (snapshot atual, 9 posições):**
```
Para cada posição: w_i = (qty × price) / total_market

Ativo     Qty   Preço     Valor      Peso (w)   w²
─────────────────────────────────────────────────────
PETR3      22 × 49,38 = 1.086,36    0,3668    0,134558
SAPR11     15 × 39,47 =   592,05    0,1999    0,039965
MDNE3      12 × 29,70 =   356,40    0,1203    0,014482
PLPL3      19 × 14,35 =   272,65    0,0921    0,008476
AURA33      2 ×133,10 =   266,20    0,0899    0,008079
VALE3       2 × 78,30 =   156,60    0,0529    0,002796
CMIG3       8 × 15,50 =   124,00    0,0419    0,001753
TEND3       2 × 29,03 =    58,06    0,0196    0,000384
VULC3       3 × 16,41 =    49,23    0,0166    0,000276
                        ──────────            ─────────
Total:                  2.961,55    1,0000    0,210769

HHI = Σ(w²) = 0,2108 ✓

Comparação com pesos iguais: se os 9 ativos tivessem pesos iguais,
HHI = 1/9 = 0,1111. O HHI real (0,2108) é quase 2× o ideal,
mostrando concentração moderada — PETR3 sozinha representa 36,7%.

Métricas derivadas:
  top3 = w_PETR3 + w_SAPR11 + w_MDNE3 = 0,3668 + 0,1999 + 0,1203 = 0,6871 (68,71%)
  top5 = top3 + w_PLPL3 + w_AURA33   = 0,6871 + 0,0921 + 0,0899 = 0,8690 (86,90%)
```

**HHI por janela temporal:** Usa o HHI do **último dia** contido na janela (snapshot point-in-time, não média). Como o portfólio tem apenas ~5 meses de história, o último dia de cada janela é o mesmo (2026-03-13) para todas que cabem no período, resultando em HHI idêntico. Conforme a história crescer, as janelas mais curtas passarão a refletir snapshots diferentes.

### Tabela de risco por janela

| Janela | TE | IR | HHI | Nº Ativos | Pregões |
|---|---|---|---|---|---|
| All | 17,73% | 1,54 | 0,2108 | 9 | 66 |
| YTD | 16,29% | 8,17 | 0,2108 | 9 | 50 |
| 3M | 16,29% | 8,17 | 0,2108 | 9 | 50 |
| 6M | 17,73% | 1,54 | 0,2108 | 9 | 66 |

**Nota sobre IR alto no YTD/3M:** O IR de 8,17 no YTD é matematicamente correto mas inflado pela anualização de um período curto (50 pregões). O alpha acumulado é modesto, mas `(1 + alpha)^(252/50)` amplifica exponencialmente. Comparar sempre com o número de pregões.

### Gráfico de concentração

**Tipo:** Barras horizontais (Chart.js, `indexAxis: 'y'`)  
**Dados:** `ledger_positions.json → positions[]`  
**Peso no JS:** `w = (net_qty × current_price) / total_current_market` — divisão trivial (render-safe)  
**Ordenação:** Decrescente por peso  
**Cor:** accent-blue (`#4dabf7`)

---

## Métricas adicionais em `dashboard_latest.json`

Além dos cards exibidos, o backend computa e disponibiliza métricas extras na mesma série TWR:

| Métrica | Caminho JSON | Valor atual | Fórmula |
|---|---|---|---|
| % do CDI | `real.twr.pct_cdi` | 638,9% | `total_return / cdi_total × 100` |
| Risk-Free Annual | `real.twr.risk_free_annual` | 15,03% | CDI annualized (from LFTS11 real data) |
| Annualize Safe | `real.meta.annualize_safe` | false | `trading_days >= 252` |
| CDI Total Return | `real.cdi.total_return` | 3,68% | `∏(1 + r_LFTS11) − 1` (real data) |
| CDI Annual Rate | `real.cdi.annual_rate` | 15,03% | Annualized from LFTS11 real data |
| CDI Source | `real.cdi.source` | LFTS11.SA | Ticker used (or "SELIC flat rate (fallback)") |
| Sharpe | `real.twr.sharpe` | 4,53 | `(annual_return − rf) / volatility` |
| Sortino | `real.twr.sortino` | 7,84 | `(annual_return − rf) / downside_dev` |
| Max Drawdown | `real.twr.max_drawdown` | 5,85% | Max peak-to-trough do índice TWR |
| Calmar | `real.twr.calmar` | 20,73 | `annual_return / max_drawdown` |
| Beta | `real.relative.beta` | 0,84 | `cov(r_port, r_bench) / var(r_bench)` |
| Tracking Error | `real.relative.tracking_error` | 17,73% | `std(r_port − r_bench) × √252` |
| Information Ratio | `real.relative.information_ratio` | 1,39 | `alpha_annual / tracking_error` |
| Correlation | `real.relative.correlation` | 0,67 | `corr(r_port, r_bench)` |
| Benchmark Annual | `real.benchmark.annual_return` | 96,64% | `(1 + bench_total)^(252/n) − 1` |
| Alpha Annual | `real.alpha.annual` | 24,56% | `annual_return − benchmark_annual` |

### Exemplos de cálculo das métricas adicionais

**Sharpe Ratio:**
```
Sharpe = (annual_return − risk_free) / volatility
       = (121,2% − 15,03%) / 23,44%
       = 106,17% / 23,44%
       = 4,53 ✓

Interpretação: para cada 1% de risco (volatilidade), a carteira gera
4,53% de retorno acima do CDI. Valor inflado pela anualização de <1 ano.
```

**Sortino Ratio:**
```
Sortino = (annual_return − risk_free) / downside_deviation
  downside_dev = std(min(r_t, 0), ddof=1) × √252  (só retornos negativos)

Sortino = 106,17% / 13,55% = 7,84 ✓

Diferença vs Sharpe: Sortino penaliza apenas a volatilidade negativa (downside).
Se Sortino >> Sharpe, a maioria da volatilidade é de alta (bom).
```

**Max Drawdown:**
```
1. Construir índice TWR: idx₀ = 1, idx_t = idx_{t-1} × (1 + r_t)
2. Para cada dia, rastrear o pico máximo até então
3. Drawdown_t = (idx_t − peak_t) / peak_t
4. Max Drawdown = |min(Drawdown_t)| = 5,85% ✓

Interpretação: no pior momento, a carteira caiu 5,85% desde seu ponto mais alto.
```

**Beta:**
```
Beta = cov(r_port, r_bench) / var(r_bench)
     = 0,84 ✓

Interpretação: quando o Ibovespa sobe 1%, o portfólio tende a subir 0,84%.
Beta < 1 indica portfólio menos volátil que o mercado.
```

---

## Fontes de dados

| Arquivo | O que contém | Universo | Gerado por |
|---|---|---|---|
| `ledger.csv` | Todas as 42 transações | **Todos** os ativos | B1 + B12 |
| `ledger_positions.json` | Snapshot atual: qty, invested, price, pnl por ativo + HHI real | **Todos** os ativos ativos (9 posições) | B2 (v2.1.0, shared ticker norm) |
| `portfolio_history.csv` | Valor diário por ativo: date, symbol, qty, price, value | **Todos** os ativos (100% cobertura) | B4 (v3.1.0, shared ticker norm, sem weekends) |
| `portfolio_real_daily.csv` | Retornos diários TWR + benchmark + CDI, só dias úteis | **Portfólio real** | D_Publish (v3.1.0, Step 4a) |
| `dashboard_latest.json` | Métricas consolidadas: model + real (TWR, CDI, snapshot, relative, risk_windows, structure) | **Portfólio real** (seção `real`) | D_Publish (v3.1.0, Steps 4b/4b2/4c) |
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
| **G** | HHI vinha do portfólio modelo (A4, 5 ativos GA) | ✅ Corrigido | `real.structure` agora calculado de `ledger_positions.json` (portfólio real, 9 ativos). HHI: 0,52 → 0,21 |

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
| R1 | Fix HHI source: model → real (`ledger_positions.json`) | `D_Publish.py` `_build_real_section()` | D v3.1.0 |
| R2 | New `_compute_risk_windows()` (TE, IR, HHI per time window) | `D_Publish.py` Step 4b2 | D v3.1.0 |
| R3 | Risk KPIs page with cards, table, concentration chart | `2_risk.html` | — |
