/**
 * data-colors.js — Fonte de verdade para todas as cores de dados.
 * Nenhum gráfico, tabela ou badge deve definir suas próprias cores diretamente.
 */

export const DC = {
  // ── Séries temporais fixas ──────────────────────────────────────
  portfolio:   { line: '#1B3560', area: 'rgba(27,53,96,0.13)',  dash: []       },
  ibov:        { line: '#B8780A', area: 'rgba(184,120,10,0.10)', dash: [6, 3]  },
  cdi:         { line: '#8a7a65', area: 'rgba(138,122,101,0.10)',dash: [2, 4]  },

  // ── Semântica de valor (P&L, retorno, ação recomendada) ─────────
  pos: {
    strong:  '#5A8B29',   // Use requested green consistently
    mid:     '#5A8B29',
    light:   '#5A8B29',
    bg:      'rgba(90, 139, 41, 0.09)',
  },
  neg: {
    strong:  '#BD3022',   // Use requested red consistently
    mid:     '#BD3022',
    bg:      'rgba(189, 48, 34, 0.10)',
  },
  neutral: {
    line:    '#5C6B7A',   // Valores entre -2% e +2%
    bg:      'rgba(92,107,122,0.10)',
  },

  // ── Ativos — paleta categórica (até 6 séries distintas) ─────────
  assets: [
    '#1B3560',  // a1 — navy
    '#B8780A',  // a2 — âmbar
    '#6B3FA0',  // a3 — roxo
    '#5A8B29',  // a4 — verde
    '#BD3022',  // a5 — vermelho
    '#5C6B7A',  // a6 — slate
  ],

  // ── Heatmap de correlação (escala divergente) ────────────────────
  heatmap: {
    positive: '#1B3560',
    zero:     '#F5F0E8',
    negative: '#BD3022',
  },

  // ── Score sequencial (ESG, qualidade, momentum) ──────────────────
  score: {
    high:    '#5A8B29',   // score >= 0,55
    medium:  '#B8780A',   // score 0,35–0,54
    low:     '#BD3022',   // score < 0,35
    scoreThresholds: [0.35, 0.55],
  },
};

/**
 * Retorna a cor do ativo baseada na sua posição no ranking de peso.
 * @param {string} ticker 
 * @param {string[]} holdings Array ordenado por peso decrescente.
 */
export function assetColor(ticker, holdings) {
  if (!holdings) return DC.assets[DC.assets.length - 1];
  const i = holdings.indexOf(ticker);
  if (i === -1) return DC.assets[DC.assets.length - 1];
  return DC.assets[Math.min(i, DC.assets.length - 1)];
}

/**
 * Retorna a cor semântica baseada no percentual de retorno/P&L.
 * @param {number} pct Valor decimal (ex: 0.15 para 15%)
 */
export function plColor(pct) {
  if (pct >=  0.20) return DC.pos.strong;
  if (pct >=  0.05) return DC.pos.mid;
  if (pct >=  0.02) return DC.pos.light;
  if (pct >= -0.02) return DC.neutral.line;
  if (pct >= -0.20) return DC.neg.mid;
  return DC.neg.strong;
}

/**
 * Retorna a cor do score baseada nos thresholds centralizados.
 * @param {number} v Valor do score (geralmente 0 a 1)
 */
export function scoreColor(v) {
  const [lo, hi] = DC.score.scoreThresholds;
  if (v >= hi) return DC.score.high;
  if (v >= lo) return DC.score.medium;
  return DC.score.low;
}

/**
 * Interpola as cores do heatmap linearmente.
 * @param {number} v Valor entre -1 e 1.
 */
export function interpHeatmap(v) {
  const zero = [245, 240, 232]; // #F5F0E8
  const pos  = [ 27,  53,  96]; // #1B3560
  const neg  = [189,  48,  34]; // #BD3022
  
  const t = Math.abs(v);
  const base = v >= 0 ? pos : neg;
  
  const r = Math.round(zero[0] + (base[0] - zero[0]) * t);
  const g = Math.round(zero[1] + (base[1] - zero[1]) * t);
  const b = Math.round(zero[2] + (base[2] - zero[2]) * t);
  
  return `rgb(${r},${g},${b})`;
}
