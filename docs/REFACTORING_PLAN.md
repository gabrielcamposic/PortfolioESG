# PortfolioESG — Plano de Refatoração Backend + Frontend

**Início:** 2026-03-03  
**Última atualização:** 2026-03-09  
**Objetivo:** Racionalizar a produção e armazenamento de dados do pipeline para que o frontend seja puramente render, sem cálculos.

---

## Princípios Arquiteturais

1. **Cálculos no momento certo** — Cada engine grava resultados completos e autocontidos no momento do cálculo. Evita recálculos e elimina dúvida sobre a origem do número.
2. **Histórico individual, consolidação sob demanda** — CSVs append-only com `run_id` para cada engine. Consolidações são feitas por D_Publish para o frontend.
3. **Armazenamento em texto estático** — CSV para dados tabulares, JSON para hierárquicos, JSONL para históricos com estrutura aninhada.
4. **Fonte canônica única** — Todos os dados vivem em `data/`. `html/data/` contém apenas symlinks. Zero duplicação física.
5. **D_Publish como último transformador** — Cria symlinks e gera JSONs de conveniência (última linha de CSVs). Zero cálculos primários.
6. **Frontend render-only** — Recebe dados prontos via `html/data/`. Nenhum cálculo no browser.

---

## Pipeline de Dados (estado atual)

```
A1_Download.py    → data/findb/StockDataDB.csv, FinancialsDB.csv, skipped_tickers.json
A2_Scoring.py     → data/results/scored_stocks.csv, sector_pe.csv, correlation_matrix.csv
A3_Portfolio.py   → data/results/portfolio_results_db.csv, ga_fitness_noise_db.csv, latest_run_summary.json
A4_Analysis.py    → data/results/portfolio_timeseries.csv,
                    portfolio_diagnostics_history.csv, performance_attribution_history.csv,
                    asset_attribution_history.csv, performance_windows_history.csv

B1_Process_Notes  → data/transactions_parsed.csv, fees_parsed.csv, processed_notes.json
B2_Consolidate    → data/ledger.csv, ledger_positions.json
B4_Portfolio_Hist → data/portfolio_history.json

C_Optimized       → data/results/optimized_recommendation.json, optimized_portfolio_history.csv

D_Publish.py      → html/data/ (symlinks) + data/results/scored_targets.json,
                    pipeline_latest.json, mis_model_latest.json, mis_real_latest.json,
                    portfolio_diagnostics.json, performance_attribution.json
```

---

## Formato de Dados — Decisão

| Formato | Quando usar |
|---|---|
| **CSV** | Dados tabulares/planos, append-only (histórico), grande volume, leitura pandas/Excel |
| **JSON** | Dados hierárquicos/aninhados, snapshot (estado atual), consumo direto pelo browser |
| **JSONL** | Históricos com estrutura aninhada, append-friendly como CSV mas preserva hierarquia |

### Arquivos e formato recomendado

#### CSVs (manter)
| Arquivo | Engine | Descrição |
|---|---|---|
| `StockDataDB.csv` | A1 | Preços OHLCV (~41MB, ~600K linhas) |
| `FinancialsDB.csv` | A1 | Dados financeiros por ativo (~13K linhas) |
| `scored_stocks.csv` | A2 | Scoring histórico, append-only com run_id |
| `sector_pe.csv` | A2 | P/E mediano por setor, append-only |
| `correlation_matrix.csv` | A2 | Matriz N×N de correlação (overwrite) |
| `portfolio_results_db.csv` | A3 | Histórico de portfólios otimizados |
| `ga_fitness_noise_db.csv` | A3 | Convergência GA por geração/run |
| `portfolio_timeseries.csv` | A4 | Série temporal diária (overwrite) |
| `portfolio_diagnostics_history.csv` | A4 | Métricas por run |
| `performance_attribution_history.csv` | A4 | Brinson attribution por run |
| `asset_attribution_history.csv` | A4 | Attribution por ativo/run |
| `performance_windows_history.csv` | A4 | Janelas de performance (YTD, 3M, etc.) |
| `ledger.csv` | B2 | Transações consolidadas |
| `transactions_parsed.csv` | B1 | Transações brutas das notas |
| `fees_parsed.csv` | B1 | Taxas detalhadas |
| `*_performance.csv` (6) | Todos | Logs operacionais |

#### JSONs (manter)
| Arquivo | Engine | Descrição |
|---|---|---|
| `latest_run_summary.json` | A3 | Snapshot do melhor portfólio (a simplificar — Fase 2.3) |
| `optimized_recommendation.json` | C | Recomendação de rebalanceamento |
| `ledger_positions.json` | B2 | Posições atuais com totais |
| `scored_targets.json` | D | Mapa ticker→targetPrice |
| `pipeline_latest.json` | D | Projeção do portfólio modelo sobre capital real |
| `processed_notes.json` | B1 | Manifesto de notas processadas |
| `*_progress.json` (4) | A1-A3 | Status efêmero para frontend polling |

#### Mudanças de formato planejadas
| Arquivo | De → Para | Engine | Razão |
|---|---|---|---|
| `portfolio_history.json` | JSON → CSV | B4 | Série temporal com aninhamento desnecessário. CSV flat ~10x menor. |
| `optimized_portfolio_history.csv` | CSV → JSONL | C | Listas de stocks em campos CSV = parsing frágil. JSONL preserva arrays. |
| `skipped_tickers.json` | JSON → JSONL | A1 | ~1.5MB reescrito inteiro a cada skip. JSONL = append-only. |

#### Eliminações planejadas
| Arquivo | Razão |
|---|---|
| `portfolio_diagnostics.json` | Agora derivado por D_Publish (não mais escrito por A4) ✅ |
| `performance_attribution.json` | Agora derivado por D_Publish (não mais escrito por A4) ✅ |
| `mis_model_latest.json` + `mis_real_latest.json` | Consolidar em `dashboard_latest.json` |
| `cloud_cost_comparison.json` | Sem consumidor no pipeline/frontend |
| `resource_metrics.json` | Sem consumidor no pipeline/frontend |

---

## Fases de Implementação

### Fase 1 — Correções Críticas ✅ (2026-03-04)

> Bloqueavam um frontend funcional. Todas implementadas e validadas.

**1.1 Unificar `run_id` no pipeline A** ✅  
- `run_all.sh` e `A_Portfolio.sh` geram `PIPELINE_RUN_ID` via env var
- `A2_Scoring.py` e `A3_Portfolio.py` leem do env com fallback local
- `A4_Analysis.py` já lia de A3 via `portfolio_results_db.csv`
- **Validado:** A2, A3, A4 todos com `20260304-223802` na mesma run

**1.2 Adicionar totais a `ledger_positions.json`** ✅  
- `B2_Consolidate_Ledger.py` calcula `total_current_market`, `total_invested_cash`, `total_unrealized_pnl`
- **Validado:** `market=3688.38, invested=3427.61, pnl=260.77`
- **Consequência:** `pipeline_latest.json` agora tem projeções reais (antes todos `null`)

**1.3 Corrigir ticker inconsistency** ✅  
- `C_OptimizedPortfolio.py` usa `symbol` (Yahoo) em vez de `ticker` (broker name)
- **Validado:** zero broker names em `optimized_recommendation.json`; `"VULCABRAS ON ED NM.SA"` eliminado

**1.4 Corrigir case-sensitivity nos parâmetros** ✅  
- `anapar.txt`, `scorpar.txt`, `portpar.txt`, `downpar.txt`: `data/Results` → `data/results`
- Portabilidade Linux garantida

---

### Fase 2 — Eliminar Duplicações ✅ (2026-03-09)

> Removidas escritas duplicadas e dados inline volumosos. D_Publish assume geração de snapshots.

**2.1 Eliminar escrita dupla de `portfolio_timeseries.csv`** ✅  
- Removida segunda `to_csv()` hardcoded em `A4_Analysis.py` (redundante com `OUTPUT_CSV`)
- Arquivos: `engines/A4_Analysis.py`

**2.2 Eliminar JSONs snapshot redundantes** ✅  
- `A4_Analysis.py` não grava mais `portfolio_diagnostics.json` nem `performance_attribution.json`
- `D_Publish.py` v1.3.0: nova função `publish_derived_snapshots()` (Step 0) gera os snapshots a partir da última linha dos CSVs history
- Executa antes de `publish_symlink_files()` para que os symlinks apontem para os JSONs recém-gerados
- Arquivos: `engines/A4_Analysis.py`, `engines/D_Publish.py`

**2.3 Simplificar `latest_run_summary.json`** ✅  
- Removidos dados inline volumosos de `A3_Portfolio.py`:
  - `portfolio_timeseries` (~24KB) — dados existem em `portfolio_results_db.csv`
  - `stock_sparklines` — dados existem em `StockDataDB.csv`
  - `ga_fitness_history` — dados existem em `ga_fitness_noise_db.csv`
- Removido bloco de ~90 linhas que construía essas estruturas
- Mantido: `sector_exposure_list` (usado por `publish_mis_model()` em D_Publish)
- Redução de ~27KB para ~3KB
- Arquivos: `engines/A3_Portfolio.py`

---

### Fase 3 — Clareza Semântica e Formato (pendente)

**3.1 Renomear Sharpe modelo → `sharpe_forward`**  
- `A3_Portfolio.py`: campo `sharpe_ratio` → `sharpe_forward` em `portfolio_results_db.csv` e `latest_run_summary.json`
- A4 mantém `sharpe` (realizado). Sem ambiguidade.
- Arquivos: `engines/A3_Portfolio.py`

**3.2 Simplificar D_Publish — consolidar JSONs derivados**  
- Eliminar `mis_model_latest.json` e `mis_real_latest.json`
- Gerar um único `dashboard_latest.json` que agrega última linha de cada CSV history
- Zero cálculos, só formatação
- Arquivos: `engines/D_Publish.py`

**3.3 Migrar `portfolio_history.json` → CSV**  
- `B4_Portfolio_History.py` grava CSV flat: `date,symbol,qty,price,value,market_value,cost_basis,pnl,pnl_pct`
- De 91KB para ~10KB. Legível por pandas e browser.
- Posições por dia são reconstruíveis a partir das linhas do mesmo date.
- Arquivos: `engines/B4_Portfolio_History.py`, `engines/D_Publish.py`

**3.4 Migrar `optimized_portfolio_history.csv` → JSONL**  
- `C_OptimizedPortfolio.py` grava 1 linha JSON por registro
- Preserva arrays nativos de stocks em vez de listas comma-separated dentro de CSV
- Arquivos: `engines/C_OptimizedPortfolio.py`, `engines/D_Publish.py`

**3.5 Migrar `skipped_tickers.json` → JSONL**  
- `A1_Download.py` grava append-only (1 linha/skip)
- Elimina reescrita de ~1.5MB a cada ticker adicionado
- Arquivos: `engines/A1_Download.py`

---

### Fase 4 — Nice-to-have (pós-frontend)

**4.1** Adicionar `run_id` unificado aos performance CSVs para correlação com outputs.

**4.2** Mover `cloud_cost_comparison.json` e `resource_metrics.json` para backup.

**4.3** Adicionar `scoring_run_id` ao `portfolio_results_db.csv` para rastreabilidade scoring → selection.

---

### Frontend — Reset (2026-03-05)

Frontend antigo removido e backupado em `backups/refactor_20260303/frontend_old/`.  
`html/data/` (30 symlinks) preservado.

O novo frontend será construído do zero sobre os dados racionalizados, seguindo o princípio **render-only**: receber dados prontos e apenas exibi-los.

---

## Mapa de Dados Canônicos (estado atual)

```
data/
├── findb/
│   ├── StockDataDB.csv          ← A1: preços OHLCV (~41MB)
│   ├── FinancialsDB.csv         ← A1: dados financeiros (~890KB)
│   └── skipped_tickers.json     ← A1: tickers inválidos (~1.5MB)
├── results/
│   ├── scored_stocks.csv        ← A2: scoring histórico
│   ├── sector_pe.csv            ← A2: P/E setorial histórico
│   ├── correlation_matrix.csv   ← A2: matriz de correlação
│   ├── portfolio_results_db.csv ← A3: portfólios otimizados histórico
│   ├── ga_fitness_noise_db.csv  ← A3: convergência GA
│   ├── latest_run_summary.json  ← A3: snapshot última run
│   ├── portfolio_timeseries.csv ← A4: série temporal diária
│   ├── portfolio_diagnostics.json       ← D: snapshot última run (derivado de history CSV)
│   ├── portfolio_diagnostics_history.csv ← A4: métricas histórico
│   ├── performance_attribution.json      ← D: snapshot última run (derivado de history CSV)
│   ├── performance_attribution_history.csv ← A4: attribution histórico
│   ├── asset_attribution_history.csv     ← A4: attribution por ativo
│   ├── performance_windows_history.csv   ← A4: janelas de performance
│   ├── optimized_recommendation.json     ← C: recomendação de rebalanceamento
│   ├── optimized_portfolio_history.csv   ← C: histórico de decisões
│   ├── scored_targets.json      ← D: mapa ticker→targetPrice
│   ├── pipeline_latest.json     ← D: projeção modelo→real
│   ├── mis_model_latest.json    ← D: dashboard modelo (a consolidar)
│   ├── mis_real_latest.json     ← D: dashboard real (a consolidar)
│   ├── *_performance.csv (6)    ← Todos: logs operacionais
│   └── analysis_performance.csv ← A4: log operacional
├── transactions_parsed.csv      ← B1: transações brutas
├── fees_parsed.csv              ← B1: taxas detalhadas
├── processed_notes.json         ← B1: manifesto de notas
├── ledger.csv                   ← B2: transações consolidadas
├── ledger_positions.json        ← B2: posições atuais + totais
├── portfolio_history.json       ← B4: histórico diário (a migrar para CSV)
├── pipeline_progress.json       ← A_Portfolio.sh: status efêmero
├── download_progress.json       ← A1: status efêmero
├── scoring_progress.json        ← A2: status efêmero
└── portfolio_progress.json      ← A3: status efêmero

html/data/
└── (30 symlinks → data/)        ← D_Publish: janela para frontend
```

---

## Problemas Conhecidos (resolvidos)

| # | Problema | Resolução | Fase |
|---|---|---|---|
| 1 | A2 e A3 geravam `run_id` independentes | `PIPELINE_RUN_ID` via env var | 1.1 ✅ |
| 2 | `ledger_positions.json` sem totais | B2 calcula totais | 1.2 ✅ |
| 3 | C_Optimized usava broker name como ticker | Usa `symbol` (Yahoo) | 1.3 ✅ |
| 4 | `data/Results` (case) nos parâmetros | Corrigido para `data/results` | 1.4 ✅ |
| 5 | `portfolio_timeseries.csv` escrito 2x | Removida escrita duplicada em A4 | 2.1 ✅ |
| 6 | JSONs snapshot redundantes com CSVs history | D_Publish gera snapshots de history CSVs | 2.2 ✅ |
| 7 | `latest_run_summary.json` com ~24KB inline | Removidos timeseries, sparklines, ga_history | 2.3 ✅ |
| 8 | Sharpe forward vs realizado sem distinção | Pendente | 3.1 |
| 9 | `mis_model` e `mis_real` como JSONs separados | Pendente | 3.2 |
| 10 | `portfolio_history.json` 91KB aninhado | Pendente | 3.3 |
| 11 | CSVs com arrays em campos texto | Pendente | 3.4 |
| 12 | `skipped_tickers.json` 1.5MB reescrito inteiro | Pendente | 3.5 |

---

## Backups

Todos os arquivos removidos estão em `backups/refactor_20260303/`.  
Ver `backups/refactor_20260303/README.md` para inventário detalhado.

