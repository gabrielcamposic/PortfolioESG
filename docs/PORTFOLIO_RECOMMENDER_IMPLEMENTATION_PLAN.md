# Plano de Implementacao: Recomendador de Portfolio Estavel

Data inicial: 2026-06-05

Documento vivo para guiar a evolucao incremental do modelo de recomendacao de portfolio. A proposta parte do diagnostico em `docs/PORTFOLIO_RECOMMENDER_BEHAVIOR_ANALYSIS.md` e deve ser atualizada a cada fase implementada.

## Objetivo

Evoluir o modelo para continuar rodando diariamente, mas recomendar rebalanceamentos apenas quando houver evidencia robusta, persistente e operacionalmente justificavel. O foco e preservar capacidade de monitoramento rapido sem transformar ruido diario, targets anomalos ou stress de mercado em ordens frequentes de compra/venda.

## Principios de Implementacao

1. Nao duplicar pipeline nem frontend.
2. Manter a decisao oficial atual funcionando enquanto novas metricas entram em modo diagnostico ou shadow.
3. Alternar ciclos curtos: scripts primeiro, dashboard depois, validacao, proximo ciclo.
4. Persistir novos campos nos mesmos artefatos JSON/CSV sempre que possivel.
5. Tornar cada melhoria visivel no dashboard antes de promover a logica para decisao oficial.
6. Versionar explicitamente mudancas de comportamento com campos como `model_version`, `scoring_version`, `decision_engine_version` ou equivalentes.
7. Preferir funcoes pequenas e testaveis a grandes reescritas do pipeline.

## Estrategia De Shadow Sem Duplicacao

O pipeline atual continua gerando a decisao oficial. As novas logicas devem inicialmente salvar campos paralelos:

```json
{
  "decision": "REBALANCE",
  "comparison": {
    "holdings": {
      "expected_return_pct": 344.3
    },
    "optimal": {
      "expected_return_pct": 403.93
    }
  },
  "diagnostics": {
    "target_quality": {},
    "return_contributors": [],
    "market_regime": {}
  },
  "shadow": {
    "expected_return_adjusted_pct": 48.2,
    "decision": "WATCH",
    "veto_reasons": []
  }
}
```

No dashboard, a abordagem equivalente e adicionar secoes, cards ou tabelas nas telas atuais. Nao criar uma segunda aplicacao.

## Mapa De Arquivos Provaveis

Scripts principais:

- `engines/A2_Scoring.py`: qualidade de targets, scores por ativo, metricas de input.
- `engines/A3_Portfolio.py`: retorno esperado ajustado, otimizacao com sinal ajustado.
- `engines/A4_Analysis.py`: diagnosticos de risco, regime, turnover e historico.
- `engines/C_OptimizedPortfolio.py`: comparacao carteira atual vs ideal, gate de rebalanceamento, decisao shadow/oficial.
- `engines/D_Publish.py`: publicacao dos novos campos para dashboard.

Parametros:

- `parameters/scorpar.txt`: parametros de target quality e shrinkage.
- `parameters/portpar.txt`: parametros de retorno ajustado e otimizacao.
- `parameters/optpar.txt`: parametros do gate de rebalanceamento.
- `parameters/risk_profile.txt`: parametros de regime e conservadorismo.

Outputs:

- `data/results/scored_stocks.csv`
- `data/results/latest_run_summary.json`
- `data/results/optimized_recommendation.json`
- `data/results/dashboard_latest.json`
- `data/results/portfolio_diagnostics.json`
- `data/results/optimized_portfolio_history.jsonl`

Frontend:

- `html/sections/model.html`: decisao, comparacao, veto reasons, shadow decision.
- `html/sections/scoring.html`: qualidade de targets e top contributors.
- `html/sections/risk.html`: regime de mercado, stress e drawdown.
- `html/sections/portfolio.html`: impacto na carteira real e evolucao base 100.

## Status Geral

| Fase | Nome | Status | Resultado esperado |
|---|---|---|---|
| 0 | Baseline e diagnostico atual | Implementado em 2026-06-05 | Explicar de onde vem o retorno esperado atual |
| 1 | Quality gate de targets | Implementado em 2026-06-05 | Identificar targets confiaveis, suspeitos e rejeitados |
| 2 | Retorno esperado com shrinkage | Implementado em 2026-06-05 | Criar retorno ajustado sem substituir decisao oficial |
| 3 | Regime de mercado com stress pos-pico | Implementado em 2026-06-05 | Detectar drawdown recente e elevar cautela |
| 4 | Gate de rebalanceamento shadow | Implementado em 2026-06-05 | Comparar decisao oficial vs decisao alternativa |
| 5 | Estados HOLD/WATCH/PARTIAL/REBALANCE | Implementado em 2026-06-06 | Reduzir binariedade da recomendacao |
| 6 | Otimizacao com penalidade de turnover | Implementado em 2026-06-06 | Preferir estabilidade quando ganho marginal e baixo |
| 7 | Backtest e calibracao | Implementado em 2026-06-06 | Calibrar thresholds com historico |
| 8 | Promocao para decisao oficial | Implementado em 2026-06-06 | Substituir decisao oficial com seguranca |

## Fase 0: Baseline E Diagnostico Atual

### Objetivo

Tornar transparente o comportamento atual sem alterar nenhuma decisao do modelo.

### Scripts

Implementar diagnosticos adicionais nos outputs existentes:

- Top contribuintes do retorno esperado por portfolio.
- Concentracao do retorno esperado em poucos ativos.
- Fonte do retorno esperado por ativo: target Yahoo, fallback PE setorial, historico, sem dado.
- Retorno esperado bruto da carteira atual, ideal e otima.
- Retorno historico equivalente, quando disponivel, lado a lado com target-based return.
- Turnover sugerido, numero de transacoes e valor negociado como percentual da carteira.

Campos sugeridos:

```json
{
  "diagnostics": {
    "return_concentration": {
      "top1_contribution_pct": 0,
      "top2_contribution_pct": 0,
      "top5_contribution_pct": 0
    },
    "return_contributors": [
      {
        "stock": "KLBN4.SA",
        "weight": 0.3915,
        "current_price": 3.35,
        "target_price": 24.75,
        "raw_upside_pct": 638.88,
        "return_contribution_pct": 250.11,
        "target_source": "YahooFinance"
      }
    ]
  }
}
```

### Dashboard

Adicionar em `model.html` ou `scoring.html`:

- Card "Origem do Retorno Esperado".
- Tabela "Top contribuintes do upside".
- Alerta visual quando top 2 ativos explicarem mais de 50% do retorno esperado.
- Comparacao "retorno por target" vs "retorno historico/pipeline".

### Criterios De Aceite

- O usuario consegue explicar a recomendacao sem abrir logs.
- O dashboard evidencia casos como KLBN4 e AMBP3.
- A decisao oficial continua identica a anterior.

## Fase 1: Quality Gate De Targets

### Objetivo

Pontuar a confiabilidade dos targets antes que eles entrem no retorno esperado.

### Scripts

Criar uma funcao de avaliacao por ativo, preferencialmente em `A2_Scoring.py` ou helper compartilhado:

```text
target_quality_score: 0.0 a 1.0
target_quality_bucket: high | medium | low | reject
target_quality_flags: lista de motivos
```

Flags iniciais:

- `missing_target`
- `sector_pe_fallback`
- `stale_target`
- `extreme_upside`
- `negative_or_zero_forward_pe`
- `very_low_price`
- `low_liquidity`
- `target_class_mismatch_suspected`
- `unit_or_share_class_mismatch_suspected`
- `corporate_action_check_required`
- `distressed_price_action`

Heuristicas candidatas:

- Marcar `extreme_upside` acima de 150% ou acima do percentil 95 do universo.
- Marcar `very_low_price` abaixo de um piso configuravel.
- Marcar `sector_pe_fallback` sempre que o target vier de PE setorial.
- Marcar suspeita de classe/unit quando target e muito proximo de outro ticker relacionado, mas preco e escala sao muito diferentes.
- Reduzir confianca quando o ativo caiu muito e o target permaneceu estavel.

Parametros sugeridos:

```text
TARGET_EXTREME_UPSIDE_PCT = 150
TARGET_REJECT_UPSIDE_PCT = 300
TARGET_LOW_PRICE_PCT = 1.00
TARGET_STALE_DAYS = 45
TARGET_MAX_FALLBACK_QUALITY = 0.35
```

### Dashboard

Adicionar:

- Tabela "Qualidade dos Targets".
- Filtros por bucket: high, medium, low, reject.
- Lista de flags por ativo.
- Indicador de quanto do retorno esperado vem de targets low/reject.

### Criterios De Aceite

- Ativos como AMBP3 via fallback extremo aparecem como low/reject.
- Casos suspeitos como KLBN4 aparecem com flag investigavel.
- Nenhuma decisao oficial muda ainda.

## Fase 2: Retorno Esperado Com Shrinkage

### Objetivo

Criar um retorno esperado ajustado pela confianca do target, sem substituir o retorno oficial imediatamente.

### Scripts

Calcular:

```text
raw_expected_return
adjusted_expected_return
target_quality_score
shrinkage_factor
```

Forma conceitual:

```text
adjusted_return =
    quality * capped_raw_target_return
  + (1 - quality) * base_return
  - uncertainty_penalty
```

`base_return` pode comecar simples:

- mediana do setor;
- retorno esperado de mercado;
- retorno historico suavizado;
- zero real/conservador para targets rejeitados.

Regras iniciais:

- Target high: usa boa parte do upside, ainda com cap.
- Target medium: mistura target e base setorial.
- Target low: forte shrinkage para base.
- Target reject: nao usar target; usar base conservadora ou excluir do retorno forward.

Implementacao atual:

- `shared_tools/target_quality.py` adiciona `calculate_adjusted_return`.
- `A2_Scoring.py` salva campos shadow por ativo: `RawExpectedReturnPct`, `CappedRawExpectedReturnPct`, `AdjustedExpectedReturnPct`, `ShrinkageFactor`, `AdjustedReturnBasePct`, `AdjustedReturnDeltaPct` e `UncertaintyPenaltyPct`.
- `C_OptimizedPortfolio.py` adiciona `diagnostics.adjusted_returns`, contributors com contribuicao bruta/ajustada/reduzida e bloco `shadow` com ganho ajustado.
- `D_Publish.py` publica `hold_adjusted_12m`, `gross_adjusted_12m`, `net_adjusted_12m` e `excess_adjusted_net_12m`.
- `html/sections/model.html` mostra retorno bruto vs ajustado, reducao total e reducao por ativo.

Parametros atuais:

```text
RETURN_ADJUSTMENT_CAP_PCT = 150
RETURN_ADJUSTMENT_FLOOR_PCT = -80
RETURN_ADJUSTMENT_BASE_PCT = 0
RETURN_ADJUSTMENT_REJECT_BASE_PCT = 0
RETURN_ADJUSTMENT_UNCERTAINTY_PENALTY_PCT = 0
```

### Dashboard

Mostrar:

- Retorno bruto vs retorno ajustado.
- Diferenca por ativo.
- Quanto o portfolio perde de retorno ao aplicar qualidade.
- Top ativos com maior reducao por shrinkage.

### Criterios De Aceite

- O retorno esperado extremo cai para faixa plausivel.
- A recomendacao oficial ainda pode continuar usando o retorno antigo.
- O usuario consegue comparar raw vs adjusted no dashboard.

## Fase 3: Regime De Mercado Com Stress Pos-Pico

### Objetivo

Capturar que o mercado pode estar em stress mesmo quando o retorno acumulado desde a base inicial ainda e positivo.

### Scripts

Adicionar metricas de regime:

- Drawdown do Ibovespa desde pico em 3M e 6M.
- Volatilidade anualizada recente do Ibovespa.
- Percentual do universo com retorno negativo em 3M e 6M.
- Percentual do universo em drawdown maior que 20%.
- Dispersao cross-sectional dos retornos.
- Queda setorial mediana.

Estados sugeridos:

```text
normal
volatile_watch
stress
dislocation_opportunity
```

Regras iniciais:

- `stress` se Ibovespa cair mais de 10% desde pico recente ou se dispersao/drawdown amplo for alto.
- `volatile_watch` se volatilidade e dispersao estiverem elevadas sem queda forte do indice.
- `dislocation_opportunity` apenas se preco cair, mas qualidade de target/fundamento permanecer alta.

Implementacao atual:

- `shared_tools/market_regime.py` calcula regime com `^BVSP`, janelas de 63/126 pregoes, breadth negativa, breadth de drawdown e dispersao robusta `p90-p10`.
- `C_OptimizedPortfolio.py` grava `diagnostics.market_regime` e campos resumidos no `shadow`.
- `D_Publish.py` publica o regime em `dashboard_latest.json`.
- `html/sections/risk.html` exibe card "Regime de Mercado" com drawdown 3M/6M, volatilidade, breadth, dispersao e pior setor.

Parametros atuais:

```text
REGIME_BENCHMARK_TICKER = ^BVSP
REGIME_LOOKBACK_3M_DAYS = 63
REGIME_LOOKBACK_6M_DAYS = 126
REGIME_DRAWDOWN_STRESS_PCT = 10
REGIME_NEGATIVE_BREADTH_PCT = 60
REGIME_DRAWDOWN_BREADTH_PCT = 45
REGIME_ASSET_DRAWDOWN_THRESHOLD_PCT = 20
REGIME_VOLATILITY_WATCH_PCT = 25
REGIME_DISPERSION_WATCH_PCT = 35
```

### Dashboard

Adicionar em `risk.html` ou `model.html`:

- Card "Regime de Mercado".
- Explicacao quantitativa: drawdown desde pico, vol, dispersao, percentual de ativos negativos.
- Impacto do regime: shrinkage maior, hurdle maior, turnover menor.

### Criterios De Aceite

- O caso do Ibovespa saindo de pico perto de 138 e indo para 119 no grafico e identificado como stress/alerta.
- O regime passa a ser visivel para o usuario.

## Fase 4: Gate De Rebalanceamento Shadow

### Objetivo

Separar "portfolio matematicamente melhor" de "vale operar agora".

### Scripts

Criar `shadow_decision` em `C_OptimizedPortfolio.py`:

```text
official_decision: decisao atual
shadow_decision: HOLD | WATCH | PARTIAL_REBALANCE | REBALANCE
shadow_veto_reasons: lista
shadow_hurdle_pct: hurdle dinamico
shadow_expected_gain_pct: ganho esperado ajustado
```

Regras candidatas:

```text
trade_allowed =
    adjusted_net_gain > dynamic_hurdle
and signal_persistence_days >= N
and turnover <= turnover_budget
and portfolio_target_quality >= confidence_floor
and suspicious_target_contribution <= max_suspicious_contribution
```

Hurdle dinamico:

```text
dynamic_hurdle =
    transaction_cost
  + slippage_estimate
  + tax_drag_estimate
  + model_uncertainty_penalty
  + regime_stress_penalty
```

Implementacao atual:

- `C_OptimizedPortfolio.py` calcula `shadow_decision` sem alterar `decision` oficial.
- O gate usa ganho ajustado liquido, custo de transicao, estimativa de slippage, arrasto tributario, penalidade de incerteza, penalidade de regime, persistencia do sinal, budget de turnover e qualidade dos targets.
- Em regime `stress`, o hurdle recebe addon e o budget efetivo de turnover e reduzido pelo multiplicador do regime.
- `optimized_recommendation.json` salva `shadow_decision`, `shadow_trade_allowed`, `shadow_hurdle_pct`, `shadow_expected_gain_pct`, componentes do hurdle, vetos e metricas de qualidade/turnover.
- `optimized_portfolio_history.jsonl` registra os principais campos shadow para medir persistencia e auditar a evolucao da decisao.
- `D_Publish.py` publica o bloco `shadow` em `dashboard_latest.json`.
- `html/sections/model.html` mostra o painel "Gate Shadow" com decisao oficial vs shadow, ganho ajustado vs hurdle, persistencia, turnover, qualidade e motivos de veto.

Parametros atuais:

```text
SHADOW_BASE_HURDLE_PCT = 0.5
SHADOW_SLIPPAGE_ESTIMATE_PCT = 0.15
SHADOW_TAX_DRAG_ESTIMATE_PCT = 0
SHADOW_MODEL_UNCERTAINTY_PENALTY_PCT = 0.5
SHADOW_MIN_PERSISTENCE_DAYS = 2
SHADOW_TURNOVER_BUDGET_PCT = 35
SHADOW_CONFIDENCE_FLOOR = 0.60
SHADOW_MAX_SUSPICIOUS_RETURN_CONTRIBUTION_PCT = 35
SHADOW_PARTIAL_REBALANCE_MIN_GAIN_PCT = 1.0
```

### Dashboard

Mostrar:

- Decisao oficial vs decisao shadow.
- Motivos de veto.
- Ganho ajustado vs hurdle.
- Persistencia do sinal.
- Turnover requerido.

### Criterios De Aceite

- O usuario ve quando o modelo atual recomenda `REBALANCE`, mas o gate shadow recomendaria `WATCH`.
- O output oficial antigo segue intacto.

## Fase 5: Estados HOLD / WATCH / PARTIAL / REBALANCE

### Objetivo

Reduzir a decisao binaria e permitir que o modelo avise sem necessariamente operar.

### Scripts

Estados:

- `HOLD`: sem mudanca.
- `WATCH`: oportunidade/risco detectado, mas sem trade.
- `PARTIAL_REBALANCE`: ajuste limitado por bandas, risco ou concentracao.
- `REBALANCE`: mudanca relevante, persistente e confiavel.

Adicionar:

- Bandas de tolerancia por ativo.
- Bandas por setor.
- Orcamento de turnover mensal/semanal.
- Acao recomendada em reais e percentual.

Implementacao atual:

- `C_OptimizedPortfolio.py` cria `shadow.execution_plan` com estado executavel, acao de hoje, intensidade, orcamento, valor executavel e valor adiado.
- O plano usa o `shadow_decision` da fase 4 como entrada, sem alterar `decision` oficial.
- Transacoes passam a ser classificadas como `EXECUTE`, `MONITOR`, `HOLD`, `DEFER_BUDGET`, `DEFER_MAX_ACTIONS`, `IGNORE_BAND` ou `IGNORE_SMALL`.
- O plano compara peso atual, peso-alvo teorico e peso executavel para cada ativo relevante.
- O plano calcula drift setorial atual vs alvo e marca setores fora da banda configurada.
- O historico JSONL registra estado executavel, intensidade, valor executavel e quantidade de acoes executaveis.
- `html/sections/model.html` mostra "Plano Executavel" dentro do card do Gate Shadow.

Parametros atuais:

```text
EXECUTION_ASSET_TOLERANCE_BAND_PCT = 2.0
EXECUTION_SECTOR_TOLERANCE_BAND_PCT = 5.0
EXECUTION_WEEKLY_TURNOVER_BUDGET_PCT = 12
EXECUTION_MONTHLY_TURNOVER_BUDGET_PCT = 35
EXECUTION_MIN_TRADE_VALUE_BRL = 25
EXECUTION_MAX_ACTIONS = 6
```

### Dashboard

Mostrar:

- Estado da decisao.
- Intensidade da acao.
- "Por que nao rebalancear hoje".
- Diferenca entre portfolio atual, alvo teorico e alvo executavel.

### Criterios De Aceite

- Rodar diariamente nao implica recomendacao diaria de compra/venda.
- O dashboard comunica claramente quando o modelo esta apenas monitorando.

## Fase 6: Otimizacao Com Penalidade De Turnover

### Objetivo

Fazer o otimizador preferir estabilidade quando o ganho marginal e pequeno.

### Scripts

Alterar objetivo de otimizacao conceitual:

```text
portfolio_score =
    adjusted_expected_alpha
  - lambda_risk * risk
  - lambda_turnover * turnover
  - lambda_uncertainty * uncertainty
  - lambda_concentration * concentration
```

Adicionar:

- Penalidade por turnover.
- Penalidade por concentracao de retorno em targets suspeitos.
- Limite de peso em ativos low/reject.
- Comparacao entre portfolio ideal bruto e portfolio estavel.

Implementacao atual:

- `C_OptimizedPortfolio.py` calcula `shadow.stable_optimization` em paralelo ao otimo oficial.
- A carteira estavel avalia todos os blends entre carteira atual e portfolio ideal usando retorno ajustado, turnover, excesso de turnover, incerteza de targets, concentracao de retorno e contribuicao suspeita.
- A decisao oficial e o portfolio modelo oficial seguem intactos; a carteira estavel e diagnostica/shadow.
- O historico JSONL registra blend estavel, blend oficial, turnover poupado, trade-off de retorno ajustado e score estavel.
- `html/sections/model.html` mostra "Otimizacao Estavel" comparando otimo oficial vs carteira estavel.

Parametros atuais:

```text
TURNOVER_PENALTY_LAMBDA = 0.05
STABLE_TURNOVER_TARGET_PCT = 12
STABLE_TURNOVER_EXCESS_PENALTY_LAMBDA = 0.10
STABLE_UNCERTAINTY_PENALTY_LAMBDA = 0.03
STABLE_CONCENTRATION_PENALTY_LAMBDA = 0.02
STABLE_SUSPICIOUS_RETURN_PENALTY_LAMBDA = 0.03
```

### Dashboard

Mostrar:

- Fronteira retorno ajustado vs turnover.
- Quanto retorno adicional cada percentual de turnover compra.
- Portfolio teorico vs portfolio estavel.

### Criterios De Aceite

- O modelo consegue dizer que existe uma carteira melhor, mas nao o bastante para trocar grande parte da carteira.
- A recomendacao se torna mais estavel entre rodadas.

## Fase 7: Backtest E Calibracao

### Objetivo

Calibrar thresholds com historico em vez de intuicao.

### Scripts

Reprocessar historico comparando:

- Logica atual.
- Target quality.
- Retorno ajustado.
- Gate shadow.
- Otimizacao com turnover.

Metricas:

- Retorno realizado.
- Volatilidade.
- Drawdown.
- Turnover acumulado.
- Numero de rebalanceamentos.
- Estabilidade do conjunto de ativos.
- Falsos positivos de targets extremos.
- Performance por regime.

Implementacao atual:

- `D_Publish.py` cria `model.calibration` dentro de `dashboard_latest.json` e tambem publica `model_calibration.json`.
- O historico de `optimized_portfolio_history.jsonl` e deduplicado por data, mantendo a ultima execucao de cada dia para evitar que rodadas de desenvolvimento distorcam frequencia de trade.
- A comparacao cobre cinco versoes: oficial atual, retorno ajustado, gate shadow, plano executavel e otimizacao estavel.
- O diagnostico calcula cobertura por versao, frequencia de trade, turnover acumulado, ganho medio, estabilidade do conjunto de ativos, sinais suspeitos e falsos positivos de targets extremos quando ha retorno realizado futuro.
- Retorno realizado de 5 e 21 pregoes usa `portfolio_real_daily.csv`; quando nao ha pregoes futuros suficientes, a cobertura aparece explicitamente como limitada.
- `html/sections/model.html` mostra o painel "Comparativo de Versoes" logo apos o gate shadow.

### Dashboard

Adicionar uma visao "Comparativo de Versoes":

- Modelo atual vs modelo candidato.
- Frequencia de trade.
- Retorno/risco.
- Drawdown.
- Turnover.

### Criterios De Aceite

- Thresholds deixam de ser arbitrarios.
- O usuario consegue escolher parametros olhando consequencias historicas.

## Fase 8: Promocao Para Decisao Oficial

### Objetivo

Substituir a decisao oficial pela nova logica quando ela estiver validada.

### Scripts

- Promover `shadow_decision` para `decision`.
- Manter a decisao antiga como `legacy_decision` por 30 a 60 dias.
- Registrar `decision_engine_version`.
- Manter campos raw e adjusted para auditabilidade.

Implementacao atual:

- `C_OptimizedPortfolio.py` promove `shadow.execution_plan.decision_state` para o campo top-level `decision`.
- A logica antiga de excesso bruto segue preservada em `legacy_decision`, `legacy_reason`, `legacy_excess_return_pct` e `legacy_decision_engine_version`.
- O novo motor registra `decision_engine_version = v2_operational_shadow_conservative`, `decision_engine_phase` e `decision_transition_window_days = 60`.
- O bloco `shadow` tambem carrega decisao oficial promovida, decisao legada e versoes dos motores para auditoria.
- `D_Publish.py` passa a publicar `model.decision.verdict` a partir da decisao promovida e inclui a comparacao legada no dashboard.
- `html/sections/model.html` mostra "Motor de Decisao" com Oficial vs Legado, versao do motor e motivos do gate.
- `html/js/header.js` usa a acao oficial promovida e mostra a decisao legada no tooltip quando divergir.

### Dashboard

- Mostrar versao do motor de decisao.
- Manter comparacao com decisao legada durante periodo de transicao.
- Exibir changelog resumido da logica.

### Criterios De Aceite

- Nova decisao oficial usa retorno ajustado, qualidade de target, regime e gate de rebalanceamento.
- O usuario ainda consegue auditar como seria a decisao antiga.

## Sequencia Recomendada De Trabalho

1. Implementar Fase 0 nos scripts.
2. Expor Fase 0 no dashboard.
3. Validar com a recomendacao mais recente.
4. Implementar Fase 1 nos scripts.
5. Expor Fase 1 no dashboard.
6. Validar casos KLBN4, AMBP3 e CMIG3.
7. Implementar Fase 2 em modo shadow.
8. Expor raw vs adjusted no dashboard.
9. Implementar Fase 3 e mostrar regime.
10. Implementar Fase 4 e comparar decisao oficial vs shadow.
11. Seguir para Fases 5 a 8 apenas depois que os sinais estiverem interpretaveis.

## Checklist Por Ciclo

Use este checklist a cada rodada no VSCode:

- [ ] A mudanca preserva o pipeline atual.
- [ ] Novos campos tem nomes claros e documentados.
- [ ] O dashboard mostra a mudanca de forma auditavel.
- [ ] Foi testado com a recomendacao mais recente.
- [ ] Foi testado com pelo menos um caso anomalico conhecido.
- [ ] Logs explicam os principais calculos.
- [ ] O status deste documento foi atualizado.
- [ ] O changelog deste documento foi atualizado.

## Testes Minimos Recomendados

Para cada fase, quando aplicavel:

- Rodar o pipeline completo.
- Verificar `data/results/optimized_recommendation.json`.
- Verificar `data/results/dashboard_latest.json`.
- Verificar que campos antigos continuam presentes.
- Verificar que valores extremos nao geram `NaN`, `inf` ou erro de renderizacao.
- Validar no dashboard que texto, tabelas e cards nao quebram layout.

Casos de regressao a manter:

- KLBN4.SA: target suspeito por escala/classe/unit.
- AMBP3.SA: fallback PE setorial extremo.
- CMIG3.SA: fallback PE setorial relevante, mas menos extremo.
- Ibovespa: drawdown desde pico recente deve impactar regime.

## Parametros A Calibrar

Lista inicial, sem compromisso de valores finais:

| Parametro | Uso |
|---|---|
| `TARGET_EXTREME_UPSIDE_PCT` | Flag de upside extremo |
| `TARGET_REJECT_UPSIDE_PCT` | Rejeicao ou shrinkage maximo de upside absurdo |
| `TARGET_STALE_DAYS` | Idade maxima para target pleno |
| `TARGET_MAX_FALLBACK_QUALITY` | Qualidade maxima para fallback PE setorial |
| `RETURN_ADJUSTMENT_CAP_PCT` | Teto aplicado ao retorno bruto antes do shrinkage |
| `RETURN_ADJUSTMENT_FLOOR_PCT` | Piso aplicado ao retorno bruto antes do shrinkage |
| `RETURN_ADJUSTMENT_BASE_PCT` | Retorno-base conservador usado no shrinkage |
| `RETURN_ADJUSTMENT_REJECT_BASE_PCT` | Retorno-base para target rejeitado |
| `RETURN_ADJUSTMENT_UNCERTAINTY_PENALTY_PCT` | Penalidade maxima adicional por incerteza |
| `REGIME_DRAWDOWN_STRESS_PCT` | Drawdown de indice para stress |
| `REGIME_NEGATIVE_BREADTH_PCT` | Percentual de ativos negativos para stress |
| `REGIME_DRAWDOWN_BREADTH_PCT` | Percentual de ativos em drawdown relevante para stress |
| `REGIME_ASSET_DRAWDOWN_THRESHOLD_PCT` | Drawdown minimo por ativo para breadth de stress |
| `REGIME_VOLATILITY_WATCH_PCT` | Volatilidade anualizada para alerta |
| `REGIME_DISPERSION_WATCH_PCT` | Dispersao cross-sectional para alerta |
| `SHADOW_BASE_HURDLE_PCT` | Hurdle minimo do gate shadow antes de custos e penalidades |
| `SHADOW_SLIPPAGE_ESTIMATE_PCT` | Estimativa conservadora de slippage por rebalanceamento |
| `SHADOW_TAX_DRAG_ESTIMATE_PCT` | Arrasto tributario estimado no hurdle dinamico |
| `SHADOW_MODEL_UNCERTAINTY_PENALTY_PCT` | Penalidade fixa por incerteza do modelo |
| `SHADOW_MIN_PERSISTENCE_DAYS` | Persistencia minima do sinal |
| `SHADOW_TURNOVER_BUDGET_PCT` | Turnover maximo para trade |
| `SHADOW_CONFIDENCE_FLOOR` | Confianca minima do portfolio |
| `SHADOW_MAX_SUSPICIOUS_RETURN_CONTRIBUTION_PCT` | Limite de retorno vindo de targets suspeitos |
| `SHADOW_PARTIAL_REBALANCE_MIN_GAIN_PCT` | Ganho minimo para considerar rebalanceamento parcial quando so o turnover veta |
| `EXECUTION_ASSET_TOLERANCE_BAND_PCT` | Banda por ativo antes de transformar drift em acao |
| `EXECUTION_SECTOR_TOLERANCE_BAND_PCT` | Banda por setor para diagnosticar drift setorial relevante |
| `EXECUTION_WEEKLY_TURNOVER_BUDGET_PCT` | Orcamento semanal para execucao parcial |
| `EXECUTION_MONTHLY_TURNOVER_BUDGET_PCT` | Orcamento mensal maximo para execucao |
| `EXECUTION_MIN_TRADE_VALUE_BRL` | Valor minimo por ordem executavel |
| `EXECUTION_MAX_ACTIONS` | Numero maximo de acoes em execucao parcial |
| `TURNOVER_PENALTY_LAMBDA` | Penalidade de turnover na otimizacao |
| `STABLE_TURNOVER_TARGET_PCT` | Turnover alvo antes de penalidade adicional |
| `STABLE_TURNOVER_EXCESS_PENALTY_LAMBDA` | Penalidade extra sobre turnover acima do alvo |
| `STABLE_UNCERTAINTY_PENALTY_LAMBDA` | Penalidade por baixa qualidade media dos targets |
| `STABLE_CONCENTRATION_PENALTY_LAMBDA` | Penalidade por concentracao do retorno esperado |
| `STABLE_SUSPICIOUS_RETURN_PENALTY_LAMBDA` | Penalidade por retorno vindo de targets low/reject |

## Registro De Decisoes

| Data | Decisao | Motivo |
|---|---|---|
| 2026-06-05 | Usar modo shadow em vez de pipeline duplicado | Permite evoluir sem quebrar a decisao oficial |
| 2026-06-05 | Alternar scripts e dashboard por fase | Permite observar cada melhoria antes de seguir |
| 2026-06-05 | Priorizar target quality antes de trocar otimizacao | Diagnostico mostrou retornos extremos concentrados em poucos targets |

## Changelog

| Data | Mudanca |
|---|---|
| 2026-06-06 | Fase 8 implementada: decisao operacional promovida para `decision`, decisao bruta preservada como `legacy_decision`, `decision_engine_version` registrado, dashboard mostra Oficial vs Legado e header usa a nova acao oficial |
| 2026-06-06 | Fase 7 implementada: `D_Publish.py` publica `model.calibration`/`model_calibration.json` com comparativo historico de versoes, cobertura, trade frequency, turnover, retorno realizado futuro, estabilidade, falsos positivos e performance por regime; `model.html` mostra "Comparativo de Versoes" |
| 2026-06-06 | Fase 6 implementada: `shadow.stable_optimization` compara otimo oficial vs carteira estavel com penalidades de turnover, incerteza, concentracao e retorno suspeito; historico ganhou campos estaveis; `model.html` mostra "Otimizacao Estavel" |
| 2026-06-06 | Fase 5 implementada: `shadow.execution_plan` com estado executavel, intensidade, bandas por ativo/setor, orcamento semanal/mensal, classificacao de acoes, historico resumido e painel "Plano Executavel" em `model.html` |
| 2026-06-05 | Fase 4 implementada: gate shadow em `C_OptimizedPortfolio.py`, hurdle dinamico, vetos de persistencia/turnover/qualidade/retorno suspeito, historico shadow, publicacao em `dashboard_latest.json`, e painel "Gate Shadow" em `model.html` |
| 2026-06-05 | Fase 3 implementada: helper `shared_tools/market_regime.py`, `diagnostics.market_regime` no otimizador, resumo de regime no shadow/historico, publicacao no dashboard, e card de regime em `risk.html` |
| 2026-06-05 | Fase 2 implementada: retorno esperado ajustado por qualidade do target em modo shadow, novas colunas `Adjusted*`/`ShrinkageFactor` no scoring, `diagnostics.adjusted_returns` e `shadow` no otimizador, campos ajustados em `dashboard_latest.json`, e comparacao bruto vs ajustado no card de origem do retorno |
| 2026-06-05 | Fase 1 implementada: helper compartilhado `shared_tools/target_quality.py`, novas colunas `TargetQuality*` em `scored_stocks.csv`, contributors com `target_quality_score/bucket/flags`, resumo por bucket em `dashboard_latest.json`, e coluna "Qualidade" no card de origem do retorno |
| 2026-06-05 | Fase 0 implementada: `optimized_recommendation.json` ganhou `diagnostics` com concentracao de retorno, top contribuintes, fonte do target e turnover; `dashboard_latest.json` publica resumo diagnostico; `model.html` exibe origem do retorno esperado e alerta de concentracao |
| 2026-06-05 | Criacao do plano inicial de implementacao |
