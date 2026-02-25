// ═══════════════════════════════════════════════════════════════════════════
// FIREBASE CONFIGURATION TEMPLATE
// ═══════════════════════════════════════════════════════════════════════════
// INSTRUÇÕES:
// 1. Copie este arquivo para firebase-config.js
// 2. Substitua os valores YOUR_* pelas suas credenciais do Firebase
// 3. O arquivo firebase-config.js está no .gitignore e não será commitado
// ═══════════════════════════════════════════════════════════════════════════
window.FIREBASE_CONFIG = {
    apiKey: "YOUR_API_KEY",
    authDomain: "YOUR_PROJECT_ID.firebaseapp.com",
    projectId: "YOUR_PROJECT_ID",
    storageBucket: "YOUR_PROJECT_ID.firebasestorage.app",
    messagingSenderId: "YOUR_MESSAGING_SENDER_ID",
    appId: "YOUR_APP_ID",
    measurementId: "YOUR_MEASUREMENT_ID"
};
// Lista de emails autorizados a acessar o sistema
window.ALLOWED_EMAILS = [
    "seu-email@exemplo.com"
];
