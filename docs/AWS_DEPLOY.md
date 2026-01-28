# PortfolioESG - Infraestrutura AWS + GitHub

Este documento descreve como hospedar o PortfolioESG na AWS com deploy automático via GitHub Actions.

## Arquitetura

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   GitHub    │────▶│   GitHub    │────▶│    AWS S3   │
│  Repository │     │   Actions   │     │   (Static)  │
└─────────────┘     └─────────────┘     └─────────────┘
                                               │
                                               ▼
                                        ┌─────────────┐
                                        │ CloudFront  │
                                        │    (CDN)    │
                                        └─────────────┘
                                               │
                                               ▼
                                        ┌─────────────┐
                                        │   Usuário   │
                                        └─────────────┘
```

## Pré-requisitos

1. Conta AWS
2. Conta GitHub
3. AWS CLI instalado (`brew install awscli`)
4. Domínio próprio (opcional, mas recomendado)

---

## Parte 1: Configuração AWS

### 1.1 Criar Bucket S3

```bash
# Defina variáveis
BUCKET_NAME="portfolioesg-app"
REGION="sa-east-1"  # São Paulo

# Criar bucket
aws s3 mb s3://$BUCKET_NAME --region $REGION

# Configurar para website estático
aws s3 website s3://$BUCKET_NAME --index-document index.html --error-document index.html
```

### 1.2 Criar Policy do Bucket

Crie um arquivo `bucket-policy.json`:
```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "PublicReadGetObject",
            "Effect": "Allow",
            "Principal": "*",
            "Action": "s3:GetObject",
            "Resource": "arn:aws:s3:::portfolioesg-app/*"
        }
    ]
}
```

Aplique a policy:
```bash
aws s3api put-bucket-policy --bucket $BUCKET_NAME --policy file://bucket-policy.json
```

### 1.3 Criar Distribuição CloudFront (Recomendado)

```bash
# Criar distribuição (via console é mais fácil)
# Vá em: AWS Console > CloudFront > Create Distribution
# Origin: portfolioesg-app.s3-website-sa-east-1.amazonaws.com
# Viewer Protocol Policy: Redirect HTTP to HTTPS
```

### 1.4 Criar Usuário IAM para Deploy

```bash
# Criar usuário
aws iam create-user --user-name github-actions-deploy

# Criar policy de deploy
cat > deploy-policy.json << 'EOF'
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "s3:PutObject",
                "s3:GetObject",
                "s3:DeleteObject",
                "s3:ListBucket"
            ],
            "Resource": [
                "arn:aws:s3:::portfolioesg-app",
                "arn:aws:s3:::portfolioesg-app/*"
            ]
        },
        {
            "Effect": "Allow",
            "Action": [
                "cloudfront:CreateInvalidation"
            ],
            "Resource": "*"
        }
    ]
}
EOF

# Anexar policy
aws iam put-user-policy --user-name github-actions-deploy --policy-name S3DeployPolicy --policy-document file://deploy-policy.json

# Criar access keys
aws iam create-access-key --user-name github-actions-deploy
# GUARDE O OUTPUT! Você precisará do AccessKeyId e SecretAccessKey
```

---

## Parte 2: Configuração GitHub

### 2.1 Inicializar Repositório

```bash
cd /Users/gabrielcampos/PortfolioESG
git init
git add .
git commit -m "Initial commit"
```

### 2.2 Criar Repositório no GitHub

1. Vá em https://github.com/new
2. Nome: `PortfolioESG`
3. Privado (recomendado)
4. NÃO inicialize com README

```bash
git remote add origin https://github.com/SEU_USUARIO/PortfolioESG.git
git branch -M main
git push -u origin main
```

### 2.3 Configurar Secrets no GitHub

1. Vá em: Repository > Settings > Secrets and variables > Actions
2. Adicione os seguintes secrets:

| Nome | Valor |
|------|-------|
| `AWS_ACCESS_KEY_ID` | Access Key do usuário IAM |
| `AWS_SECRET_ACCESS_KEY` | Secret Key do usuário IAM |
| `AWS_REGION` | `sa-east-1` |
| `S3_BUCKET` | `portfolioesg-app` |
| `CLOUDFRONT_DISTRIBUTION_ID` | ID da distribuição (opcional) |

---

## Parte 3: GitHub Actions (CI/CD)

O workflow em `.github/workflows/deploy.yml` fará:
1. Detectar push na branch `main`
2. Sincronizar pasta `html/` com S3
3. Invalidar cache do CloudFront

---

## Parte 4: Fluxo de Desenvolvimento

### Workflow diário:

```bash
# 1. Fazer alterações localmente
# ... edite arquivos ...

# 2. Testar localmente
cd html && python -m http.server 8000

# 3. Commit e push
git add .
git commit -m "Descrição da mudança"
git push

# 4. GitHub Actions faz deploy automático! 🚀
```

### Verificar status do deploy:
- Vá em: Repository > Actions
- Veja o status do workflow

---

## Parte 5: Domínio Personalizado (Opcional)

### Com Route 53:
1. Registre domínio em Route 53
2. Crie certificado SSL no ACM (us-east-1 para CloudFront)
3. Configure Alternate Domain no CloudFront
4. Crie registro A/AAAA apontando para CloudFront

### Com domínio externo:
1. Crie CNAME apontando para URL do CloudFront

---

## Custos Estimados (USD/mês)

| Serviço | Custo |
|---------|-------|
| S3 (< 1GB) | ~$0.02 |
| CloudFront (< 10GB transfer) | ~$0.85 |
| Route 53 (opcional) | ~$0.50 |
| **Total** | **~$1-2/mês** |

---

## Segurança Adicional

### Proteger dados sensíveis:
Os arquivos JSON com dados financeiros ficam públicos no S3. Para maior segurança:

1. **Opção simples**: Não faça commit dos dados, gere-os localmente
2. **Opção média**: Use S3 presigned URLs com Lambda
3. **Opção avançada**: Migre dados para Firestore com regras de segurança

### .gitignore recomendado:
```
# Dados sensíveis
html/data/*.json
html/data/*.csv
data/

# Python
__pycache__/
*.pyc
.venv/

# Logs
logs/
*.log

# OS
.DS_Store
```

---

## Troubleshooting

### "Access Denied" no S3
- Verifique a bucket policy
- Verifique se o bucket permite acesso público

### Deploy falha no GitHub Actions
- Verifique os secrets configurados
- Verifique as permissões do usuário IAM

### Site não atualiza após deploy
- CloudFront tem cache, aguarde ou crie invalidation
- Limpe cache do navegador (Cmd+Shift+R)
