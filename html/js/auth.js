(function() {
  'use strict';

  // ═══════════════════════════════════════════════════════════════════════════
  // FIREBASE CONFIGURATION
  // ═══════════════════════════════════════════════════════════════════════════
  //
  // As credenciais são carregadas de firebase-config.js (não versionado no Git).
  // Veja firebase-config.template.js para instruções de configuração.
  //
  // IMPORTANTE: Nunca commite credenciais no repositório!
  // ═══════════════════════════════════════════════════════════════════════════

  // Firebase configuration - carregada de arquivo externo (firebase-config.js)
  // O arquivo firebase-config.js define window.FIREBASE_CONFIG e window.ALLOWED_EMAILS
  const FIREBASE_CONFIG = window.FIREBASE_CONFIG || {
    apiKey: "NOT_CONFIGURED",
    authDomain: "NOT_CONFIGURED",
    projectId: "NOT_CONFIGURED",
    storageBucket: "NOT_CONFIGURED",
    messagingSenderId: "NOT_CONFIGURED",
    appId: "NOT_CONFIGURED",
    measurementId: "NOT_CONFIGURED"
  };


  // Lista de emails autorizados a acessar o sistema (carregada de firebase-config.js)
  const ALLOWED_EMAILS = window.ALLOWED_EMAILS || [];

  // Se a lista estiver vazia, qualquer usuário autenticado pode acessar
  // Se tiver emails, apenas esses terão acesso
  const RESTRICT_BY_EMAIL = ALLOWED_EMAILS.length > 0;

  // ═══════════════════════════════════════════════════════════════════════════
  // ESTADO GLOBAL
  // ═══════════════════════════════════════════════════════════════════════════

  let auth = null;
  let currentUser = null;
  let isInitialized = false;

  // ═══════════════════════════════════════════════════════════════════════════
  // VERIFICAÇÃO DE CONFIGURAÇÃO
  // ═══════════════════════════════════════════════════════════════════════════

  function isConfigured() {
    return FIREBASE_CONFIG.apiKey !== "YOUR_API_KEY" &&
           FIREBASE_CONFIG.projectId !== "YOUR_PROJECT_ID";
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // INICIALIZAÇÃO DO FIREBASE
  // ═══════════════════════════════════════════════════════════════════════════

  async function initializeFirebase() {
    if (isInitialized) return;

    try {
      // Carrega Firebase SDK dinamicamente
      await loadScript('https://www.gstatic.com/firebasejs/10.7.1/firebase-app-compat.js');
      await loadScript('https://www.gstatic.com/firebasejs/10.7.1/firebase-auth-compat.js');

      // Inicializa Firebase
      if (!firebase.apps.length) {
        firebase.initializeApp(FIREBASE_CONFIG);
      }

      auth = firebase.auth();
      isInitialized = true;

      // Configura listener de autenticação
      auth.onAuthStateChanged(handleAuthStateChange);

    } catch (error) {
      console.error('Erro ao inicializar Firebase:', error);
      showConfigError();
    }
  }

  function loadScript(src) {
    return new Promise((resolve, reject) => {
      if (document.querySelector(`script[src="${src}"]`)) {
        resolve();
        return;
      }
      const script = document.createElement('script');
      script.src = src;
      script.onload = resolve;
      script.onerror = reject;
      document.head.appendChild(script);
    });
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // GERENCIAMENTO DE AUTENTICAÇÃO
  // ═══════════════════════════════════════════════════════════════════════════

  function handleAuthStateChange(user) {
    currentUser = user;

    if (user) {
      // Usuário logado - verifica se está na lista de autorizados
      if (RESTRICT_BY_EMAIL && !ALLOWED_EMAILS.includes(user.email.toLowerCase())) {
        showUnauthorizedOverlay(user.email);
        return;
      }

      // Usuário autorizado
      hideLoginOverlay();
      addUserInfo(user);
    } else {
      // Usuário não logado
      showLoginOverlay();
    }
  }

  async function signInWithGoogle() {
    try {
      const provider = new firebase.auth.GoogleAuthProvider();
      provider.setCustomParameters({
        prompt: 'select_account'
      });
      await auth.signInWithPopup(provider);
    } catch (error) {
      console.error('Erro no login:', error);
      showLoginError(error.message);
    }
  }

  async function signOut() {
    try {
      await auth.signOut();
      location.reload();
    } catch (error) {
      console.error('Erro no logout:', error);
    }
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // INTERFACE DE LOGIN
  // ═══════════════════════════════════════════════════════════════════════════

  function showLoginOverlay() {
    // Remove overlay existente se houver
    document.getElementById('authOverlay')?.remove();

    const overlay = document.createElement('div');
    overlay.id = 'authOverlay';
    overlay.innerHTML = `
      <div class="auth-container">
        <div class="auth-card">
          <div class="auth-header">
            <div class="auth-logo">📊</div>
            <h1>PortfolioESG</h1>
            <p>Sistema de Análise de Investimentos</p>
          </div>

          <div class="auth-body">
            <p class="auth-instruction">Faça login para acessar seus dados</p>

            <button id="googleSignInBtn" class="google-signin-btn">
              <svg class="google-icon" viewBox="0 0 24 24" width="24" height="24">
                <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
                <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
                <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
              </svg>
              <span>Entrar com Google</span>
            </button>

            <div id="authError" class="auth-error"></div>
          </div>

          <div class="auth-footer">
            <div class="auth-security">
              <span class="lock-icon">🔒</span>
              <span>Conexão segura via OAuth 2.0</span>
            </div>
          </div>
        </div>
      </div>
    `;

    document.body.prepend(overlay);
    addAuthStyles();

    // Esconde conteúdo principal
    const main = document.querySelector('main');
    if (main) main.style.display = 'none';
    document.body.style.overflow = 'hidden';

    // Event listener para botão de login
    document.getElementById('googleSignInBtn').addEventListener('click', signInWithGoogle);
  }

  function showUnauthorizedOverlay(email) {
    document.getElementById('authOverlay')?.remove();

    const overlay = document.createElement('div');
    overlay.id = 'authOverlay';
    overlay.innerHTML = `
      <div class="auth-container">
        <div class="auth-card">
          <div class="auth-header">
            <div class="auth-logo">🚫</div>
            <h1>Acesso Não Autorizado</h1>
          </div>

          <div class="auth-body">
            <p class="auth-unauthorized-msg">
              O email <strong>${email}</strong> não está autorizado a acessar este sistema.
            </p>
            <p class="auth-instruction">
              Entre em contato com o administrador para solicitar acesso.
            </p>

            <button id="tryAnotherAccountBtn" class="google-signin-btn secondary">
              <span>Tentar com outra conta</span>
            </button>
          </div>
        </div>
      </div>
    `;

    document.body.prepend(overlay);
    addAuthStyles();

    document.getElementById('tryAnotherAccountBtn').addEventListener('click', async () => {
      await signOut();
    });
  }

  function showConfigError() {
    document.getElementById('authOverlay')?.remove();

    const overlay = document.createElement('div');
    overlay.id = 'authOverlay';
    overlay.innerHTML = `
      <div class="auth-container">
        <div class="auth-card">
          <div class="auth-header">
            <div class="auth-logo">⚠️</div>
            <h1>Configuração Necessária</h1>
          </div>

          <div class="auth-body">
            <p class="auth-instruction">
              O Firebase ainda não foi configurado. Siga as instruções no arquivo
              <code>js/auth.js</code> para configurar a autenticação.
            </p>
            <div class="config-steps">
              <h4>Passos:</h4>
              <ol>
                <li>Acesse <a href="https://console.firebase.google.com/" target="_blank">Firebase Console</a></li>
                <li>Crie um projeto</li>
                <li>Ative Authentication > Google</li>
                <li>Copie as credenciais do projeto</li>
                <li>Atualize FIREBASE_CONFIG em auth.js</li>
              </ol>
            </div>
          </div>
        </div>
      </div>
    `;

    document.body.prepend(overlay);
    addAuthStyles();
  }

  function showLoginError(message) {
    const errorEl = document.getElementById('authError');
    if (errorEl) {
      errorEl.textContent = message;
      errorEl.classList.add('visible');
      setTimeout(() => errorEl.classList.remove('visible'), 5000);
    }
  }

  function hideLoginOverlay() {
    const overlay = document.getElementById('authOverlay');
    if (overlay) {
      overlay.classList.add('hiding');
      setTimeout(() => {
        overlay.remove();
        // Mostra conteúdo principal
        const main = document.querySelector('main');
        if (main) main.style.display = '';
        document.body.style.overflow = '';
      }, 300);
    }
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // INFORMAÇÕES DO USUÁRIO
  // ═══════════════════════════════════════════════════════════════════════════

  function addUserInfo(user) {
    // Remove info existente
    document.getElementById('userInfoContainer')?.remove();

    const controls = document.querySelector('.header .controls');
    if (!controls) return;

    const container = document.createElement('div');
    container.id = 'userInfoContainer';
    container.className = 'user-info-container';
    container.innerHTML = `
      <div class="user-info">
        <img src="${user.photoURL || ''}" alt="" class="user-avatar" onerror="this.style.display='none'">
        <span class="user-name">${user.displayName || user.email}</span>
      </div>
      <button id="logoutBtn" class="logout-btn" title="Sair">
        <span>Sair</span>
      </button>
    `;

    controls.prepend(container);

    document.getElementById('logoutBtn').addEventListener('click', () => {
      if (confirm('Deseja encerrar a sessão?')) {
        signOut();
      }
    });

    // Adiciona estilos do usuário
    addUserInfoStyles();
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // ESTILOS
  // ═══════════════════════════════════════════════════════════════════════════

  function addAuthStyles() {
    if (document.getElementById('authStyles')) return;

    const style = document.createElement('style');
    style.id = 'authStyles';
    style.textContent = `
      #authOverlay {
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: linear-gradient(135deg, #01121a 0%, #071726 50%, #0a1f2d 100%);
        z-index: 99999;
        display: flex;
        align-items: center;
        justify-content: center;
        animation: authFadeIn 0.3s ease;
      }
      #authOverlay.hiding {
        animation: authFadeOut 0.3s ease forwards;
      }
      @keyframes authFadeIn {
        from { opacity: 0; }
        to { opacity: 1; }
      }
      @keyframes authFadeOut {
        from { opacity: 1; }
        to { opacity: 0; }
      }
      .auth-container {
        width: 100%;
        max-width: 420px;
        padding: 20px;
      }
      .auth-card {
        background: linear-gradient(180deg, rgba(255,255,255,0.04), rgba(255,255,255,0.01));
        border: 1px solid rgba(255,255,255,0.1);
        border-radius: 20px;
        padding: 48px 40px;
        box-shadow: 0 25px 80px rgba(0,0,0,0.4);
        backdrop-filter: blur(10px);
      }
      .auth-header {
        text-align: center;
        margin-bottom: 36px;
      }
      .auth-logo {
        font-size: 56px;
        margin-bottom: 20px;
        filter: drop-shadow(0 4px 8px rgba(0,0,0,0.3));
      }
      .auth-header h1 {
        color: #6fe3c5;
        font-size: 28px;
        margin: 0 0 8px 0;
        font-weight: 700;
        letter-spacing: -0.5px;
      }
      .auth-header p {
        color: #9fb0bb;
        font-size: 14px;
        margin: 0;
      }
      .auth-body {
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 20px;
      }
      .auth-instruction {
        color: #9fb0bb;
        font-size: 14px;
        text-align: center;
        margin: 0;
      }
      .auth-unauthorized-msg {
        color: #e76f51;
        font-size: 14px;
        text-align: center;
        margin: 0;
        padding: 16px;
        background: rgba(231, 111, 81, 0.1);
        border-radius: 10px;
        border: 1px solid rgba(231, 111, 81, 0.2);
      }
      .auth-unauthorized-msg strong {
        color: #fff;
      }
      .google-signin-btn {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 12px;
        width: 100%;
        padding: 14px 24px;
        background: #fff;
        border: none;
        border-radius: 12px;
        font-size: 16px;
        font-weight: 500;
        color: #3c4043;
        cursor: pointer;
        transition: all 0.2s ease;
        box-shadow: 0 2px 8px rgba(0,0,0,0.15);
      }
      .google-signin-btn:hover {
        background: #f8f9fa;
        box-shadow: 0 4px 16px rgba(0,0,0,0.2);
        transform: translateY(-2px);
      }
      .google-signin-btn:active {
        transform: translateY(0);
      }
      .google-signin-btn.secondary {
        background: transparent;
        border: 1px solid rgba(255,255,255,0.2);
        color: #9fb0bb;
      }
      .google-signin-btn.secondary:hover {
        background: rgba(255,255,255,0.05);
        border-color: rgba(255,255,255,0.3);
        color: #fff;
      }
      .google-icon {
        flex-shrink: 0;
      }
      .auth-error {
        color: #e76f51;
        font-size: 13px;
        text-align: center;
        min-height: 20px;
        opacity: 0;
        transition: opacity 0.3s;
      }
      .auth-error.visible {
        opacity: 1;
      }
      .auth-footer {
        margin-top: 32px;
        padding-top: 24px;
        border-top: 1px solid rgba(255,255,255,0.05);
      }
      .auth-security {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 8px;
        color: #9fb0bb;
        font-size: 12px;
        opacity: 0.7;
      }
      .lock-icon {
        font-size: 14px;
      }
      .config-steps {
        text-align: left;
        background: rgba(255,255,255,0.03);
        border-radius: 10px;
        padding: 20px;
        margin-top: 16px;
        width: 100%;
      }
      .config-steps h4 {
        margin: 0 0 12px 0;
        color: #6fe3c5;
        font-size: 14px;
      }
      .config-steps ol {
        margin: 0;
        padding-left: 20px;
        color: #9fb0bb;
        font-size: 13px;
        line-height: 1.8;
      }
      .config-steps a {
        color: #4fc3f7;
      }
      .config-steps code {
        background: rgba(0,0,0,0.3);
        padding: 2px 6px;
        border-radius: 4px;
        font-size: 12px;
        color: #6fe3c5;
      }
    `;
    document.head.appendChild(style);
  }

  function addUserInfoStyles() {
    if (document.getElementById('userInfoStyles')) return;

    const style = document.createElement('style');
    style.id = 'userInfoStyles';
    style.textContent = `
      .user-info-container {
        display: flex;
        align-items: center;
        gap: 12px;
      }
      .user-info {
        display: flex;
        align-items: center;
        gap: 8px;
        padding: 6px 12px;
        background: rgba(255,255,255,0.05);
        border-radius: 20px;
      }
      .user-avatar {
        width: 28px;
        height: 28px;
        border-radius: 50%;
        border: 2px solid rgba(111, 227, 197, 0.3);
      }
      .user-name {
        color: #eaf6f1;
        font-size: 13px;
        font-weight: 500;
        max-width: 150px;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }
      .logout-btn {
        background: rgba(231, 111, 81, 0.15);
        color: #e76f51;
        border: 1px solid rgba(231, 111, 81, 0.25);
        padding: 6px 14px;
        border-radius: 8px;
        font-size: 13px;
        font-weight: 500;
        cursor: pointer;
        transition: all 0.2s ease;
      }
      .logout-btn:hover {
        background: rgba(231, 111, 81, 0.25);
        border-color: rgba(231, 111, 81, 0.4);
      }
      @media (max-width: 600px) {
        .user-name {
          display: none;
        }
        .user-info {
          padding: 4px;
        }
      }
    `;
    document.head.appendChild(style);
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // INICIALIZAÇÃO
  // ═══════════════════════════════════════════════════════════════════════════

  function init() {
    if (!isConfigured()) {
      showConfigError();
      return;
    }
    initializeFirebase();
  }

  // Aguarda DOM estar pronto
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // Expõe funções globalmente para debug/uso externo
  window.portfolioAuth = {
    signOut: signOut,
    getCurrentUser: () => currentUser,
    isAuthenticated: () => !!currentUser
  };

})();
