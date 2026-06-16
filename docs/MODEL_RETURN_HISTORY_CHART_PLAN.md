# Plano de Implementacao: Grafico Historico de Retornos dos Modelos

Data inicial: 2026-06-10
Status: Proposto
Pagina alvo: `html/sections/model.html`

## Objetivo

Adicionar a pagina Modelo um grafico de linhas historico que mostre, a cada execucao do
pipeline, o retorno percentual calculado para cada carteira/modelo relevante. O grafico
deve ajudar a responder:

- A recomendacao esta ficando mais forte, mais fraca ou instavel?
- A Carteira Acida esta gerando sinal persistente ou apenas picos isolados?
- A Carteira Ponderada esta convergindo para um retorno atrativo?
- Mudancas de parametros causaram saltos bruscos no retorno calculado?
- Mudancas no motor de decisao alteraram o comportamento de forma visivel?

O objetivo nao e substituir a recomendacao oficial do dia, mas adicionar uma visao temporal
para diagnostico e confianca.

## Principio De UX

A pagina Modelo deve continuar respondendo primeiro:

1. Qual e a recomendacao oficial?
2. Qual e a composicao da carteira dessa recomendacao?
3. O que muda hoje?

O grafico historico entra depois desses blocos, como monitoramento. Ele nao deve competir
com a decisao oficial nem aparecer como recomendacao alternativa.

Ordem sugerida da pagina:

1. Recomendacao oficial
2. Composicao da carteira recomendada
3. Plano de execucao oficial
4. Tendencia dos modelos
5. Comparacao Atual vs. Acida vs. Ponderada
6. Exposicao setorial e correlacao
7. Auditoria tecnica

## Fonte De Dados Atual

O repositorio ja possui historico de recomendacoes em:

- `data/results/optimized_portfolio_history.jsonl`
- `data/results/optimized_portfolio_history.csv`

O JSONL contem campos uteis para o grafico, incluindo:

- `timestamp`
- `date`
- `decision`
- `decision_destination`
- `decision_engine_version`
- `holdings_return_pct`
- `optimal_return_pct`
- `optimal_net_return_pct`
- `acid_expected_return_pct`
- `acid_adjusted_net_return_pct`
- `balanced_expected_return_pct`
- `balanced_adjusted_net_return_pct`
- `shadow_decision`
- `execution_state`
- `acid_signal`
- `balanced_signal`

Problema atual: `optimized_portfolio_history.jsonl` vive em `data/results/`, mas nao parece
estar exposto diretamente em `html/data/`. Para a UI, a melhor opcao e publicar um artefato
limpo e pequeno em JSON.

## Artefato De Publicacao Proposto

Criar um novo arquivo publicado:

```text
data/results/model_return_history.json
html/data/model_return_history.json
```

Formato sugerido:

```json
{
  "generated_at": "2026-06-10 21:00:00",
  "source": "optimized_portfolio_history.jsonl",
  "series": [
    {
      "run_id": "20260609-223301",
      "timestamp": "2026-06-09 22:33:01",
      "date": "2026-06-09",
      "decision": "WATCH",
      "decision_destination": "STAY_CURRENT",
      "decision_engine_version": "v4_independent_balanced_target",
      "returns": {
        "current_pct": 227.99,
        "acid_raw_pct": 252.11,
        "acid_adjusted_net_pct": 9.945,
        "balanced_raw_pct": 14.3471,
        "balanced_adjusted_net_pct": 14.3471
      },
      "signals": {
        "acid": "MOVE_TO_ACID",
        "balanced": "STAY_CURRENT",
        "shadow": "WATCH",
        "execution": "WATCH"
      },
      "quality": {
        "acid_target_quality_score": 0.4691,
        "balanced_target_quality_score": 1.0
      },
      "turnover": {
        "acid_pct": 52.0766,
        "balanced_pct": 188.443
      }
    }
  ]
}
```

### Campos Obrigatorios Para A Primeira Versao

- `timestamp`
- `date`
- `decision`
- `decision_destination`
- `decision_engine_version`
- `returns.current_pct`
- `returns.acid_adjusted_net_pct`
- `returns.balanced_adjusted_net_pct`

### Campos Opcionais Para Tooltips E Diagnostico

- `returns.acid_raw_pct`
- `returns.balanced_raw_pct`
- `signals.acid`
- `signals.balanced`
- `signals.shadow`
- `turnover.acid_pct`
- `turnover.balanced_pct`
- `quality.acid_target_quality_score`
- `quality.balanced_target_quality_score`

## Metrica Padrao Do Grafico

Usar retorno ajustado/net como padrao, porque e a metrica mais proxima da decisao
investivel.

Linhas iniciais:

| Linha | Campo | Motivo |
|---|---|---|
| Carteira Atual | `returns.current_pct` | Referencia real de partida |
| Carteira Acida | `returns.acid_adjusted_net_pct` | Radar agressivo ajustado |
| Carteira Ponderada | `returns.balanced_adjusted_net_pct` | Destino investivel |

Observacao importante: hoje `holdings_return_pct` pode ser retorno bruto por target,
enquanto a Acida/Ponderada possuem campos ajustados. Na implementacao, validar se existe
campo historico ajustado para carteira atual. Se nao existir, usar `holdings_return_pct`
com label explicito, ou persistir um novo campo `holdings_adjusted_return_pct` antes de
promover o grafico como comparacao principal.

## Controles De UI

Primeira versao:

- Grafico de linhas com Chart.js, reaproveitando a dependencia ja usada em `model.html`.
- Toggle entre:
  - `Ajustado`
  - `Bruto`
- Toggle de janelas:
  - `30 exec.`
  - `90 exec.`
  - `Tudo`
- Tooltip com:
  - data/hora
  - retorno de cada linha
  - decisao oficial
  - destino oficial
  - versao do motor

Segunda versao:

- Marcadores verticais quando `decision_engine_version` muda.
- Marcadores ou pontos destacados quando `decision_destination` muda.
- Destaque de saltos bruscos.

## Deteccao De Mudancas Bruscas

Adicionar diagnostico simples por serie:

```text
delta_pp = valor_atual - valor_anterior
abs(delta_pp) >= threshold_pp => salto brusco
```

Threshold inicial sugerido:

- `5 p.p.` para retornos ajustados
- `25 p.p.` para retornos brutos, se forem exibidos

O artefato publicado pode calcular flags:

```json
"alerts": [
  {
    "series": "balanced_adjusted_net_pct",
    "delta_pp": 7.2,
    "severity": "large_move"
  }
]
```

Na primeira versao, isso pode ser calculado no frontend para evitar mudar muito o backend.
Na versao final, faz sentido publicar as flags no JSON para manter a regra auditavel.

## Implementacao Backend

Arquivo provavel:

- `engines/D_Publish.py`

Adicionar uma funcao:

```python
def publish_model_return_history():
    # 1. Ler data/results/optimized_portfolio_history.jsonl
    # 2. Normalizar campos relevantes
    # 3. Ordenar por timestamp
    # 4. Limitar ou manter historico completo
    # 5. Salvar data/results/model_return_history.json
    # 6. Expor em html/data/model_return_history.json
```

Regras:

- Ignorar linhas JSON invalidas sem quebrar a publicacao, mas registrar warning.
- Deduplicar por `timestamp` ou `run_id` quando houver repeticao.
- Preservar valores `null` quando campo nao existir.
- Nao recalcular a decisao; apenas publicar historico.
- Nao alterar `optimized_portfolio_history.jsonl`.

## Implementacao Frontend

Arquivo alvo:

- `html/sections/model.html`

Adicionar bloco HTML:

```html
<div class="card">
  <div class="card-header">Tendencia dos Modelos</div>
  <div id="model-return-history"><span class="loading">Carregando historico...</span></div>
</div>
```

Posicao recomendada:

- Depois dos blocos de recomendacao/composicao/plano oficial.
- Antes de comparacoes longas e auditoria.

Adicionar funcoes JS:

```js
function renderModelReturnHistory(history) {}
function normalizeHistoryRows(history) {}
function buildReturnHistoryDatasets(rows, mode) {}
function detectReturnJumps(rows, fields, threshold) {}
```

Adicionar fetch no `render()`:

```js
const [dashboard, pipeline, recommendation, returnHistory] = await Promise.all([
  fetchJSON('dashboard_latest.json'),
  fetchJSON('pipeline_latest.json'),
  fetchJSON('optimized_recommendation.json'),
  fetchJSON('model_return_history.json'),
]);
```

Se o arquivo nao existir, a pagina deve continuar funcionando e mostrar:

```text
Historico de retornos ainda nao publicado.
```

## Design Visual

Evitar que o grafico vire mais uma fonte de confusao:

- Titulo claro: `Tendencia dos Modelos`
- Subtitulo curto: `Retorno calculado por execucao; usado para diagnostico, nao como ordem.`
- Linhas com semantica consistente:
  - Atual: neutro/cinza
  - Acida: amber
  - Ponderada: azul
- Nao usar vermelho/verde para a linha em si; reservar essas cores para ganho/perda ou alertas.
- Mostrar poucos controles, de preferencia segmentados.
- Tooltip deve explicar o ponto, nao apenas repetir numeros.

## Criterios De Aceite

1. A pagina Modelo continua carregando mesmo sem `model_return_history.json`.
2. Quando o historico existe, o grafico mostra pelo menos Atual, Acida e Ponderada.
3. O usuario consegue ver a tendencia dos retornos ao longo das execucoes.
4. Mudancas de `decision_engine_version` ficam identificaveis no tooltip ou em marcador.
5. Saltos bruscos ficam visiveis sem poluir o grafico.
6. A recomendacao oficial continua sendo o primeiro foco da pagina.
7. O grafico nao mistura retorno bruto e ajustado sem label explicito.
8. A implementacao nao altera a logica de decisao do modelo.

## Plano Incremental

### Fase 1: Publicacao Do Historico

- Criar `model_return_history.json` a partir de `optimized_portfolio_history.jsonl`.
- Expor o arquivo em `html/data/`.
- Validar quantidade de pontos, ordenacao temporal e campos nulos.

### Fase 2: Grafico Basico

- Adicionar card `Tendencia dos Modelos` em `model.html`.
- Renderizar linhas de retorno ajustado/net.
- Implementar janela `30 exec.`, `90 exec.`, `Tudo`.
- Garantir fallback se houver menos de 2 pontos.

### Fase 3: Tooltips E Contexto De Decisao

- Incluir decisao, destino e motor no tooltip.
- Destacar pontos onde `decision_destination` muda.
- Mostrar ultima leitura em mini-metricas acima do grafico.

### Fase 4: Alertas De Mudanca Brusca

- Detectar variacoes grandes entre execucoes.
- Exibir marcador no ponto do salto.
- Adicionar resumo textual compacto: `2 saltos detectados nos ultimos 30 runs`.

### Fase 5: Integracao Com Reestruturacao Da Pagina

- Reposicionar o grafico dentro da nova hierarquia:
  recomendacao oficial, composicao, execucao, tendencia, comparacoes, auditoria.
- Mover comparacoes longas para areas secundarias ou detalhes expansivos.

## Riscos E Cuidados

### Risco: Comparar bruto com ajustado

Mitigacao:

- Padrao visual deve ser ajustado/net.
- Se retorno atual ajustado nao existir historicamente, criar campo no backend ou deixar label
  claro como `Atual bruto`.

### Risco: Historico antigo com schema incompleto

Mitigacao:

- Normalizador tolerante a campos ausentes.
- Tooltip deve ocultar linhas sem valor.
- O grafico deve ignorar pontos `null` sem quebrar.

### Risco: Muitas execucoes no eixo X

Mitigacao:

- Janela padrao: ultimas 30 execucoes.
- Eixo X com datas compactas.
- Tooltip com timestamp completo.

### Risco: Grafico competir com a recomendacao

Mitigacao:

- Nunca colocar acima do bloco de recomendacao oficial.
- Usar texto de apoio curto: `Diagnostico historico`.
- Evitar badges de compra/venda dentro do grafico.

## Testes E Validacao

Backend:

- Testar JSONL com linha invalida.
- Testar historico vazio.
- Testar duplicidade de `run_id`.
- Testar linhas antigas sem campos da Carteira Ponderada.

Frontend:

- Abrir `model.html` com historico normal.
- Abrir com `model_return_history.json` ausente.
- Abrir com apenas 1 ponto.
- Validar em desktop e mobile.
- Verificar que Chart.js nao cria canvas vazio.

Validacao manual:

- Conferir ultimo ponto do grafico contra `optimized_recommendation.json`.
- Conferir se mudanca brusca detectada corresponde a diferenca real entre execucoes.
- Conferir se tooltip mostra a versao correta do motor de decisao.

## Fora De Escopo Da Primeira Versao

- Recalibrar qualquer decisao do modelo.
- Criar nova pagina dedicada.
- Persistir parametros completos de cada execucao.
- Fazer backtest causal de mudancas de parametro.
- Comparar performance realizada futura contra cada recomendacao.

Esses itens podem virar fases futuras, mas o primeiro ganho deve ser visibilidade historica
simples, confiavel e integrada a pagina Modelo.
