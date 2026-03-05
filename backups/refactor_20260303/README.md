# Backup — Refatoração Backend 2026-03-03

Arquivos removidos do projeto durante a refatoração da arquitetura de dados.

## Mudança principal
- Engines agora escrevem apenas em `data/` (fonte canônica)
- `html/data/` é cache derivado, populado exclusivamente por `D_Publish.py`
- CSVs históricos com `run_id` substituem JSONs sobre-escritos

## Arquivos deprecados (engines removidos)

| Arquivo | Era o quê |
|---|---|
| `D_MIS.py.deprecated` | Consolidava métricas modelo+real. Cálculos migrados para A4_Analysis.py e D_Publish.py |
| `D_MIS_README.md.deprecated` | Documentação do D_MIS |
| `B3_Generate_json.py.deprecated` | Gerava JSONs para frontend (FIFO duplicado). Substituído por D_Publish.py |
| `update_holdings_meta.py.deprecated` | Enriquecia latest_run_summary.json com forwardPE/Momentum. Absorvido por D_Publish.py |

## Artefatos de teste

| Arquivo | Origem |
|---|---|
| `.tmp_mis_test/` | Diretório temporário do self-test de D_MIS.py |

## Dados antigos / obsoletos

| Arquivo | Origem |
|---|---|
| `old_BenchmarksDB.csv` | Formato antigo de benchmarks (pré-StockDataDB) |
| `old_KPIResultsDB.csv` | Formato antigo de resultados (pré-portfolio_results_db) |
| `old_yfinance_skip.json` | Lista de tickers inválidos formato antigo (~3.4MB) |
| `portfolio_results_db_backup_*.csv` | Backups manuais do portfolio_results_db (Feb 2026) |
| `performance_summary.json` | JSON estático de Nov 2025, não produzido por nenhum engine atual |

## Arquivos .bak

| Arquivo | Origem |
|---|---|
| `latest_run_summary.json.bak` | Backup automático do update_holdings_meta.py |
| `tickers.txt.bak` | Backup manual de edição de tickers |
| `transactions_parsed.csv.bak` | Backup manual do ledger |
| `ledger.csv.bak` | Backup manual do ledger |
| `scored_stocks.csv.bak` | Backup manual do scoring |

## Limpeza 2 — 2026-03-04

| Arquivo | Era o quê |
|---|---|
| `data_broken_symlink` | `data/data` → `html/data` — symlink circular quebrado de Nov 2025 |
| `ledger_consolidated.json` | Formato antigo de posições (Nov 2025). Substituído por `ledger_positions.json` |
| `findb_portfolio_timeseries.csv` | Duplicata de `data/results/portfolio_timeseries.csv` (A4 escrevia nos dois lugares via `OUTPUT_CSV`) |
| `pre_migration_20260213_121218/` | Backup antigo de migração (FinancialsDB, StockDataDB, skip_files) — consolidado aqui |

## Limpeza 3 — 2026-03-05: Frontend reset

| Pasta | Conteúdo |
|---|---|
| `frontend_old/` | Frontend completo removido para rebuild do zero |
| `frontend_old/*.html` | 6 páginas (index, help, latest_run_summary, meu_portfolio, modelo, nav, portfolio) |
| `frontend_old/css/` | styles.css (37KB) |
| `frontend_old/js/` | 8 arquivos JS (auth, firebase-config, latest_run_summary, load_nav, meu_portfolio, modelo, portfolio, portfolio_real) |
| `frontend_old/img/` | 4 imagens PNG de preview |

`html/data/` (30 symlinks para dados canônicos) foi preservado.

