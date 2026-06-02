/**
 * data-colors.js — Fonte de verdade para todas as cores de dados.
 * Nenhum gráfico, tabela ou badge deve definir suas próprias cores diretamente.
 */

export const DC = {
  // ── Séries temporais fixas ──────────────────────────────────────
  portfolio:   { line: '#4F8CC9', area: 'rgba(79,140,201,0.13)',  dash: []       },
  equity:      { line: '#C76C98', area: 'rgba(199,108,152,0.11)', dash: [10, 4]  },
  fund:        { line: '#43AFA3', area: 'rgba(67,175,163,0.11)',  dash: [8, 3]  },
  ibov:        { line: '#D79A43', area: 'rgba(215,154,67,0.10)',  dash: [6, 3]  },
  cdi:         { line: '#8793B0', area: 'rgba(135,147,176,0.09)', dash: [2, 4]  },

  // ── Semântica de valor (P&L, retorno, ação recomendada) ─────────
  pos: {
    strong:  '#5F8234',
    mid:     '#6F9341',
    light:   '#86AA59',
    bg:      'rgba(111, 147, 65, 0.11)',
  },
  neg: {
    strong:  '#A45A4E',
    mid:     '#B86D5D',
    bg:      'rgba(184, 109, 93, 0.11)',
  },
  neutral: {
    line:    '#8793B0',   // Valores entre -2% e +2%
    bg:      'rgba(135,147,176,0.12)',
  },

  // ── Ativos e setores — paleta categórica comum para barras e rosca ──
  assets: [
    '#4F8CC9',  // a1 — soft blue
    '#43AFA3',  // a2 — aqua
    '#D79A43',  // a3 — amber
    '#C76C98',  // a4 — rose
    '#7D8F4E',  // a5 — olive
    '#B86D5D',  // a6 — clay
    '#8793B0',  // a7 — lavender slate
    '#9B80C9',  // a8 — lilac
  ],

  // ── Heatmap de correlação (escala divergente) ────────────────────
  heatmap: {
    positive: '#3F78AE',
    zero:     '#F5F0E8',
    negative: '#B86D5D',
  },

  // ── Score sequencial (ESG, qualidade, momentum) ──────────────────
  score: {
    high:    '#6F9341',   // score >= 0,55
    medium:  '#D79A43',   // score 0,35–0,54
    low:     '#B86D5D',   // score < 0,35
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
  const pos  = [ 63, 120, 174]; // #3F78AE
  const neg  = [184, 109,  93]; // #B86D5D
  
  const t = Math.abs(v);
  const base = v >= 0 ? pos : neg;
  
  const r = Math.round(zero[0] + (base[0] - zero[0]) * t);
  const g = Math.round(zero[1] + (base[1] - zero[1]) * t);
  const b = Math.round(zero[2] + (base[2] - zero[2]) * t);
  
  return `rgb(${r},${g},${b})`;
}
