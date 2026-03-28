# 3_model.html — Decision Clarity Plan

**Criado:** 2026-03-22  
**Status:** ✅ Steps 1–4 implementados (2026-03-22) · 🔲 Step 5 pendente  
**Arquivos modificados:** `html/sections/3_model.html`, `engines/C_OptimizedPortfolio.py`, `engines/D_Publish.py`

---

## Objetivo

A página `3_model.html` (Portfólio Modelo) exibia a decisão HOLD/REBALANCE de forma ambígua:
o retorno esperado da **carteira atual** nunca aparecia, o label "Excesso s/ Benchmark" era
enganoso, e o custo de rebalanceamento não indicava sua irrelevância relativa. O resultado
era que o investidor precisava fazer contas mentais para entender por que o sistema escolhia
HOLD.

Este documento registra o diagnóstico, as correções implementadas e a melhoria futura pendente.

---

## Diagnóstico

### Fórmula da decisão (C_OptimizedPortfolio.py → generate_recommendation)

```
excess_return = optimal_net_return − holdings_return

  holdings_return    = retorno esperado da CARTEIRA ATUAL (target_price / current_price − 1,
                       ponderado pelos pesos atuais).
                       Exposto em dashboard_latest.json como model.returns.hold_12m.

  optimal_net_return = retorno esperado do portfólio MODELO escolhido, já líquido do custo
                       único de transição (transition_cost_pct).
                       Exposto como model.returns.net_12m.

  excess_return      = quanto a mais (%) o modelo entrega vs. manter a carteira atual.
                       Positivo → modelo ganha → REBALANCE.
                       Negativo → carteira atual ganha → HOLD.
                       Exposto como model.returns.excess_net_12m.
```

> **Nota importante:** `excess_return` é excesso sobre a **carteira atual**, NÃO sobre qualquer
> índice de mercado externo (Ibovespa, CDI, etc.). Nomear esse campo "vs benchmark" na UI
> confunde as duas coisas.

### Exemplo com dados de 2026-03-21

| Campo | Valor | Fonte |
|---|---|---|
| Retorno esperado carteira atual (hold_12m) | **22,10%** | `model.returns.hold_12m` |
| Retorno bruto modelo (gross_12m) | **18,42%** | `model.returns.gross_12m` |
| Custo de transição (transition_cost_pct) | **0,0526%** | `comparison.optimal.transition_cost_pct` |
| Retorno líquido modelo (net_12m) | **18,37%** | `model.returns.net_12m` (= 18,42 − 0,0526) |
| Excesso vs. carteira atual (excess_net_12m) | **−3,73%** | `model.returns.excess_net_12m` (= 18,37 − 22,10) |
| Custo absoluto de rebalanceamento | **R$ 1,53** | Soma de `transactions[*].cost` |
| Decisão | **HOLD** | excess (−3,73%) < limiar (0,5%) |

A **carteira atual já tem retorno esperado maior (22,10%)** do que o modelo (18,42%), por isso
o sistema decide HOLD — e não por causa do custo de R$ 1,53 (que é apenas 0,05% do portfólio e
já está descontado no `net_12m`).

### Problemas identificados antes das correções

| # | Problema | Impacto |
|---|---|---|
| P1 | `hold_12m` (22,10%) não era exibido | Investidor não via o lado esquerdo da comparação |
| P2 | Label "Excesso s/ Benchmark" | Sugere comparação com índice de mercado — errado |
| P3 | Custo mostrado só em R$ (R$ 1,53), sem % | Parecia significativo; não ficava claro que já estava em `net_12m` |
| P4 | Nenhum resumo da conta completa na UI | Investidor precisava inferir: 22,10% − 18,37% = −3,73% |

---

## Implementação

### Step 1 — Renomear label "Excesso s/ Benchmark" ✅

**Arquivo:** `html/sections/3_model.html` · função `renderSummary`

**Antes:**
```js
{ label: 'Excesso s/ Benchmark', value: fmtPct(ret.excess_net_12m), cls: colorClass(...) }
```

**Depois:**
```js
// Positivo = modelo bate carteira atual → REBALANCE
// Negativo = carteira atual bate modelo → HOLD
{ label: 'Excesso vs. Carteira Atual', value: fmtPct(ret.excess_net_12m), cls: colorClass(...) }
```

---

### Step 2 — Adicionar `Carteira Atual (12M)` ao grid de métricas ✅

**Arquivo:** `html/sections/3_model.html` · função `renderSummary`

O campo `ret.hold_12m` existia no JSON mas nunca era renderizado. Foi adicionado como
primeiro item do grid, acompanhado de renomeação dos itens do modelo para deixar claro
a qual portfólio cada retorno se refere:

| Antes | Depois |
|---|---|
| *(não exibido)* | Carteira Atual (12M) |
| Retorno Esperado (12M) | Retorno Bruto Modelo (12M) |
| Retorno Líquido (12M) | Retorno Líquido Modelo (12M) |
| Excesso s/ Benchmark | Excesso vs. Carteira Atual |

O grid foi reorganizado em blocos semânticos:
1. Carteira Atual / Modelo Bruto / Modelo Líquido
2. Excesso vs. Carteira Atual / Custo de Rebalanceamento / Retorno Histórico
3. Volatilidade / Sharpe / HHI
4. Top 5 posições

---

### Step 3 — Exibir custo como `R$ X,XX (Y%)` ✅

**Arquivo:** `html/sections/3_model.html` · função `renderSummary`

**Antes:**
```js
{ label: 'Custo Total Rebalanceamento', value: fmtBRL(totalRebCost) }
// exibia apenas: "R$ 1,53"
```

**Depois:**
```js
const costPct = recommendation?.comparison?.optimal?.transition_cost_pct;
{ label: 'Custo de Rebalanceamento',
  value: `${fmtBRL(totalRebCost)}${costPct != null ? ` (${fmtPct(costPct)})` : ''}` }
// exibe: "R$ 1,53 (0,05%)"
```

O percentual torna imediatamente visível que o custo é marginal e que o real motivo do HOLD
é o retorno esperado menor do modelo — não o custo de transação.

---

### Step 4 — Linha de comparação explícita (breakdown row) ✅

**Arquivo:** `html/sections/3_model.html` · CSS + função `renderSummary`

Uma nova caixa (`.comparison-breakdown`) é inserida entre o `meta-row` e o grid de métricas,
mostrando a conta completa de uma vez:

```
Carteira atual: 22,10%  vs.  Modelo: 18,42% − 0,05% custo = 18,37% líq.  →  Excesso: −3,73%
```

Isso elimina completamente a necessidade de inferência por parte do investidor.

---

### Documentação de código adicionada ✅

**`engines/C_OptimizedPortfolio.py` · `generate_recommendation`**

Docstring expandida com:
- Fórmula completa de `excess_return` com referência aos campos JSON
- Direção positiva/negativa e mapeamento para HOLD/REBALANCE
- Nota explícita: o excesso é sobre a *carteira atual*, não sobre índice externo
- Bloco `# TODO` para o Step 5 (veja abaixo)

**`engines/D_Publish.py` · `_build_model_section`**

Comentários inline no bloco `returns` do JSON gerado explicando cada campo
(`hold_12m`, `gross_12m`, `net_12m`, `excess_net_12m`) e a nota
*"Do not label it 'vs benchmark' in the UI"*.

---

## Step 5 — Incorporar gap de score composto à decisão (🔲 pendente)

### Contexto

O engine `C_OptimizedPortfolio.py` seleciona o portfólio candidato ótimo usando um score
composto (40% retorno esperado + 40% Sharpe + 20% momentum). Mas a decisão final
HOLD/REBALANCE usa **apenas** o excesso de retorno bruto.

Exemplo concreto (2026-03-21):

| | Score composto | Retorno esperado (12M) |
|---|---|---|
| Carteira atual | **0,344** | 22,10% |
| Portfólio modelo | **0,655** | 18,42% |

O modelo perde em retorno esperado (−3,73 pp), mas é **significativamente melhor** em Sharpe
e momentum (score quase 2× maior). A decisão atual ignora essa diferença.

### Proposta de implementação

Adicionar uma cláusula de score-gap ao `generate_recommendation`:

```python
# Parâmetros sugeridos em optpar.txt:
#   SCORE_GAP_THRESHOLD  = 0.15   (diferença mínima de score para ativar a cláusula)
#   SOFT_RETURN_FLOOR    = -2.0   (excesso de retorno mínimo — pode ser negativo)

score_gap = optimal_score - holdings_score

if excess_return >= min_excess_threshold:
    decision = 'REBALANCE'
elif score_gap >= score_gap_threshold and excess_return >= soft_return_floor:
    # Modelo perde em retorno mas ganha muito em Sharpe/momentum
    decision = 'REBALANCE'
    reason = (f"Score gap ({score_gap:.2f}) above threshold despite lower return "
              f"({excess_return:.2f}%)")
else:
    decision = 'HOLD'
```

### Questões a resolver antes de implementar

1. **Calibração dos thresholds** — `SCORE_GAP_THRESHOLD` e `SOFT_RETURN_FLOOR` precisam ser
   calibrados com dados históricos para evitar rebalanceamentos prematuros.
2. **Interpretabilidade na UI** — a razão da decisão ficará mais complexa; a
   `comparison-breakdown` da `3_model.html` precisará de um segundo cenário de renderização.
3. **Score do portfólio atual** — `holdings_score` hoje usa Sharpe real passado;
   garantir que seja calculado com a mesma janela/metodologia do score do modelo.

### Referência no código

O bloco `# TODO` já está documentado em `C_OptimizedPortfolio.py · generate_recommendation`
como ponto de entrada para esta implementação.

---

## Checklist de verificação

| Item | Status |
|---|---|
| `hold_12m` exibido no grid | ✅ |
| Label "Excesso s/ Benchmark" removido | ✅ |
| Custo exibido em BRL + % | ✅ |
| Breakdown row renderizada | ✅ |
| Docstring `generate_recommendation` atualizada | ✅ |
| Comentários `D_Publish.py` `returns` block | ✅ |
| Step 5 (score-gap clause) | 🔲 |

