# Plano Mestre: PortfolioESG Como Assessor De Investimentos

Data inicial: 2026-06-10
Status: Proposto

Este documento consolida a evolucao do projeto de um recomendador de carteiras de acoes
para um assessor de investimentos pessoal, incremental e auditavel.

Ele combina duas frentes:

1. **Produto/decisao:** criar uma experiencia que ajude a decidir o que fazer no portfolio
   total, hoje e de forma segura.
2. **Pipeline/arquitetura:** transformar os scripts atuais sem quebrar o fluxo A -> B -> C -> D,
   adicionando uma camada de assessor que consiga receber multiplas estrategias ao longo do tempo.

O objetivo nao e fazer uma grande reescrita. O objetivo e evoluir por fases pequenas,
validaveis e registradas.

---

## Tese Central

O projeto nao deve mais ser pensado como:

> "Qual modelo de acoes recomenda a melhor carteira?"

Ele deve evoluir para:

> "Existe evidencia suficiente, liquida de custos, riscos, incerteza, liquidez e restricoes
> pessoais, para alterar o portfolio consolidado agora?"

Essa mudanca implica separar tres responsabilidades:

1. **Estrategias** produzem sinais.
2. **Assessor/alocador** decide a alocacao consolidada.
3. **Execucao** traduz a decisao em ordens e mudancas operacionais.

---

## Principios

1. **Carteira atual e o default racional.** Toda estrategia precisa justificar por que vale
   mexer nela.
2. **Decisao e pesquisa sao telas diferentes.** A pagina de decisao deve ser prescritiva;
   a pagina de modelo/estrategias pode ser densa e investigativa.
3. **Risco e do portfolio total.** Risco do modelo pertence a analise da estrategia; `risk.html`
   deve mostrar risco consolidado do investidor.
4. **Scripts continuam pequenos e auditaveis.** O `run_all.sh` deve orquestrar, nao concentrar
   inteligencia.
5. **Compatibilidade primeiro.** A nova camada deve inicialmente replicar a decisao atual, antes
   de promover qualquer logica nova.
6. **Shadow antes de promocao.** Toda mudanca de decisao deve aparecer em diagnostico antes de
   virar recomendacao oficial.
7. **Registrar consolidacoes.** Cada fase deve atualizar este documento ou um changelog de fase.

---

## Arquitetura Alvo

### Camadas

```text
A. Dados e universo
   Precos, fundamentos, taxas, benchmarks, parametros.

B. Portfolio real
   Posicoes, caixa, historico, custos, liquidez observada.

C. Estrategias
   Cada estrategia publica sinais independentes.

D. Macro / Regime
   Cenario economico, juros, inflacao, bolsa, cambio, credito e apetite a risco.

E. Assessor / Alocador
   Combina estrategias e decide portfolio consolidado.

F. Execucao
   Ordens, caixa, custos, bandas, pendencias e status.

G. Publicacao / Frontend
   Artefatos estaveis para paginas de decisao, portfolio, risco e estrategias.
```

### Papeis Dos Scripts Atuais

| Script atual | Papel atual | Papel alvo |
|---|---|---|
| `A1_Download.py` / `A1b_DownloadFundCVM.py` | Coleta de dados | Continua como coleta base |
| `A2_Scoring.py` | Score de ativos de acoes | Insumo de estrategias de acoes |
| `A3_Portfolio.py` | Carteira modelo de acoes | Gerador de candidatos/sinais de acoes |
| `A4_Analysis.py` | Analises de risco/performance | Insumos de estrategia e risco consolidado |
| `B*` | Carteira real, notas, caixa | Fonte canonica do portfolio atual |
| `C_OptimizedPortfolio.py` | Recomendador final de acoes | Produtor de sinais de estrategias de acoes |
| `M_MacroRegime.py` | Nao existe | Camada de regime economico e implicacoes por estrategia |
| `E_Advisor.py` | Nao existe | Assessor/alocador consolidado |
| `D_Publish.py` | Publicacao frontend | Publica tambem advisor/risk/strategy artefacts |
| `run_all.sh` | Orquestrador A -> B -> C -> D | Orquestrador A -> B -> C -> M -> E -> D |

### Novos Componentes

```text
engines/M_MacroRegime.py
```

Responsabilidade:

- Coletar ou consolidar indicadores publicos de mercado e economia.
- Classificar regimes de juros, inflacao, bolsa, cambio, credito e apetite a risco.
- Produzir implicacoes por classe/estrategia.
- Gerar `macro_regime.json`.
- Alimentar o assessor sem tomar a decisao final sozinho.

```text
engines/E_Advisor.py
```

Responsabilidade:

- Ler sinais de estrategias.
- Ler portfolio real.
- Ler estado de risco.
- Ler regime macroeconomico.
- Aplicar politica pessoal e restricoes.
- Decidir a alocacao consolidada.
- Gerar `advisor_latest.json`.
- Gerar ou referenciar plano de execucao oficial.

Na primeira versao, `E_Advisor.py` deve apenas encapsular a decisao atual de
`optimized_recommendation.json`. Depois, passa a adicionar julgamento proprio.

---

## Contratos De Dados Alvo

### 1. `strategy_signals.json`

Arquivo futuro:

```text
data/results/strategy_signals.json
html/data/strategy_signals.json
```

Formato conceitual:

```json
{
  "generated_at": "2026-06-10T12:00:00Z",
  "strategies": [
    {
      "id": "equity_brazil_balanced",
      "label": "Acoes Brasil - Ponderada",
      "asset_classes": ["equity_brazil"],
      "role": "investable_target",
      "horizon": "12m",
      "expected_return_pct": 14.35,
      "adjusted_return_pct": 14.35,
      "risk": {
        "volatility_pct": null,
        "drawdown_pct": null,
        "liquidity_days": null
      },
      "confidence": {
        "score": 0.74,
        "drivers": ["target_quality_high", "return_not_concentrated"],
        "warnings": []
      },
      "constraints": {
        "min_weight_pct": 0,
        "max_weight_pct": 40
      },
      "portfolio": {
        "weights": {}
      },
      "execution": {
        "turnover_pct": 188.44,
        "estimated_cost_brl": 0
      },
      "status": "candidate"
    }
  ]
}
```

### 2. `advisor_latest.json`

Arquivo central da pagina de decisao:

```text
data/results/advisor_latest.json
html/data/advisor_latest.json
```

Formato conceitual:

```json
{
  "generated_at": "2026-06-10T12:00:00Z",
  "advisor_version": "v0_compatibility",
  "portfolio_state": {
    "health": "ok",
    "dominant_issues": [],
    "current_allocation": {}
  },
  "decision": {
    "action": "HOLD",
    "destination": "STAY_CURRENT",
    "summary": "Manter carteira atual; sinais alternativos nao compensam turnover e incerteza.",
    "confidence": "medium",
    "primary_reasons": [],
    "vetoes": []
  },
  "recommended_allocation": {
    "type": "current_portfolio",
    "weights": {}
  },
  "action_vs_inaction": {
    "expected_gain_pct": null,
    "risk_of_action": [],
    "risk_of_inaction": []
  },
  "rejected_alternatives": [
    {
      "strategy_id": "equity_brazil_acid",
      "reason": "Retorno depende de targets de baixa qualidade e alto turnover."
    }
  ],
  "execution_plan": {
    "state": "HOLD",
    "actions": []
  },
  "links": {
    "source_recommendation": "optimized_recommendation.json",
    "source_dashboard": "dashboard_latest.json"
  }
}
```

### 3. `risk_state.json`

Arquivo futuro para risco consolidado:

```text
data/results/risk_state.json
html/data/risk_state.json
```

Deve representar o risco do portfolio total:

- exposicao por classe
- exposicao por fator
- concentracao por ativo/emissor/setor/classe
- liquidez
- volatilidade
- drawdown
- stress tests
- contribuicao de risco por estrategia
- riscos dominantes

### 4. `macro_regime.json`

Arquivo futuro para contexto economico e de mercado:

```text
data/results/macro_regime.json
html/data/macro_regime.json
```

Formato conceitual:

```json
{
  "generated_at": "2026-06-10T12:00:00Z",
  "macro_version": "v0_regime_snapshot",
  "regime": {
    "growth": "unknown",
    "inflation": "sticky",
    "rates": "restrictive",
    "equity_market": "stress",
    "fx": "pressure",
    "credit": "neutral",
    "risk_appetite": "weak"
  },
  "indicators": {
    "selic_current_pct": 10.5,
    "selic_expected_12m_pct": 9.75,
    "ipca_12m_pct": 4.2,
    "ipca_expected_12m_pct": 4.0,
    "usdbrl": 5.35,
    "ibovespa_drawdown_3m_pct": -12.0,
    "yield_curve_state": "steepening"
  },
  "implications": [
    {
      "target": "equity_brazil",
      "effect": "negative",
      "confidence": "medium",
      "reason": "Juros reais elevados e stress de bolsa aumentam hurdle para risco."
    },
    {
      "target": "fixed_income_post",
      "effect": "positive",
      "confidence": "medium",
      "reason": "Carrego nominal permanece relevante."
    }
  ],
  "data_sources": [
    "Banco Central SGS",
    "Banco Central Focus",
    "Yahoo/Stooq/B3 proxies"
  ]
}
```

O macro nao deve recomendar compra/venda sozinho. Ele deve ajustar confianca, hurdles,
orcamento de risco, turnover, limites e alertas do assessor.

---

## Paginas Alvo

### 1. `decision.html` - Decisao / Acao

Pergunta:

> "O que eu faco agora?"

Conteudo:

1. Estado da carteira atual.
2. Carteira recomendada agora.
3. Tese da decisao.
4. Confianca, vetos e incertezas.
5. Custo de agir vs custo de nao agir.
6. Plano de execucao oficial.
7. Alternativas rejeitadas.

Nao deve conter auditoria extensa. Historico entra apenas como resumo de confianca.

### 2. `portfolio.html` - Portfolio Real

Pergunta:

> "O que eu tenho e como esta performando?"

Conteudo:

- patrimonio
- P&L
- performance TWR/MWR/broker
- contribuicao por ativo/classe
- caixa
- evolucao historica

### 3. `risk.html` - Risco Consolidado

Pergunta:

> "Meu portfolio total esta compativel com meu perfil?"

Conteudo:

- risco por classe
- risco por fator
- concentracao
- liquidez
- stress tests
- drawdown
- risco cambial/juros/inflacao/commodities

Nao deve ser risco de um modelo especifico.

### 4. `model.html` ou `strategies.html` - Estrategias / Pesquisa

Pergunta:

> "As estrategias produzem sinais bons, estaveis e confiaveis?"

Conteudo:

- comparacao de estrategias
- historico de sinais
- retorno esperado vs realizado
- target quality
- estabilidade de composicao
- turnover
- parametros
- backtest/forward validation

---

## Evolucao Do `run_all.sh`

### Estado Atual

```text
run_all.sh
  -> A_Portfolio.sh
  -> B_Ledger.sh
  -> C_OptimizedPortfolio.sh
  -> D_Publish.py
```

### Estado Alvo Incremental

```text
run_all.sh
  -> A_Portfolio.sh
  -> B_Ledger.sh
  -> C_OptimizedPortfolio.sh
  -> M_MacroRegime.py
  -> E_Advisor.py
  -> D_Publish.py
```

### Principio

`run_all.sh` deve continuar simples:

- validar pre-flight
- rodar etapas
- logar duracao
- parar em erro critico
- aceitar flags como `--only-advisor` futuramente
- aceitar flags como `--skip-macro` futuramente

Ele nao deve calcular decisao, risco ou alocacao.

---

## Plano Incremental

### Fase 0 - Consolidar Visao E Congelar Escopo Inicial

Status: proposto

Objetivo:

- Registrar esta arquitetura.
- Definir que a primeira entrega nao adiciona novas classes de ativos.
- Definir que a primeira entrega apenas reorganiza a decisao atual em contrato de assessor.

Entregaveis:

- `docs/INVESTMENT_ADVISOR_ARCHITECTURE.md`
- Lista de artefatos atuais que alimentarao o assessor.
- Criterios de aceite para `advisor_latest.json`.

Criterio de aceite:

- O projeto tem um plano unico e incremental.
- Nenhuma logica de investimento e alterada.

---

### Fase 1 - `E_Advisor.py` Em Modo Compatibilidade

Status: proposto

Objetivo:

Criar a camada do assessor sem mudar a decisao atual.

Entradas:

- `data/results/optimized_recommendation.json`
- `data/results/dashboard_latest.json`
- `data/ledger_positions.json`
- `data/results/model_return_history.json` quando existir

Saida:

- `data/results/advisor_latest.json`

Comportamento:

- Copiar a decisao oficial atual.
- Definir a carteira recomendada atual.
- Extrair plano de execucao oficial.
- Montar alternativas rejeitadas com base nos sinais Acida/Ponderada.
- Criar explicacao estruturada minima.

Mudancas no pipeline:

- Adicionar `E_Advisor.py`.
- Adicionar chamada opcional em `run_all.sh`, inicialmente apos C e antes de D.
- Adicionar flag futura `--skip-advisor`.

Criterios de aceite:

- `advisor_latest.json` e gerado.
- Decisao em `advisor_latest.json` bate com `optimized_recommendation.json`.
- Nenhuma pagina existente quebra.
- `run_all.sh --dry-run` mostra a etapa do assessor.

---

### Fase 2 - `decision.html` V0

Status: proposto

Objetivo:

Criar uma pagina nova para decisao, consumindo `advisor_latest.json`.

Blocos:

1. Estado da carteira atual.
2. Carteira recomendada agora.
3. Tese da decisao.
4. Vetos/confiança.
5. Execucao oficial.
6. Alternativas rejeitadas.

Fora de escopo:

- Graficos historicos extensos.
- Novos modelos.
- Nova logica de alocacao.

Criterios de aceite:

- O usuario consegue responder "o que faco hoje?" sem abrir `model.html`.
- Header continua mostrando a decisao resumida.
- `model.html` pode permanecer como pagina tecnica.

---

### Fase 3 - Formalizar Estrategias De Acoes

Status: proposto

Objetivo:

Transformar Acida e Ponderada em estrategias formais.

Mudancas:

- Criar `strategy_signals.json` ou bloco equivalente dentro de `advisor_latest.json`.
- Mapear:
  - `equity_brazil_acid`
  - `equity_brazil_balanced`
  - `current_portfolio`
- Cada estrategia publica retorno, risco, confianca, turnover, custo, portfolio e vetos.

Possivel implementacao:

- Manter calculos em `C_OptimizedPortfolio.py`.
- Adicionar normalizador em `E_Advisor.py`.
- Evitar reescrever C nesta fase.

Criterios de aceite:

- A pagina de decisao nao precisa conhecer o schema antigo Acida/Ponderada.
- Uma nova estrategia futura poderia ser adicionada com o mesmo contrato.

---

### Fase 4 - Alocador V0

Status: proposto

Objetivo:

Fazer o assessor decidir entre manter atual, mover para ponderada, considerar acida como
radar, ou executar parcialmente, usando regra explicita.

Regra inicial:

```text
Executar se:
  ganho ajustado > hurdle
  + sinal persistente
  + qualidade minima
  + turnover dentro do orcamento
  + concentracao aceitavel
  + sem veto de regime/risco
```

Saidas:

- `decision.primary_reasons`
- `decision.vetoes`
- `action_vs_inaction`
- `rejected_alternatives`

Criterios de aceite:

- Toda decisao tem razoes estruturadas.
- Todo modelo rejeitado tem veto dominante.
- A decisao pode ser auditada sem ler logs.

---

### Fase 5 - Risk Consolidado

Status: proposto

Objetivo:

Mover `risk.html` para risco do portfolio total.

Saida nova:

- `risk_state.json`

Blocos:

- exposicao por classe
- concentracao por ativo/setor/emissor
- liquidez
- drawdown/volatilidade
- stress tests iniciais
- riscos dominantes

Criterios de aceite:

- `risk.html` nao fala mais de risco de um modelo isolado como se fosse risco do investidor.
- A pagina de decisao consome um resumo de risco consolidado.

---

### Fase 6 - Macro / Regime Economico V0

Status: proposto

Objetivo:

Adicionar uma camada quantitativa simples de contexto economico e mercado para avaliar se
as recomendacoes futuras fazem sentido frente ao ambiente.

Motivacao:

- O stress de mercado ja influencia o modelo, mas isso e apenas uma versao minima de regime.
- Ao incluir renda fixa, ETFs, ouro, cambio e hedge, macro deixa de ser contexto narrativo e
  vira insumo de alocacao.
- A decisao deve comparar estrategias com o ambiente economico, nao apenas entre si.

Script novo:

```text
engines/M_MacroRegime.py
```

Saida:

```text
data/results/macro_regime.json
html/data/macro_regime.json
```

Indicadores V0:

- Selic atual.
- Expectativa Selic 12m.
- IPCA 12m.
- Expectativa IPCA 12m.
- Dolar/BRL.
- Ibovespa trend/drawdown.
- Juros longos ou proxy de duration.
- CDI / taxa livre de risco.
- Proxy global de apetite a risco, como S&P 500, VIX ou DXY, se facil de obter.

Fontes publicas candidatas:

- Banco Central SGS.
- Banco Central Focus.
- Tesouro Direto.
- Anbima, quando viavel.
- IBGE/IPEAData.
- Yahoo/Stooq/B3 proxies.
- FRED para indicadores globais.

Saidas interpretativas:

- regime de juros
- regime de inflacao
- regime de bolsa
- regime cambial
- apetite a risco
- implicacoes por estrategia/classe

Como deve influenciar o assessor:

- ajustar hurdle para acoes
- ajustar limite de risco
- ajustar orcamento de turnover
- favorecer ou penalizar duration
- favorecer ou penalizar caixa/renda fixa
- sugerir necessidade de hedge
- sinalizar riscos macro dominantes

Criterios de aceite:

- `macro_regime.json` e gerado com dados atuais e fonte indicada.
- O macro aparece como insumo explicativo, nao como decisao autonoma.
- `advisor_latest.json` referencia o regime macro ou suas implicacoes.
- Falha de coleta macro nao quebra o pipeline; usa ultimo dado valido ou status `stale`.

---

### Fase 7 - Pagina De Estrategias / Modelo

Status: proposto

Objetivo:

Transformar `model.html` em uma pagina de pesquisa e qualidade das estrategias.

Conteudo:

- historico de retornos esperados
- historico de decisoes
- forward validation
- estabilidade de sinais
- qualidade de targets
- turnover
- parametros e versoes

Criterios de aceite:

- `decision.html` responde acao.
- `model.html`/`strategies.html` responde qualidade dos modelos.
- Nao ha duplicacao confusa entre as duas paginas.

---

### Fase 8 - Politica Pessoal De Investimento

Status: proposto

Objetivo:

Criar uma politica formal do investidor para orientar o assessor.

Arquivo sugerido:

```text
parameters/investment_policy.json
```

Campos:

- horizonte
- tolerancia a drawdown
- liquidez minima
- limite por ativo
- limite por classe
- limite por estrategia
- turnover mensal maximo
- caixa minimo
- renda fixa minima
- exposicao internacional alvo
- hedge permitido
- preferencias ESG

Criterios de aceite:

- O assessor consegue explicar uma decisao com base no perfil, nao apenas nos modelos.
- Mudancas de perfil ficam versionadas em parametros.

---

### Fase 9 - Novas Classes E Estrategias

Status: proposto

Objetivo:

Adicionar novas estrategias sem mudar a arquitetura.

Possiveis scripts:

- `S_FixedIncome.py`
- `S_ETF.py`
- `S_Gold.py`
- `S_Hedge.py`

Cada estrategia deve publicar o mesmo tipo de sinal:

- retorno esperado
- risco esperado
- liquidez
- custos
- confianca
- limites
- portfolio/produtos candidatos

Criterios de aceite:

- O assessor combina estrategias; nao escolhe apenas uma vencedora.
- A pagina de risco mostra exposicao consolidada por classe/fator.

---

### Fase 10 - Execucao Avancada

Status: proposto

Objetivo:

Separar completamente recomendacao de implementacao operacional.

Conteudo:

- ordens oficiais
- caixa necessario
- saldo gerado
- custos
- impacto tributario quando possivel
- bandas de rebalanceamento
- status por ordem
- historico de execucao

Criterios de aceite:

- O usuario consegue abrir uma tela e executar na corretora sem reinterpretar a tese.
- Ordens simuladas nao se misturam com ordens oficiais.

---

## Roadmap De Curto Prazo Recomendado

Ordem sugerida para os proximos ciclos:

1. **Fase 1:** criar `E_Advisor.py` em modo compatibilidade.
2. **Fase 2:** criar `decision.html` V0.
3. **Fase 3:** formalizar Acida/Ponderada como estrategias.
4. **Fase 4:** implementar razoes/vetos estruturados.
5. **Fase 5:** redesenhar `risk.html` para risco consolidado.
6. **Fase 6:** adicionar `M_MacroRegime.py` V0 antes de novas classes.

Essa ordem evita adicionar novos ativos antes de ter o esqueleto certo.

---

## Relacao Com Docs Existentes

| Documento | Papel apos este plano |
|---|---|
| `docs/PORTFOLIO_RECOMMENDER_IMPLEMENTATION_PLAN.md` | Historico detalhado da evolucao do recomendador de acoes |
| `docs/PIPELINE_VISUAL_MAP.md` | Mapa do pipeline atual; deve ser atualizado quando E_Advisor entrar |
| `docs/MODEL_RETURN_HISTORY_CHART_PLAN.md` | Plano especifico para historico de retornos de modelos |
| `docs/METRICS_REFERENCE.md` | Referencia de metricas exibidas |
| `docs/INVESTMENT_ADVISOR_ARCHITECTURE.md` | Plano mestre da arquitetura futura |

O plano do recomendador de portfolio nao deve ser apagado. Ele vira o historico da camada
de estrategias de acoes. Este documento passa a ser o plano superior.

---

## Registro De Decisoes

| Data | Decisao |
|---|---|
| 2026-06-10 | Separar decisao imediata de analise de modelos. |
| 2026-06-10 | Tratar Acida/Ponderada como estrategias de acoes, nao como arquitetura final do assessor. |
| 2026-06-10 | Evoluir `run_all.sh` incrementalmente com nova etapa `E_Advisor.py`. |
| 2026-06-10 | `risk.html` deve representar risco consolidado do portfolio total. |
| 2026-06-10 | Adicionar camada `M_MacroRegime.py` para regime economico e implicacoes por estrategia. |
