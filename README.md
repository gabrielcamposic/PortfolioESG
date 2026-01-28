# 📊 PortfolioESG

Sistema de análise e otimização de portfólio de ações brasileiras com foco em critérios ESG (Environmental, Social, Governance) e rentabilidade.

> This is a personal project to find out whether it makes sense to use stocks to incentivize actual ESG oriented companies. I'm trying to figure out a way to achieve balance between great publicly available ESG metrics and profitability.

## 🎯 Funcionalidades

- **Download automático** de dados financeiros via Yahoo Finance
- **Scoring ESG** combinando métricas ambientais, sociais e de governança
- **Otimização de portfólio** usando algoritmo genético (GA)
- **Dashboard interativo** para visualização de resultados
- **Tracking de investimentos reais** via notas de negociação
- **Análise de rebalanceamento** com cálculo de custos de transação
- **Autenticação Google** para acesso seguro

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

## 📄 Licença

Projeto pessoal - uso privado.

