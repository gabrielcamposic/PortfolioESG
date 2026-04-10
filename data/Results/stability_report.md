# Relatório de Estabilidade do Modelo

Data do Teste: 2026-04-10 00:42:05
Número de Execuções: 10

## 1. Estatísticas de Performance

| Métrica | Média | Desvio Padrão | CV (%) | Min | Max |
| :--- | :---: | :---: | :---: | :---: | :---: |
| Sharpe Ratio | 3.8793 | 0.0104 | 0.27% | 3.8625 | 3.8959 |
| Retorno Esperado (12m %) | 84.8850 | 0.9883 | 1.16% | 83.6900 | 87.0800 |
| Retorno Histórico (12m %) | 131.2393 | 2.7270 | 2.08% | 127.3708 | 134.7576 |
| Volatilidade (%) | 18.0800 | 0.2735 | 1.51% | 17.7600 | 18.7000 |
| Score Agregado | 0.5246 | 0.0026 | 0.50% | 0.5201 | 0.5292 |
| Componente Sharpe | 0.7641 | 0.0062 | 0.82% | 0.7539 | 0.7726 |
| Componente Upside | 0.0935 | 0.0006 | 0.65% | 0.0924 | 0.0944 |
| Componente Momentum | 0.5671 | 0.0036 | 0.63% | 0.5619 | 0.5739 |

> [!TIP]
> Um Coeficiente de Variação (CV) abaixo de 5% indica alta estabilidade. Acima de 10% sugere que o modelo pode precisar de mais iterações para convergir.

## 2. Estabilidade da Composição

| Ativo | Frequência (%) | Peso Médio | Desvio Peso | CV Peso (%) |
| :--- | :---: | :---: | :---: | :---: |
| PETR4.SA | 100.0% | 0.2089 | 0.0176 | 8.43% |
| VALE3.SA | 100.0% | 0.0905 | 0.0187 | 20.70% |
| AURA33.SA | 100.0% | 0.1741 | 0.0065 | 3.71% |
| PNVL3.SA | 100.0% | 0.1033 | 0.0221 | 21.41% |
| PRIO3.SA | 100.0% | 0.1470 | 0.0163 | 11.07% |
| ENEV3.SA | 100.0% | 0.1457 | 0.0152 | 10.43% |
| AXIA6.SA | 100.0% | 0.0932 | 0.0229 | 24.62% |
| DASA3.SA | 80.0% | 0.0231 | 0.0048 | 20.90% |
| RADL3.SA | 40.0% | 0.0303 | 0.0102 | 33.49% |
| UGPA3.SA | 10.0% | 0.0065 | 0.0000 | 0.00% |
| PETR3.SA | 10.0% | 0.0593 | 0.0000 | 0.00% |
| ABCB4.SA | 10.0% | 0.0016 | 0.0000 | 0.00% |

## 3. Conclusão e Recomendações

O modelo apresenta **alta estabilidade**. Os resultados são consistentes e convergem para um ótimo global claro.
