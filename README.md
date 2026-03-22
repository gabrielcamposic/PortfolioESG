# 📊 PortfolioESG

Sistema de análise e otimização de portfólio de ações brasileiras com foco em critérios ESG (Environmental, Social, Governance) e rentabilidade.

> This is a personal project to find out whether it makes sense to use stocks to incentivize actual ESG oriented companies. I'm trying to figure out a way to achieve balance between great publicly available ESG metrics and profitability.

## 🎯 Funcionalidades

- **Download automático** de dados financeiros via Yahoo Finance
- **Scoring ESG** combinando métricas ambientais, sociais e de governança
- **Otimização de portfólio** usando algoritmo genético (GA)
- **Dashboard interativo** para visualização de resultados
- **Tracking de investimentos reais** via notas de negociação
- **Análise de rebalanceamento** com cálculo de custos de transação e comparação explícita entre modelo e carteira atual
- **Autenticação Google** para acesso seguro

## 📚 Documentação técnica (docs/)

| Arquivo | Descrição | Status |
|---------|-----------|--------|
| [METRICS_REFERENCE.md](docs/METRICS_REFERENCE.md) | Fórmulas, fontes e exemplos de cada métrica das páginas `1_portfolio.html` e `2_risk.html` | ✅ Completo |
| [BROKER_RETURN_PLAN.md](docs/BROKER_RETURN_PLAN.md) | Diagnóstico e implementação do MWR / Modified Dietz (paridade com retorno da corretora) | ✅ Completo |
| [MODEL_DECISION_CLARITY.md](docs/MODEL_DECISION_CLARITY.md) | Diagnóstico e implementação das melhorias de clareza da página `3_model.html` (decisão HOLD/REBALANCE) | ✅ Steps 1–4 · 🔲 Step 5 |

## 🏗️ Arquitetura

```
PortfolioESG/
├── engines/               # Scripts Python de análise
│   ├── A1_Download.py    # Download de dados
│   ├── A2_Scoring.py     # Scoring ESG e financeiro
│   ├── A3_Portfolio.py   # Otimização via GA
│   ├── A4_Analysis.py    # Análise e geração de relatórios
│   ├── B1_*.py           # Processamento de notas de negociação
│   └── requirements.txt
├── html/                  # Frontend estático
│   ├── css/
│   ├── js/
│   │   ├── auth.js       # Autenticação Google (Firebase)
│   │   └── *.js
│   ├── data/             # Dados JSON (gerados)
│   └── *.html
├── parameters/            # Configurações
├── data/                  # Dados processados
├── docs/                  # Documentação
└── .github/workflows/     # CI/CD
```

## 🚀 Quick Start

### 1. Clone e configure

```bash
git clone https://github.com/SEU_USUARIO/PortfolioESG.git
cd PortfolioESG

# Crie ambiente virtual
python -m venv .venv
source .venv/bin/activate  # macOS/Linux

# Instale dependências
pip install -r engines/requirements.txt
```

### 2. Execute a análise

```bash
cd engines
./A_Portfolio.sh
```

### 3. Visualize os resultados

```bash
cd ../html
python -m http.server 8000
# Acesse http://localhost:8000/latest_run_summary.html
```

## 📦 Deploy na AWS

Veja [docs/AWS_DEPLOY.md](docs/AWS_DEPLOY.md) para instruções completas.

### Resumo:
1. Configure bucket S3 + CloudFront
2. Configure secrets no GitHub
3. Push para `main` - deploy automático!

## 🔐 Autenticação

O sistema usa Firebase Authentication com Google OAuth. Veja [docs/SETUP_AUTH.md](docs/SETUP_AUTH.md).

## 📊 Workflows GitHub Actions

| Workflow | Trigger | Descrição |
|----------|---------|-----------|
| `deploy.yml` | Push em `main` | Deploy do frontend para S3 |
| `run-analysis.yml` | Manual / Cron | Executa análise de portfólio |

## 🛠️ Desenvolvimento

```bash
# Fazer alterações
git checkout -b feature/nova-funcionalidade

# Commit
git add .
git commit -m "feat: descrição"

# Push e PR
git push origin feature/nova-funcionalidade
```

## 📈 Métricas Calculadas

- **Sharpe Ratio** - Retorno ajustado ao risco
- **Retorno Anual** - Performance projetada
- **Volatilidade** - Risco do portfólio
- **HHI** - Índice de concentração
- **Forward P/E** - Valuation das ações
- **Momentum** - Tendência de preços

---

## 📚 Documentação dos Scripts

### A1_Download.py - Download de Dados Financeiros

**Propósito:** Baixar dados financeiros e métricas de ações do Yahoo Finance, consolidando em bases de dados locais para uso nos scripts subsequentes.

#### Funcionalidades

| Funcionalidade | Descrição |
|----------------|-----------|
| Download de preços | Obtém histórico de preços (10 anos) via yfinance |
| Métricas financeiras | Forward P/E, Forward EPS, Target Price, Beta |
| Calendário de feriados | Gera calendário B3 para validação de dias úteis |
| Skip List | Gerencia ações descontinuadas ou indisponíveis |
| Consolidação | Salva dados em FinancialsDB.csv e PricesDB.csv |
| Modo direto | Alternativa ao download que consolida dados locais |

#### Arquivos de Entrada

| Arquivo | Localização | Descrição |
|---------|-------------|-----------|
| `tickers.txt` | `parameters/` | Lista de ações a processar (Ticker,Name,Sector,Industry,BrokerName) |
| `benchmarks.txt` | `parameters/` | Benchmarks para comparação (IBOV, IFIX, etc.) |
| `download_parameters.json` | `parameters/` | Configurações de download e consolidação |
| `paths.json` | `parameters/` | Caminhos de diretórios do projeto |

#### Arquivos de Saída

| Arquivo | Localização | Descrição |
|---------|-------------|-----------|
| `FinancialsDB.csv` | `data/findb/` | Métricas consolidadas de todas as ações |
| `PricesDB.csv` | `data/findb/` | Preços históricos consolidados |
| `skip_list.json` | `data/findb/` | Ações a ignorar (descontinuadas/inválidas) |
| `download.log` | `logs/` | Log detalhado da execução |

#### Parâmetros de Configuração (downpar.txt)

| Parâmetro | Valor | Descrição |
|-----------|-------|-----------|
| `storage_mode` | `direct` | "direct" ou "legacy" |
| `history_years` | `10` | Anos de histórico a baixar |
| `debug_mode` | `false` | Ativar logs detalhados |
| `dynamic_user_agents_enabled` | `true` | Rotacionar user agents |

#### Modos de Execução

| Modo | Comando | Descrição |
|------|---------|-----------|
| Direto | `--direct` ou config | Consolida dados sem download (mais rápido) |
| Full | `--full` ou config | Download completo de todas as ações |
| Skip download | `--skip-download` | Pula o download, usa dados existentes |

#### Fluxo de Execução

```
1. Carrega configurações (paths.json, download_parameters.json)
2. Carrega lista de tickers (tickers.txt + benchmarks.txt)
3. Carrega skip list existente
4. Gera calendário de feriados B3
5. Para cada ticker:
   a. Verifica se está na skip list permanente → pula
   b. Baixa dados do Yahoo Finance (com retry)
   c. Valida dados (histórico mínimo, métricas disponíveis)
   d. Se falha consistente → adiciona à skip list
   e. Salva métricas no acumulador
6. Consolida dados em FinancialsDB.csv e PricesDB.csv
7. Atualiza skip_list.json
8. Gera relatório de execução
```

#### Skip List - Critérios

| Tipo | Critério | Ação |
|------|----------|------|
| Temporário | Falha em 1-29 dias consecutivos | Tenta novamente na próxima execução |
| Permanente | Falha em 30+ dias consecutivos | Ignora definitivamente |
| Manual | Adicionado manualmente | Ignora até remoção manual |

#### Exemplo de Uso

```bash
# Via shell script (recomendado)
cd engines
./A_Portfolio.sh

# Direto (para debug)
python A1_Download.py --direct

# Com logs detalhados
python A1_Download.py --direct --debug
```

#### Métricas Coletadas por Ação

| Métrica | Campo | Descrição |
|---------|-------|-----------|
| Forward P/E | `forwardPE` | P/E baseado em lucros projetados |
| Forward EPS | `forwardEps` | Lucro por ação projetado |
| Target Price | `targetMeanPrice` | Preço-alvo médio dos analistas |
| Beta | `beta` | Sensibilidade ao mercado |
| Market Cap | `marketCap` | Capitalização de mercado |
| Setor | `sector` | Setor da empresa |
| Indústria | `industry` | Indústria específica |

#### Tratamento de Erros

- **HTTP 404**: Ação não encontrada → adiciona à skip list
- **Timeout**: Retry com backoff exponencial
- **Dados insuficientes**: Marca como skip temporário
- **Rate limiting**: Delay automático entre requests

---

### A2_Scoring.py - Scoring e Ranqueamento de Ações

**Propósito:** Calcular scores compostos para cada ação combinando Sharpe Ratio, Upside Potential e Momentum, com pesos dinâmicos ajustados por perfil de risco e regime de mercado.

#### Funcionalidades

| Funcionalidade | Descrição |
|----------------|-----------|
| Sharpe Ratio | Calcula retorno ajustado ao risco para cada ação |
| Upside Potential | Usa targetMeanPrice do Yahoo (fallback: SectorMedianPE) |
| Momentum | Retorno nos últimos N dias (parametrizável) |
| Dynamic Weighting | Pesos baseados em variância das métricas |
| Risk Profile | Ajusta pesos conforme perfil (conservador/moderado/agressivo) |
| Market Regime | Detecta bull/bear market e ajusta estratégia |
| Correlation Matrix | Calcula correlação entre top 20 ações |

#### Arquivos de Entrada

| Arquivo | Localização | Descrição |
|---------|-------------|-----------|
| `PricesDB.csv` | `data/findb/` | Preços históricos consolidados |
| `FinancialsDB.csv` | `data/findb/` | Métricas financeiras (P/E, EPS, targetMeanPrice) |
| `tickers.txt` | `parameters/` | Lista de ações com setores |
| `skipped_tickers.json` | `data/findb/` | Ações a ignorar |
| `scorpar.txt` | `parameters/` | Parâmetros de scoring |
| `risk_profile.txt` | `parameters/` | Configuração de perfil de risco |

#### Arquivos de Saída

| Arquivo | Localização | Descrição |
|---------|-------------|-----------|
| `scored_stocks.csv` | `data/results/` | Histórico de scores (append) |
| `sector_pe.csv` | `data/results/` | P/E mediano por setor |
| `correlation_matrix.csv` | `data/results/` | Matriz de correlação top 20 |
| `scoring.log` | `logs/` | Log detalhado da execução |

#### Cálculo do Composite Score

```
CompositeScore = SharpeNorm × W_sharpe + UpsideNorm × W_upside + MomentumNorm × W_momentum
```

Onde os pesos (W) são calculados dinamicamente:
1. **Base**: Proporcional à variância de cada métrica normalizada
2. **Perfil**: Ajustados conforme tendências do perfil de risco
3. **Regime**: Modulados pelo regime de mercado atual

#### Cálculo do Upside Potential

| Método | Condição | Fórmula |
|--------|----------|---------|
| Yahoo Finance | `targetMeanPrice` disponível | `(targetMeanPrice / CurrentPrice) - 1` |
| Sector P/E (fallback) | Sem target price | `(SectorMedianPE / forwardPE) - 1` |

#### Detecção de Regime de Mercado

| Regime | Condição | Efeito no Perfil |
|--------|----------|------------------|
| `strong_bull` | trend > 20% E vol < 70th percentile | Mais conservador (×1.5) |
| `bull` | trend > 5% | Levemente conservador (×1.2) |
| `neutral` | -5% < trend < 5% | Sem ajuste (×1.0) |
| `bear` | trend < -5% | Mais dinâmico (×0.8) |
| `strong_bear` | trend < -20% OU vol > 85th percentile | Muito dinâmico (×0.6) |

Os thresholds são parametrizáveis em `risk_profile.txt`.

#### Filtros Aplicados

Ações são excluídas do output se:
- Upside Potential ≤ 0 (sem potencial de valorização)
- CurrentPrice ou TargetPrice inválidos
- forwardPE = 0 ou ausente
- Ticker na skip list permanente

#### Exemplo de Uso

```bash
# Via pipeline (recomendado)
cd engines
./A_Portfolio.sh

# Direto (para debug)
python A2_Scoring.py
```

---

### A3_Portfolio.py - Otimização de Portfólio

**Propósito:** Encontrar a melhor combinação de ações usando Algoritmo Genético (para portfólios grandes) ou Brute-Force (para portfólios pequenos), otimizando pelo Sharpe Ratio.

#### Funcionalidades

| Funcionalidade | Descrição |
|----------------|-----------|
| Brute-Force | Avalia todas combinações para k ≤ threshold (padrão: 4) |
| Algoritmo Genético | Otimização evolucionária para k > threshold |
| Diversificação por Setor | Limita ações por setor (configurável) |
| Convergência Adaptativa | Para simulações quando Sharpe estabiliza |
| Fase de Refinamento | Re-otimiza top portfólios do brute-force |
| Métricas para Frontend | HHI, sector exposure, sparklines |

#### Arquivos de Entrada

| Arquivo | Localização | Descrição |
|---------|-------------|-----------|
| `scored_stocks.csv` | `data/results/` | Ações ranqueadas pelo A2_Scoring |
| `StockDataDB.csv` | `data/findb/` | Preços históricos consolidados |
| `FinancialsDB.csv` | `data/findb/` | Métricas financeiras |
| `portpar.txt` | `parameters/` | Parâmetros de otimização |

#### Arquivos de Saída

| Arquivo | Localização | Descrição |
|---------|-------------|-----------|
| `portfolio_results_db.csv` | `data/results/` | Histórico de portfólios (append) |
| `ga_fitness_noise_db.csv` | `data/results/` | Histórico de fitness do GA |
| `latest_run_summary.json` | `html/data/` | Resultado para frontend |
| `portfolio.log` | `logs/` | Log detalhado |

#### Algoritmo de Otimização

**Sharpe Ratio Maximization:**
```
Sharpe = (Retorno_Esperado - Taxa_Livre_Risco) / Volatilidade
```

**Brute-Force (k ≤ heuristic_threshold_k):**
1. Gera todas combinações de k ações
2. Filtra por diversificação setorial
3. Simula N pesos aleatórios por combinação
4. Seleciona melhor Sharpe

**Algoritmo Genético (k > heuristic_threshold_k):**
1. População inicial: combinações aleatórias
2. Fitness: Sharpe Ratio do portfólio
3. Seleção: Tournament selection
4. Crossover: Single-point com reparo
5. Mutação: Troca aleatória de ação
6. Elitismo: Top N sobrevive
7. Convergência: Para se Sharpe estabilizar

#### Parâmetros Principais (portpar.txt)

| Parâmetro | Default | Descrição |
|-----------|---------|-----------|
| `min_stocks` | 5 | Mínimo de ações no portfólio |
| `max_stocks` | 20 | Máximo de ações no portfólio |
| `heuristic_threshold_k` | 4 | Limite para usar brute-force |
| `ga_population_size` | 60 | Tamanho da população do GA |
| `ga_num_generations` | 40 | Gerações máximas do GA |
| `max_stocks_per_sector` | 4 | Diversificação setorial |

#### Exemplo de Uso

```bash
# Via pipeline C (recomendado)
cd engines
./C_OptimizedPortfolio.sh

# Direto (para debug)
python C_OptimizedPortfolio.py
```

---

### D_Publish.py - Geração do Dashboard JSON

**Propósito:** Consolidar todos os resultados parciais (A, B, C) num único arquivo `dashboard_latest.json` consumido pelo frontend.  É o ponto central onde os campos expostos na UI são calculados e nomeados.

#### Funcionalidades

| Funcionalidade | Descrição |
|----------------|-----------|
| Seção `model` | Agrega retornos, risco, decisão, valuation e composição do portfólio modelo |
| Seção `real` | Métricas TWR reais calculadas a partir de `portfolio_history.csv` + `ledger.csv` |
| Campos `returns` | Calcula `hold_12m`, `gross_12m`, `net_12m`, `excess_net_12m` com fórmulas documentadas |
| Decisão espelhada | Replica HOLD/REBALANCE a partir de `optimized_recommendation.json` |

#### Campos `model.returns` (dashboard_latest.json)

| Campo | Fórmula | Descrição |
|-------|---------|-----------|
| `hold_12m` | Σ(w_i × target_i/current_i − 1) | Retorno esperado da **carteira atual** |
| `gross_12m` | Σ(w_i × target_i/current_i − 1) | Retorno esperado do **modelo** (bruto) |
| `net_12m` | `gross_12m − transition_cost_pct` | Retorno do modelo já líquido do custo de transição |
| `excess_net_12m` | `net_12m − hold_12m` | Excesso do modelo sobre a carteira atual (> 0 → REBALANCE) |

> ⚠️ `excess_net_12m` é excesso sobre a **carteira atual**, não sobre índice de mercado.
> Não nomear como "vs benchmark" na UI.

#### Arquivos de Saída

| Arquivo | Localização | Descrição |
|---------|-------------|-----------|
| `dashboard_latest.json` | `html/data/` | JSON unificado para o frontend |

---

## 📄 Licença

Projeto pessoal - uso privado.

#### Funcionalidades

| Funcionalidade | Descrição |
|----------------|-----------|
| Brinson-Fachler Attribution | Decompõe retorno ativo em allocation, selection e interaction |
| Tracking Error | Volatilidade dos retornos excedentes vs benchmark |
| Information Ratio | Retorno excedente ajustado por tracking error |
| Momentum Signal | Média ponderada de momentum 3m/6m/12m |
| Turnover | Mudança de pesos entre execuções |
| Liquidity Score | Relação volume/peso para liquidez |

#### Arquivos de Entrada

| Arquivo | Localização | Descrição |
|---------|-------------|-----------|
| `portfolio_results_db.csv` | `data/results/` | Histórico de portfólios |
| `StockDataDB.csv` | `data/findb/` | Preços históricos |
| `FinancialsDB.csv` | `data/findb/` | Métricas financeiras |
| `scored_stocks.csv` | `data/results/` | Ações ranqueadas (para setores) |
| `anapar.txt` | `parameters/` | Parâmetros de análise |

#### Arquivos de Saída

| Arquivo | Localização | Descrição |
|---------|-------------|-----------|
| `portfolio_timeseries.csv` | `data/findb/` e `html/data/` | Série temporal completa |
| `performance_attribution.json` | `html/data/` | Atribuição Brinson-Fachler |
| `portfolio_diagnostics.json` | `html/data/` | Métricas de diagnóstico |
| `analysis.log` | `logs/` | Log detalhado |

#### Modelo Brinson-Fachler

Decompõe o retorno ativo (α) em três efeitos:

| Efeito | Fórmula | Descrição |
|--------|---------|-----------|
| **Allocation** | `(Wp - Wb) × (Rb - R_total)` | Contribuição de sob/sobre-pesar setores |
| **Selection** | `Wb × (Rp - Rb)` | Contribuição de escolher ações melhores dentro do setor |
| **Interaction** | `(Wp - Wb) × (Rp - Rb)` | Efeito combinado allocation + selection |

Onde:
- `Wp` = Peso do portfólio no setor
- `Wb` = Peso do benchmark no setor
- `Rp` = Retorno do portfólio no setor
- `Rb` = Retorno do benchmark no setor

#### Exemplo de Uso

```bash
# Via pipeline (recomendado)
cd engines
./A_Portfolio.sh

# Direto (para debug)
python A4_Analysis.py
```

---

### B1_Process_Notes.py - Processamento de Notas de Negociação

**Propósito:** Processar PDFs de notas de negociação da corretora, extraindo transações (compras/vendas) e taxas, e reconstruir o ledger de posições.

#### Funcionalidades

| Funcionalidade | Descrição |
|----------------|-----------|
| Extração de PDF | Usa pdfplumber para extrair texto, com fallback OCR |
| Parsing de notas | Interpreta formato padrão de notas de negociação brasileiras |
| Mapeamento de símbolos | Associa nomes da corretora aos tickers do Yahoo Finance |
| Idempotência | Evita reprocessar documentos já importados |
| Reconstrução do ledger | Calcula posições líquidas a partir de transações |
| Alocação de taxas | Distribui taxas proporcionalmente entre transações |

#### Arquivos de Entrada

| Arquivo | Localização | Descrição |
|---------|-------------|-----------|
| `*.pdf` | `Notas_Negociação/` | PDFs das notas de negociação |
| `tickers.txt` | `parameters/` | Mapeamento ticker ↔ nome na corretora |
| `processed_notes.json` | `html/data/` | Manifest de arquivos já processados |
| `paths.txt` | `parameters/` | Configurações de caminhos |

#### Arquivos de Saída

| Arquivo | Localização | Descrição |
|---------|-------------|-----------|
| `transactions_parsed.csv` | `data/` | Todas as transações extraídas |
| `fees_parsed.csv` | `data/` | Taxas e emolumentos |
| `ledger.csv` | `data/` | Posições líquidas calculadas |
| `processed_notes.json` | `html/data/` | Manifest atualizado |
| `process_notes.log` | `logs/` | Log detalhado da execução |

#### Fluxo de Execução

```
1. Carrega configurações (paths.txt)
2. Lista PDFs em Notas_Negociação/
3. Carrega manifest de arquivos processados
4. Para cada PDF não processado:
   a. Extrai texto (pdfplumber ou OCR)
   b. Faz parsing da nota (datas, transações, taxas)
   c. Valida dados extraídos
   d. Verifica se broker_document já existe → pula
   e. Mapeia nomes de ações para símbolos
   f. Salva em transactions_parsed.csv e fees_parsed.csv
   g. Marca como processado
5. Atualiza tickers.txt com novos BrokerNames
6. Salva manifest
7. Reconstrói ledger (posições líquidas)
8. Gera resumo (total investido, custo de implementação)
```

#### Formato da Nota de Negociação

O parser espera o formato padrão brasileiro com:
- Data do pregão e data de liquidação
- Número do documento (broker_document)
- Tabela de negócios: C/V, Ticker, Quantidade, Preço, Valor
- Resumo de taxas: emolumentos, liquidação, etc.

#### Mapeamento de Símbolos

O script mantém mapeamento bidirecional:
- **Name** (Yahoo Finance): "Petrobrás S.A."
- **BrokerName** (Corretora): "PETROBRAS ON NM"
- **Ticker**: "PETR3.SA"

Quando encontra um novo BrokerName, atualiza automaticamente `tickers.txt`.

#### Exemplo de Uso

```bash
# Via pipeline B (recomendado)
cd engines
./B_Ledger.sh

# Direto (para debug)
python B1_Process_Notes.py
```

---

### B2_Consolidate_Ledger.py - Consolidação de Posições

**Propósito:** Ler o ledger de transações e agregar por ticker para gerar posições líquidas atuais.

#### Funcionalidades

| Funcionalidade | Descrição |
|----------------|-----------|
| Agregação de transações | Consolida compras e vendas por ticker |
| Mapeamento de símbolos | Associa nomes do ledger a símbolos do Yahoo Finance |
| Enriquecimento | Adiciona preço atual e target price às posições |
| Filtragem | Remove posições com quantidade zero ou negativa |

#### Arquivos de Entrada

| Arquivo | Localização | Descrição |
|---------|-------------|-----------|
| `ledger.csv` | `data/` | Transações processadas pelo B1 |
| `tickers.txt` | `parameters/` | Mapeamento de símbolos |
| `scored_stocks.csv` | `data/results/` | Target prices do último scoring |
| `StockDataDB.csv` | `data/findb/` | Preços atuais |

#### Arquivos de Saída

| Arquivo | Localização | Descrição |
|---------|-------------|-----------|
| `ledger_positions.json` | `html/data/` | Posições consolidadas para o frontend |

---

### B3_Generate_json.py - Geração de JSONs para Frontend

**Propósito:** Gerar arquivos JSON consumidos pelo frontend (meu_portfolio.html).

#### Arquivos de Saída

| Arquivo | Localização | Descrição |
|---------|-------------|-----------|
| `ledger_positions.json` | `html/data/` | Posições com quantidades e valores |
| `pipeline_latest.json` | `html/data/` | Último portfolio recomendado com pesos |
| `scored_targets.json` | `html/data/` | Mapa de target prices por ticker |
| `ledger.csv` | `html/data/` | Cópia do ledger para acesso web |

---

### B4_Portfolio_History.py - Histórico de Valor do Portfolio

**Propósito:** Gerar série temporal de valor do portfolio implementado para visualização.

#### Funcionalidades

| Funcionalidade | Descrição |
|----------------|-----------|
| Cálculo de posições diárias | Rastreia holdings ao longo do tempo |
| Valoração a mercado | Multiplica posições por preços de fechamento |
| Preenchimento de gaps | Interpola valores em dias sem negociação |

#### Arquivos de Saída

| Arquivo | Localização | Descrição |
|---------|-------------|-----------|
| `portfolio_history.json` | `html/data/` | Série temporal para gráfico de patrimônio |

---

### C_OptimizedPortfolio.py - Otimização com Custos de Transação

**Propósito:** Combinar o portfolio ideal (de A) com holdings atuais (de B) para gerar uma recomendação de transição que maximiza retorno considerando custos de transação.

> 📄 Veja [docs/MODEL_DECISION_CLARITY.md](docs/MODEL_DECISION_CLARITY.md) para o diagnóstico completo da lógica de decisão, fórmulas e a melhoria futura pendente (Step 5 — score-gap clause).

#### Funcionalidades

| Funcionalidade | Descrição |
|----------------|-----------|
| Análise de custos | Calcula custo médio de transação do histórico |
| Geração de candidatos | Cria portfólios de transição (blends entre ideal e atual) |
| Score composto | Avalia candidatos por retorno esperado, Sharpe e momentum |
| Recomendação | REBALANCE se retorno excedente > threshold, senão HOLD |
| Histórico de decisões | Registra cada recomendação para análise |

#### Arquivos de Entrada

| Arquivo | Localização | Descrição |
|---------|-------------|-----------|
| `latest_run_summary.json` | `html/data/` | Portfolio ideal do último A_Portfolio.sh |
| `ledger_positions.json` | `html/data/` | Holdings atuais do último B_Ledger.sh |
| `ledger.csv` | `data/` | Histórico de transações para cálculo de custos |
| `optpar.txt` | `parameters/` | Parâmetros de otimização |

#### Arquivos de Saída

| Arquivo | Localização | Descrição |
|---------|-------------|-----------|
| `optimized_recommendation.json` | `html/data/` | Última recomendação |
| `optimized_portfolio_history.csv` | `data/results/` | Histórico de decisões |
| `optimized_*.log` | `logs/` | Log detalhado |

#### Parâmetros (optpar.txt)

| Parâmetro | Default | Descrição |
|-----------|---------|-----------|
| `WEIGHT_EXPECTED_RETURN` | 0.4 | Peso do retorno esperado no score composto |
| `WEIGHT_SHARPE_RATIO` | 0.4 | Peso do Sharpe no score composto |
| `WEIGHT_MOMENTUM` | 0.2 | Peso do momentum no score composto |
| `MIN_EXCESS_RETURN_THRESHOLD` | 0.5 | Mínimo de retorno excedente para REBALANCE (pp) |
| `TRANSACTION_COST_MODE` | DYNAMIC | DYNAMIC ou FIXED |
| `TRANSACTION_COST_FIXED_PCT` | 0.1 | Custo fixo se mode=FIXED (%) |

#### Fórmula de Decisão

```
excess_return = optimal_net_return − holdings_return

  holdings_return    = retorno esperado da carteira atual (target_price/current_price − 1,
                       ponderado pelos pesos atuais).
                       → Exposto em dashboard_latest.json como model.returns.hold_12m

  optimal_net_return = retorno esperado do modelo, já líquido do custo único de transição.
                       → Exposto como model.returns.net_12m

  excess_return      = quanto a mais (%) o modelo entrega vs. manter a carteira atual.
                       Positivo → modelo ganha → REBALANCE
                       Negativo → carteira atual ganha → HOLD
                       → Exposto como model.returns.excess_net_12m

⚠️  excess_return é excesso sobre a CARTEIRA ATUAL, não sobre índice de mercado externo.
```

Se `excess_return ≥ MIN_EXCESS_RETURN_THRESHOLD` → **REBALANCE**; caso contrário → **HOLD**.

#### Fluxo de Decisão

```
1. Carrega portfolio ideal (A) e holdings atuais (B)
2. Calcula retorno esperado de holdings via target prices (→ hold_12m)
3. Calcula retorno esperado do modelo via target prices (→ gross_12m)
4. Calcula custo de transição B → modelo (→ transition_cost_pct)
5. net_12m = gross_12m − transition_cost_pct
6. excess_return = net_12m − hold_12m
7. Se excess_return ≥ threshold → REBALANCE com transações detalhadas
   Senão → HOLD
```

#### Exemplo de Uso

```bash
# Via pipeline C (recomendado)
cd engines
./C_OptimizedPortfolio.sh

# Direto (para debug)
python C_OptimizedPortfolio.py
```


