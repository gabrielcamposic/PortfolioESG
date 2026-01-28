# Configuração de Autenticação Google (Firebase)

Este documento explica como configurar a autenticação via Google para o PortfolioESG.

## 1. Criar Projeto no Firebase

1. Acesse [Firebase Console](https://console.firebase.google.com/)
2. Clique em **"Adicionar projeto"**
3. Digite um nome (ex: "PortfolioESG")
4. Desative Google Analytics (opcional para este caso)
5. Clique em **"Criar projeto"**

## 2. Ativar Autenticação Google

1. No menu lateral, vá em **"Build" > "Authentication"**
2. Clique em **"Começar"** ou **"Get started"**
3. Na aba **"Sign-in method"**, clique em **"Google"**
4. Ative o toggle **"Ativar"**
5. Configure o email de suporte (seu email)
6. Clique em **"Salvar"**

## 3. Registrar App Web

1. Na página inicial do projeto, clique no ícone **"</>"** (Web)
2. Digite um apelido (ex: "PortfolioESG Web")
3. **NÃO** ative Firebase Hosting
4. Clique em **"Registrar app"**
5. Copie as credenciais exibidas:

```javascript
const firebaseConfig = {
  apiKey: "AIza...",
  authDomain: "projeto-xyz.firebaseapp.com",
  projectId: "projeto-xyz",
  storageBucket: "projeto-xyz.appspot.com",
  messagingSenderId: "123456789",
  appId: "1:123456789:web:abc123"
};
```

## 4. Configurar auth.js

1. Abra `/html/js/auth.js`
2. Substitua `FIREBASE_CONFIG` pelas suas credenciais:

```javascript
const FIREBASE_CONFIG = {
  apiKey: "SUA_API_KEY",
  authDomain: "SEU_PROJETO.firebaseapp.com",
  projectId: "SEU_PROJETO",
  storageBucket: "SEU_PROJETO.appspot.com",
  messagingSenderId: "SEU_SENDER_ID",
  appId: "SEU_APP_ID"
};
```

## 5. Restringir Acesso por Email (Recomendado)

Para permitir apenas emails específicos, edite a lista em `auth.js`:

```javascript
const ALLOWED_EMAILS = [
  "seu.email@gmail.com",
  "outro.email@gmail.com"
];
```

Se a lista estiver vazia, qualquer pessoa com conta Google poderá acessar.

## 6. Configurar Domínios Autorizados (Para AWS)

Quando hospedar na AWS:

1. No Firebase Console, vá em **"Authentication" > "Settings"**
2. Na aba **"Authorized domains"**
3. Clique em **"Add domain"**
4. Adicione seu domínio AWS (ex: `seu-bucket.s3.amazonaws.com` ou seu domínio personalizado)

## 7. Deploy na AWS S3

### Opção A: S3 + CloudFront (Recomendado)

1. Crie um bucket S3 com nome único
2. Faça upload de todos os arquivos da pasta `/html`
3. Configure CloudFront para servir o bucket
4. Use ACM para certificado SSL gratuito
5. Adicione o domínio CloudFront aos domínios autorizados do Firebase

### Opção B: S3 Website Hosting

1. Crie um bucket S3 com nome único
2. Ative "Static website hosting"
3. Configure permissões públicas (menos seguro)
4. Adicione o endpoint ao Firebase

## Estrutura de Arquivos

```
html/
├── js/
│   ├── auth.js          # Configuração de autenticação
│   ├── latest_run_summary.js
│   └── meu_portfolio.js
├── css/
│   └── styles.css
├── data/                 # Dados gerados pelos scripts
├── latest_run_summary.html
└── meu_portfolio.html
```

## Testando Localmente

1. Inicie um servidor local:
   ```bash
   cd html
   python -m http.server 8000
   ```

2. Acesse `http://localhost:8000/latest_run_summary.html`

3. O Firebase funciona em localhost por padrão

## Segurança

### O que esta solução protege:
- ✅ Acesso não autorizado às páginas
- ✅ Autenticação segura via OAuth 2.0
- ✅ Restrição por email específico
- ✅ Sessão persistente no navegador

### O que esta solução NÃO protege:
- ❌ Acesso direto aos arquivos JSON (qualquer um com URL pode baixar)
- ❌ Proteção server-side dos dados

### Para proteção completa dos dados:
- Use S3 presigned URLs com Lambda
- Ou mova os dados para Firestore com regras de segurança
- Ou implemente um backend com autenticação

## Troubleshooting

### "Configuração Necessária"
- Verifique se preencheu FIREBASE_CONFIG corretamente
- Certifique-se que não há "YOUR_" nos valores

### "popup blocked"
- Permita popups para o domínio
- Ou use `signInWithRedirect` ao invés de `signInWithPopup`

### "unauthorized domain"
- Adicione o domínio em Firebase > Authentication > Settings > Authorized domains

### Erros de CORS
- Verifique as configurações de CORS do S3
- Use CloudFront para evitar problemas de CORS
