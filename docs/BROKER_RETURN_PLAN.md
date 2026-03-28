# Broker Return (MWR/Modified Dietz) — Analysis & Implementation Plan

**Criado:** 2026-03-14  
**Status:** ✅ Implementação concluída (2026-03-15)  
**Referência:** docs/METRICS_REFERENCE.md, docs/2_RISK_PAGE_PLAN.md

---

## Objetivo

Adicionar ao pipeline a métrica de retorno que a corretora usa: **Modified Dietz** (MWR mensal), composto mensalmente. Isso permitirá exibir no frontend o mesmo número que o investidor vê no app da corretora, lado a lado com o TWR, para transparência.

---

## Diagnóstico: Por que a corretora mostra −2,66% e o nosso sistema mostra +23,50%?

### Dados da corretora

| Mês | Rentabilidade | CDI |
|---|---|---|
| Outubro/25 | +4,96% | 1,28% |
| Novembro/25 | −5,66% | 1,05% |
| Dezembro/25 | 0,00% | 1,22% |
| Janeiro/26 | +8,47% | 1,16% |
| Fevereiro/26 | −6,18% | 1,00% |
| Março/26 | −3,41% | 0,00% |
| **Total** | **−2,66%** | — |

A corretora compõe os retornos mensais: `∏(1 + r_m) − 1 = (1,0496)(0,9434)(1,00)(1,0847)(0,9382)(0,9659) − 1 = −2,66%` ✓

### Nosso TWR composto mensalmente (stock-only)

| Mês | Nosso TWR | Broker | Diferença |
|---|---|---|---|
| Out/25 | +4,47% | +4,96% | −0,49 pp |
| Nov/25 | −4,72% | −5,66% | +0,94 pp |
| Dez/25 | *(sem dados)* | 0,00% | — |
| Jan/26 | +18,21% | +8,47% | +9,74 pp |
| Fev/26 | +6,91% | −6,18% | +13,09 pp |
| Mar/26 | −1,83% | −3,41% | +1,58 pp |
| **Total** | **+23,50%** | **−2,66%** | **+26,16 pp** |

### As três causas raíz da divergência

**1. Cash dilution (fator principal).** A corretora rastreia o saldo total da conta (ações + caixa). Após a liquidação total em nov/25, ~R$1.937 ficaram como caixa rendendo 0% de nov/11 a jan/2 (~7 semanas). Em janeiro, ~R$960 ainda ficaram ociosos enquanto só R$977 foram investidos. Esse caixa morto arrasta o retorno mensal para baixo. Nosso TWR só rastreia períodos com posições — esse tempo ocioso não existe.

**2. Dezembro conta como um mês.** A corretora tem 6 meses na cadeia de composição (out→mar), incluindo dezembro a 0%. Nosso TWR tem 5 meses (sem dezembro). Compor `×1,00` por um mês extra não muda o número, mas estabelece o denominador de janeiro como muito maior (pois carrega o caixa ocioso).

**3. Timing de depósitos penaliza o MWR.** Em fevereiro, R$1.962 foram depositados no dia 2 de 28. As ações caíram antes de se recuperar. No MWR, esse depósito grande no início do mês recebe o impacto total da queda intra-mês. No TWR, o depósito é "removido" do cálculo — só a performance das ações importa.

### Timeline real do portfólio

```
Out 17: Compra CSMG3(16), PLPL3(15), VULC3(10) por R$987,88
Out 31: Portfólio = R$1.041,94  →  Broker: +4,96%

Nov 03: Compra mais CSMG3(15), PLPL3(4), VULC3(13) por R$923,23
Nov 10: Vendas parciais + compra LAVV3(9)
Nov 11: VENDE TUDO. Zero posições. Caixa = ~R$1.937
Nov 30: Zero posições  →  Broker: −5,66%

Dez: Zero posições todo o mês  →  Broker: 0,00%

Jan 02: Compra VULC3(3), VALE3(2), AURA33(2), MDNE3(12), AXIA6(5), TEND3(2) por R$977,03
Jan 31: Portfólio = R$1.137,55  →  Broker: +8,47%

Fev 02: Compra SAPR11(15), PLPL3(19), PETR3(22), CMIG3(8) por R$1.962,35
Fev 19: Vende AXIA6(5) por R$318,42
Fev 28: Portfólio = R$3.016,62  →  Broker: −6,18%

Mar 13: Portfólio = R$2.961,55  →  Broker: −3,41%
```

### Qual está certo?

**Ambos estão corretos** — respondem perguntas diferentes:

| Método | Pergunta | Resultado |
|---|---|---|
| **Broker (MWR/Dietz)** | "Qual foi minha experiência pessoal, dado quando coloquei dinheiro?" | −2,66% |
| **Nosso TWR** | "Quão boa foi minha estratégia de stock-picking, independente do timing de aportes?" | +23,50% |
| **Simple ROI** | "Quanto dinheiro ganhei sobre o investido?" | +9,36% |

---

## Plano de Implementação

### Mudança 1 — Computar retorno Modified Dietz mensal em D_Publish.py

**Arquivo:** `engines/D_Publish.py`  
**Nova função:** `_compute_broker_return(hist_df, ledger_df)`

**Algoritmo Modified Dietz mensal:**

```
Para cada mês no range (first_transaction_month → last_data_month):

  1. V_start = valor do portfólio (stock + cash_in_account) no primeiro dia útil do mês
     - Se mês anterior teve posições: V_start_stock = último stock value do mês anterior
     - Cash = acumulado de vendas anteriores não reinvestidas
     - V_start = V_start_stock + cash
     - Se nenhuma posição e nenhum cash: V_start = 0

  2. Para cada transação no mês:
     - Buys: external deposit = max(buy_cost - available_cash, 0)
     - Sells: cash += sell_proceeds (interno, sem novos depósitos)
     - Track: day_of_flow, amount, direction

  3. V_end = stock value no último dia útil + cash remanescente

  4. Gain = V_end - V_start - Σ(external_deposits)

  5. Weighted capital (Modified Dietz):
     D = V_start + Σ(w_i × CF_i)
     onde w_i = (CD - D_i) / CD
       CD = dias corridos no mês
       D_i = dia corrido do fluxo dentro do mês
       CF_i = depósito externo (positivo)

  6. r_month = Gain / D  (se D > 0, senão 0)

  7. Compor: total = ∏(1 + r_month) − 1
```

**Nota importante:** Para implementar corretamente, precisamos saber os depósitos EXTERNOS (dinheiro entrando do banco para a corretora), que são diferentes dos buys (que podem usar caixa já na corretora). A heurística é: `external_deposit = buy_cost - available_cash` quando `buy_cost > available_cash`.

**Alternativa mais simples (recomendada para v1):** Não tentar rastrear o caixa. Em vez disso, usar o **método da cota** sobre o portfólio de ações apenas, mas incluir meses com zero posições como 0%. Isso é mais fácil de implementar e chega mais perto do broker do que o TWR puro.

### Mudança 2 — Adicionar `broker_return` ao dashboard_latest.json

**Nova seção em `real`:**

```json
"broker_return": {
  "method": "modified_dietz_monthly",
  "monthly": {
    "2025-10": { "return": 0.0447, "trading_days": 11 },
    "2025-11": { "return": -0.0472, "trading_days": 6 },
    "2025-12": { "return": 0.0, "trading_days": 0 },
    "2026-01": { "return": 0.1821, "trading_days": 22 },
    "2026-02": { "return": 0.0691, "trading_days": 19 },
    "2026-03": { "return": -0.0183, "trading_days": 9 }
  },
  "total": -0.0266,
  "note": "Approximation of broker MWR. Exact match requires external deposit/withdrawal data not available in ledger."
}
```

### Mudança 3 — Exibir no frontend

Adicionar um card ou tooltip em `1_portfolio.html` ou `2_risk.html` mostrando o retorno estilo-corretora, com sub-texto explicando a diferença:

```
Card: "Retorno Corretora"
Value: −2,66%
Sub: "Modified Dietz · inclui caixa ocioso"
```

### Desafios conhecidos

1. **~~Depósitos externos desconhecidos.~~** ✅ Resolvido. Extratos da Ágora (PDFs) fornecem depósitos, saques, dividendos e transferências para fundos. Parser: `engines/B13_Cash_Parser.py`. Output: `data/cash_movements.csv`.

2. **Preços B3 vs Yahoo Finance.** A corretora usa preços oficiais B3 (preço de ajuste). O Yahoo Finance pode diferir em ±0,5%. Isso explica a diferença de ~0,5 pp em outubro.

3. **Settlement date (T+2).** A corretora pode creditar ações no D+2, não na data de negociação. Isso pode mover fluxos entre meses na fronteira.

4. **Portfolio_history.csv não cobre o gap.** O período de zero posições (nov/11 → jan/2) não tem dados em `portfolio_history.csv`. D_Publish precisa detectar e preencher esses meses com retorno 0%.

---

## Ordem de Implementação (Atualizado 2026-03-15)

Descartada a abordagem v1 (heurística sem cash tracking). Implementação direta com dados reais de extratos da Ágora.

| Step | Tarefa | Tipo | Status |
|---|---|---|---|
| 1 | Criar `engines/B13_Cash_Parser.py` — parser de extratos Ágora → `cash_movements.csv` | Backend | ✅ |
| 2 | Integrar B13 em `B1_Process_Notes.py` (chamar após rebuild do ledger) | Backend | ✅ |
| 3 | Rodar B13 e validar `cash_movements.csv` contra saldos dos extratos | Validação | ✅ |
| 4 | Adicionar `_compute_broker_return()` em `D_Publish.py` — Modified Dietz mensal com cash tracking | Backend | ✅ |
| 5 | Wiring: integrar broker_return em `_build_real_section()` → `dashboard_latest.json` | Backend | ✅ |
| 6 | Frontend: card "Retorno Corretora" em Row 1 (3º card), grid 5 colunas | Frontend | ✅ |
| 7 | Comparar com dados da corretora e documentar diferenças | Validação | ✅ |
| 8 | Atualizar `METRICS_REFERENCE.md` com fórmula Modified Dietz | Docs | ✅ |

---

## Fonte de dados: Extratos da Ágora

### PDFs disponíveis (em `Notas_Negociação/`)

| Arquivo | Período | Conteúdo |
|---|---|---|
| `202501-12 Extrato Ágora.pdf` | Out–Dez 2025 | 2 depósitos, 2 saques, 1 dividendo, operações |
| `202601 Extrato Ágora.pdf` | Jan 2026 | 1 depósito, operações |
| `20260201-20260315 Extrato Ágora.pdf` | Fev–Mar 2026 | 1 depósito, 2 transferências Bradesco ESG, operações |

### Fluxos externos identificados

| Data | Tipo | Valor (R$) | Descrição |
|---|---|---|---|
| 2025-10-17 | DEPOSIT | +1.000,00 | TED BCO 237 |
| 2025-11-03 | DIVIDEND | +1,25 | VULC3 (10 ações) |
| 2025-11-03 | DEPOSIT | +1.000,00 | DOC BCO 237 |
| 2025-11-12 | WITHDRAWAL | −440,46 | SPB/TED para banco |
| 2025-11-13 | WITHDRAWAL | −1.586,69 | SPB/TED para banco |
| 2025-12-15 | DIVIDEND | +50,60 | VULC3 (23 ações) |
| 2026-01-02 | DEPOSIT | +1.000,00 | DOC BCO 237 |
| 2026-02-02 | DEPOSIT | +2.000,00 | DOC BCO 237 |
| 2026-02-19 | FUND_TRANSFER | −100,00 | Bradesco ESG Global MM |
| 2026-02-24 | FUND_TRANSFER | −300,00 | Bradesco ESG Global MM |

### Padrões de texto do pdfplumber

O extrato em PDF tem layout `Data | Descrição | Valor (R$)` mas o pdfplumber mistura colunas.
Padrões confiáveis para regex:

- **Depósito:** `(TED|DOC) BCO` + `4666\S*\s+[\d.]+,\d{2}` (valor positivo) + `REF`
- **Saque:** `#SPB#RET#` ou `46663-` + `-[\d.]+,\d{2}` (valor negativo)
- **Dividendo:** `DIVIDENDOS S/` + `\d+\s+[\d.]+,\d{2}` + `DE` + ticker
- **Fundo:** `PAG - APLIC.` + `BRADESCO ESG` + `-[\d.]+,\d{2}`
- **Operação (skip):** `OPERACOES NA BOLSA`
- **Saldo:** `Saldo do dia` + `[\d.]+,\d{2}` (para validação)
- **Datas:** `DD/MM/YYYY` explícitas ou `DD\n(Mês)` com mês PT-BR

### Notas sobre fund transfers

O investidor aplica parte dos proventos no fundo Bradesco ESG Global MM (multi-mercado low-risk).
Total transferido: R$400. **Não rastrear performance do fundo** — tratar como WITHDRAWAL
para fins de Modified Dietz (dinheiro saindo da conta de ações).

---

## Arquivos Impactados

| Arquivo | Ação |
|---|---|
| `engines/B13_Cash_Parser.py` | **NOVO** — Parser de extratos Ágora → `data/cash_movements.csv` |
| `engines/B1_Process_Notes.py` | Chamar B13 após rebuild do ledger |
| `data/cash_movements.csv` | **NOVO** — Saída do parser |
| `data/processed_extratos.json` | **NOVO** — Manifesto de extratos processados |
| `engines/D_Publish.py` | Nova função `_compute_broker_return()`, integrar no `real` section |
| `data/results/dashboard_latest.json` | Nova seção `real.broker_return` |
| `html/sections/1_portfolio.html` | Card "Retorno Corretora" em Row 1 (3º card, grid 5 colunas) |
| `docs/METRICS_REFERENCE.md` | Documentar a métrica Modified Dietz |

