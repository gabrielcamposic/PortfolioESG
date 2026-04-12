/* ─────────────────────────────────────────────────────────────
   header.js — PortfolioESG · auto-inject shared header + nav
   Usage: <script src="../js/header.js" data-page="portfolio|risk|model"></script>
   ───────────────────────────────────────────────────────────── */
(function () {
  const currentPage = (document.currentScript && document.currentScript.dataset.page) || '';
  const DATA_BASE   = '../data';

  /* ─── 1. Inject header CSS ─── */
  const style = document.createElement('style');
  style.textContent = `
    .header-bar {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 16px;
      padding: 14px 24px;
      background: var(--glass-bg);
      backdrop-filter: var(--glass-blur);
      -webkit-backdrop-filter: var(--glass-blur);
      border: 1px solid var(--border);
      border-radius: var(--radius-lg);
      margin-bottom: 32px;
      box-shadow: var(--shadow-premium);
      position: sticky;
      top: 10px;
      z-index: 100;
    }

    .header-logo-block {
      display: flex;
      flex-direction: column;
      align-items: flex-start;
      gap: 4px;
    }
    .header-brand-logo {
      height: 28px;
      width: auto;
      object-fit: contain;
    }
    .header-logo {
      font-size: 20px;
      font-weight: var(--font-weight-emphasis);
      letter-spacing: -0.02em;
      color: var(--text-primary);
      text-decoration: none;
      line-height: 1;
    }
    .header-logo span { color: var(--accent-blue); }
    .header-date {
      font-size: 9px;
      color: var(--text-muted);
      font-family: var(--font-sans);
      font-weight: var(--font-weight-emphasis);
      text-transform: uppercase;
      letter-spacing: 0.1em;
    }
    .header-separator {
      width: 1px;
      height: 48px;
      background: var(--border-strong);
      flex-shrink: 0;
    }
    .nav-tabs { 
      display: flex; 
      align-items: center; 
      gap: 4px; 
      background: var(--bg-card-alt);
      padding: 4px;
      border-radius: var(--radius-md);
      border: 1px solid var(--border-strong);
    }
    .nav-tab {
      display: inline-flex;
      align-items: center;
      padding: 6px 4px;
      margin: 0 10px;
      border-radius: 0;
      font-size: 13px;
      font-weight: var(--font-weight-emphasis);
      color: var(--text-secondary);
      text-decoration: none;
      transition: all 0.2s ease;
      border-bottom: 3px solid transparent;
    }
    .nav-tab:hover {
      color: var(--brand-blue);
    }
    .nav-tab.active {
      color: var(--brand-blue);
      border-bottom-color: var(--brand-red);
    }
    /* Pipeline status */
    .pipeline-status { display: flex; align-items: center; gap: 8px; font-size: 12px; font-weight: 600; color: var(--text-secondary); }
    .status-dot { width: 10px; height: 10px; border-radius: 50%; border: 2px solid var(--bg-card); box-shadow: 0 0 0 1px var(--border); }
    .status-dot.running { background: var(--accent-yellow); animation: hdr-pulse 1.5s ease-in-out infinite; }
    .status-dot.error   { background: var(--color-negative); }
    @keyframes hdr-pulse { 0%,100%{opacity:1; transform: scale(1);} 50%{opacity:.5; transform: scale(0.9);} }
    
    .decision-badge {
      display: inline-flex; align-items: center;
      padding: 4px 10px; border-radius: 20px;
      font-size: 9px; font-weight: var(--font-weight-emphasis); letter-spacing: 0.05em; text-transform: uppercase;
      box-shadow: var(--shadow-sm);
    }
    .decision-badge.rebalance {
      background: var(--bg-negative); color: var(--color-negative); border: 1px solid var(--color-negative);
    }
    .decision-badge.hold {
      background: var(--bg-positive); color: var(--color-positive); border: 1px solid var(--color-positive);
    }
    
    .portfolio-value { 
      margin-left: auto; 
      display: flex;
      flex-direction: column;
      align-items: flex-end;
    }
    .portfolio-value .pv-label {
      font-size: 9px; color: var(--color-label);
      text-transform: uppercase; font-weight: var(--font-weight-emphasis); letter-spacing: 0.8px;
    }
    .portfolio-value .pv-amount {
      font-size: 26px; font-weight: var(--font-weight-light);
      font-family: var(--font-sans); color: var(--text-primary);
      line-height: 1; letter-spacing: -0.5px;
    }
    .portfolio-value .pv-pnl { font-size: 11px; font-weight: var(--font-weight-emphasis); font-family: var(--font-sans); }
    
    @media (max-width: 1024px) {
      .header-bar { padding: 10px 16px; border-radius: var(--radius-md); top: 0; margin-bottom: 16px; width: 100%; left: 0; border-left: none; border-right: none; }
      .nav-tabs { width: 100%; order: 3; overflow-x: auto; white-space: nowrap; scrollbar-width: none; }
      .nav-tabs::-webkit-scrollbar { display: none; }
      .header-separator { display: none; }
      .portfolio-value { margin-left: auto; }
    }
    @media (max-width: 640px) {
      .header-logo { font-size: 18px; }
      .portfolio-value .pv-amount { font-size: 18px; }
      .nav-tab { padding: 5px 10px; font-size: 12px; }
      .header-brand-logo { height: 22px; }
    }


  `;
  document.head.appendChild(style);

  /* ─── 2. Build header DOM ─── */
  const PAGES = [
    { id: 'portfolio', label: 'Portfólio',   href: '1_portfolio.html' },
    { id: 'risk',      label: 'Risco',        href: '2_risk.html'      },
    { id: 'model',     label: 'Modelo',       href: '3_model.html'     },
    { id: 'scoring',   label: 'Scoring ESG',  href: '07_scoring.html'  },
    { id: 'history',   label: 'Histórico',    href: '08_history.html'  },
    { id: 'glossary',  label: 'Explicações',  href: '09_glossary.html' },
  ];

  function buildHeader() {
    const navHTML = PAGES.map(p =>
      `<a class="nav-tab${p.id === currentPage ? ' active' : ''}" href="${p.href}">${p.label}</a>`
    ).join('');
    const el = document.createElement('div');
    el.id = 'header-bar';
    el.className = 'header-bar';
    el.innerHTML = `
      <div class="header-logo-block">
        <img src="../img/logo.png" class="header-brand-logo" alt="Logo">
        <a class="header-logo" href="1_portfolio.html">Portfolio<span>ESG</span></a>
        <span id="header-date" class="header-date">—</span>
      </div>

      <div class="header-separator"></div>
      <nav class="nav-tabs">${navHTML}</nav>
      <div id="pipeline-separator" class="header-separator" style="display:none"></div>
      <div id="pipeline-status" class="pipeline-status" style="display:none"></div>
      <div class="portfolio-value" id="portfolio-value">
        <div class="pv-label">Valor do Portfolio</div>
        <div class="pv-amount">—</div>
      </div>
    `;
    return el;
  }

  /* ─── 3. Formatters ─── */
  function fmtBRL(v) {
    if (v == null || isNaN(v)) return '—';
    return v.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
  }
  function fmtPct(v) {
    if (v == null || isNaN(v)) return '—';
    return (v * 100).toFixed(2) + '%';
  }
  // "20260321-060232" → "21 mar 2026"
  function fmtRunDate(rid) {
    if (!rid) return '—';
    const m = rid.match(/^(\d{4})(\d{2})(\d{2})-/);
    if (!m) return rid;
    const months = ['jan','fev','mar','abr','mai','jun','jul','ago','set','out','nov','dez'];
    return `${parseInt(m[3])} ${months[parseInt(m[2]) - 1]} ${m[1]}`;
  }

  /* ─── 4. Fetch & render data ─── */
  async function fetchJSON(file) {
    const r = await fetch(`${DATA_BASE}/${file}`);
    if (!r.ok) throw new Error(`${file}: ${r.status}`);
    return r.json();
  }

  async function renderData() {
    try {
      const [dashboard, positions, progress] = await Promise.all([
        fetchJSON('dashboard_latest.json'),
        fetchJSON('ledger_positions.json'),
        fetchJSON('pipeline_progress.json').catch(() => null),
      ]);

      // ── Date below logo (from run_id) ──────────────────────────────────
      const runId = dashboard.model?.meta?.run_id;
      const dateEl = document.getElementById('header-date');
      if (dateEl) dateEl.textContent = fmtRunDate(runId);

      // ── Pipeline status — only show when actively running or errored ───
      const pStatus = progress?.pipeline_run_status;
      if (pStatus) {
        const stage = (pStatus.current_stage || '').toLowerCase();
        let dotClass = null;
        let text = '';
        if (pStatus.start_time && !pStatus.end_time) {
          dotClass = 'running';
          text = pStatus.current_stage || 'Em execução…';
        } else if (stage === 'error' || pStatus.status_message?.toLowerCase().includes('error')) {
          dotClass = 'error';
          text = pStatus.status_message || 'Erro';
        }
        // Only render if there's something actionable to show
        if (dotClass) {
          document.getElementById('pipeline-status').style.display = 'flex';
          document.getElementById('pipeline-status').innerHTML =
            `<div class="status-dot ${dotClass}"></div><span class="status-text">${text}</span>`;
          document.getElementById('pipeline-separator').style.display = '';
        }
      }

      // ── Portfolio value + decision badge ──────────────────────────────
      const market   = positions.total_current_market;
      const invested = positions.total_invested_cash;
      const pnl      = positions.total_unrealized_pnl;
      const pnlClass = pnl >= 0 ? 'positive' : 'negative';
      const pnlSign  = pnl >= 0 ? '+' : '';
      const pnlPct   = invested ? pnl / invested : 0;

      const verdict  = dashboard.model?.decision?.verdict;
      const decCls   = verdict?.toUpperCase() === 'REBALANCE' ? 'rebalance' : 'hold';
      const decLabel = verdict?.toUpperCase() === 'REBALANCE' ? 'Rebalancear' : 'Manter';
      const decHTML  = verdict
        ? `<span class="decision-badge ${decCls}">${decLabel}</span>`
        : '';

      document.getElementById('portfolio-value').innerHTML = `
        <div class="pv-label">Valor do Portfolio</div>
        <div class="pv-amount">${fmtBRL(market)}</div>
        <div class="pv-pnl ${pnlClass}">${pnlSign}${fmtBRL(pnl)} (${pnlSign}${fmtPct(pnlPct)})</div>
        ${decHTML}
      `;

    } catch (err) {
      console.error('Header render error:', err);
      document.getElementById('portfolio-value').innerHTML =
        `<div class="pv-label">Valor do Portfolio</div><div class="pv-amount">—</div>`;
    }
  }

  /* ─── 5. Init ─── */
  function init() {
    document.body.insertBefore(buildHeader(), document.body.firstChild);
    renderData();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
