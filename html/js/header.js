/* ─────────────────────────────────────────────────────────────
   header.js — PortfolioESG · Premium Dual-Layer Header
   Usage: <script src="../js/header.js" data-page="portfolio|risk|model"></script>
   ───────────────────────────────────────────────────────────── */
(function () {
  const currentPage = (document.currentScript && document.currentScript.dataset.page) || '';
  const DATA_BASE   = '../data';

  /* ─── 1. Inject header CSS ─── */
  const style = document.createElement('style');
  style.textContent = `
    :root {
      --header-top-bg: #1F2329;
      --header-main-bg: #FFF8EE;
    }

    /* Outer wrapper to keep everything sticky */
    .header-wrapper {
      position: sticky;
      top: 0;
      z-index: 1000;
      width: 100%;
      margin-bottom: 32px;
    }

    /* Dark Top Bar */
    .top-bar {
      background: var(--header-top-bg);
      color: #F7F0E6;
      display: flex;
      align-items: center;
      gap: 32px;
      padding: 8px 32px;
      font-size: 11px;
      font-family: var(--font-sans);
      font-weight: 700;
      border-bottom: 1px solid rgba(247,240,230,0.10);
    }
    .top-bar .tb-item { display: flex; align-items: center; gap: 8px; }
    .top-bar .tb-label { color: rgba(247,240,230,0.62); text-transform: uppercase; font-size: 9px; letter-spacing: 0.05em; font-weight: 700; }
    .top-bar .tb-value { font-weight: 700; }
    .top-bar .pv-pnl { font-weight: 700; }
    .top-bar .pv-pnl.positive { color: #A7C96B !important; }
    .top-bar .pv-pnl.negative { color: #E9877F !important; }
    .top-bar .decision-badge { 
      padding: 2px 10px; border-radius: 4px; 
      font-size: 9px; font-weight: 700; text-transform: uppercase;
    }
    .top-bar .decision-badge.rebalance { background: #B86D5D; color: #fff; }
    .top-bar .decision-badge.hold { background: #6F9341; color: #fff; }
    .top-bar .decision-badge.watch { background: #C78F40; color: #fff; }
    .top-bar .decision-badge.partial_rebalance { background: #4F8CC9; color: #fff; }

    /* Light Main Header */
    .header-bar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 12px 32px;
      background: var(--header-main-bg);
      border-bottom: 1px solid var(--border-strong);
      border-left: 1px solid var(--border-strong);
      border-right: 1px solid var(--border-strong);
      border-bottom-left-radius: var(--radius-md);
      border-bottom-right-radius: var(--radius-md);
      box-shadow: var(--shadow-sm);
    }

    .header-logo-block {
      display: flex;
      align-items: center;
      gap: 12px;
    }
    .header-brand-logo {
      height: 24px;
      width: auto;
    }
    .header-logo {
      font-size: 18px;
      font-weight: 800;
      letter-spacing: -0.02em;
      color: var(--text-primary);
      text-decoration: none;
    }
    .header-logo span { color: var(--brand-blue); }
    .nav-tabs { 
      display: flex; 
      align-items: center; 
      gap: 4px; 
    }
    .nav-tab {
      display: inline-flex;
      align-items: center;
      padding: 6px 12px;
      font-size: 13px;
      font-weight: 600;
      color: var(--text-secondary);
      text-decoration: none;
      transition: all 0.2s ease;
      border-bottom: 2px solid transparent;
    }
    .nav-tab:hover { color: var(--brand-blue); }
    .nav-tab.active {
      color: var(--brand-blue);
      border-bottom-color: var(--brand-red);
    }
    .export-btn {
      display: inline-flex; align-items: center; gap: 6px;
      padding: 6px 14px; margin-left: auto;
      font-size: 11px; font-weight: 700; text-transform: uppercase;
      color: #F7F0E6; background: #1F2329;
      border: none; border-radius: 4px;
      cursor: pointer; text-decoration: none;
      transition: background 0.2s;
    }
    .export-btn:hover { background: #2A3038; }

    /* Pipeline status in top bar */
    .pipeline-status { display: flex; align-items: center; gap: 6px; margin-left: auto; font-size: 10px; color: rgba(247,240,230,0.7); }
    .status-dot { width: 8px; height: 8px; border-radius: 50%; }
    .status-dot.running { background: #D79A43; animation: hdr-pulse 1.5s infinite; }
    .status-dot.error   { background: var(--color-negative); }
    @keyframes hdr-pulse { 0%,100%{opacity:1} 50%{opacity:.5} }

    @media (max-width: 1024px) {
      .top-bar { padding: 6px 16px; gap: 16px; overflow-x: auto; white-space: nowrap; }
      .header-bar { padding: 10px 16px; flex-direction: column; gap: 12px; align-items: flex-start; }
      .nav-tabs { margin-left: 0; width: 100%; overflow-x: auto; }
    }
  `;
  document.head.appendChild(style);

  /* ─── 2. Build header DOM ─── */
  const PAGES = [
    { id: 'portfolio', label: 'Portfólio',   href: 'portfolio.html' },
    { id: 'risk',      label: 'Risco',        href: 'risk.html'      },
    { id: 'model',     label: 'Modelo',       href: 'model.html'     },
    { id: 'scoring',   label: 'Scoring ESG',  href: 'scoring.html'  },
    { id: 'history',   label: 'Histórico',    href: 'history.html'  },
    { id: 'glossary',  label: 'Explicações',  href: 'glossary.html' },
  ];

  function buildHeader() {
    const navHTML = PAGES.map(p =>
      `<a class="nav-tab${p.id === currentPage ? ' active' : ''}" href="${p.href}">${p.label}</a>`
    ).join('');

    const wrapper = document.createElement('div');
    wrapper.className = 'header-wrapper';

    wrapper.innerHTML = `
      <!-- Top Dark Bar -->
      <div class="top-bar" id="top-bar">
        <div class="tb-item" id="tb-value">
          <span class="tb-label">Portfolio</span>
          <span class="tb-value">—</span>
        </div>
        <div class="tb-item" id="tb-pnl">
          <span class="tb-label">Valorização</span>
          <span class="tb-value">—</span>
        </div>
        <div class="tb-item" id="tb-alpha">
          <span class="tb-label">Alpha</span>
          <span class="tb-value">—</span>
        </div>
        <div class="tb-item" id="tb-beta">
          <span class="tb-label">Beta</span>
          <span class="tb-value">—</span>
        </div>
        <div class="tb-item" id="tb-cdi">
          <span class="tb-label">% CDI</span>
          <span class="tb-value">—</span>
        </div>
        <div class="tb-item" id="tb-sharpe">
          <span class="tb-label">Sharpe</span>
          <span class="tb-value">—</span>
        </div>
        <div class="tb-item" id="tb-exp">
          <span class="tb-label">Exp. 12M Modelo</span>
          <span class="tb-value">—</span>
        </div>
        <div class="tb-item" id="tb-decision">
          <span class="tb-label">Ação</span>
          <span class="tb-value">—</span>
        </div>
        <div class="tb-item" id="tb-update">
          <span class="tb-label">Ult.</span>
          <span class="tb-value">—</span>
        </div>
        <div id="pipeline-status" class="pipeline-status" style="display:none"></div>
      </div>

      <!-- Main Navigation Bar -->
      <header class="header-bar">
        <nav class="nav-tabs">${navHTML}</nav>
        <button class="export-btn" onclick="window.open('export_pdf.html', '_blank')">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>
          Exportar PDF
        </button>
      </header>
    `;
    return wrapper;
  }

  /* ─── 3. Formatters ─── */
  function fmtBRL(v) {
    if (v == null || isNaN(v)) return '—';
    return v.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
  }
  function fmtPct(v) {
    if (v == null || isNaN(v)) return '—';
    return (v >= 0 ? '+' : '') + (v * 100).toFixed(2) + '%';
  }
  function fmtRunDate(rid) {
    if (!rid) return '—';
    const m = rid.match(/^(\d{4})(\d{2})(\d{2})-/);
    if (!m) return rid;
    const months = ['jan','fev','mar','abr','mai','jun','jul','ago','set','out','nov','dez'];
    return `${parseInt(m[3])} ${months[parseInt(m[2]) - 1]} ${m[1]}`;
  }
  function decisionLabel(decision) {
    return ({
      HOLD: 'Manter',
      WATCH: 'Observar',
      PARTIAL_REBALANCE: 'Parcial',
      REBALANCE: 'Rebalancear',
    })[decision] || (decision || '—');
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

      const runId    = dashboard.model?.meta?.run_id;
      const market   = positions.total_current_market;
      const invested = positions.total_invested_cash;
      const pnl      = positions.total_unrealized_pnl;
      const pnlClass = pnl >= 0 ? 'positive' : 'negative';
      const pnlPct   = invested ? pnl / invested : 0;
      
      const twr      = dashboard.real?.twr || {};
      const alpha    = dashboard.real?.alpha || {};
      const mRet     = dashboard.model?.returns || {};
      const verdict  = dashboard.model?.decision?.verdict;
      const legacyDecision = dashboard.model?.decision?.legacy_decision;
      const shadow   = dashboard.model?.shadow || {};
      const execPlan = shadow.execution_plan || {};
      const actionState = execPlan.decision_state || shadow.shadow_decision || verdict;
      const actionLabel = execPlan.decision_state_label || decisionLabel(actionState);

      // 1) Valor
      document.querySelector('#tb-value .tb-value').textContent = fmtBRL(market);
      
      // 2) Valorização
      document.querySelector('#tb-pnl .tb-value').innerHTML = 
        `<span class="pv-pnl ${pnlClass}">${pnl >= 0 ? '+' : ''}${fmtBRL(pnl)} (${fmtPct(pnlPct)})</span>`;

      // 3) % do CDI
      const pctCdi = twr.pct_cdi || 0;
      document.querySelector('#tb-cdi .tb-value').innerHTML = 
        `<span class="pv-pnl ${pctCdi >= 100 ? 'positive' : 'negative'}">${pctCdi.toFixed(1)}%</span>`;

      // 4) Sharpe Ratio
      document.querySelector('#tb-sharpe .tb-value').textContent = (twr.sharpe || 0).toFixed(2);

      // 5) Alpha vs Ibov
      const alphaVal = alpha.total || 0;
      document.querySelector('#tb-alpha .tb-value').innerHTML = 
        `<span class="pv-pnl ${alphaVal >= 0 ? 'positive' : 'negative'}">${fmtPct(alphaVal)}</span>`;

      // 5.5) Beta
      const betaVal = dashboard.real?.relative?.beta || 0;
      document.querySelector('#tb-beta .tb-value').textContent = betaVal.toFixed(2);

      // 6) Retorno esperado (Modelo)
      document.querySelector('#tb-exp .tb-value').textContent = (mRet.gross_12m || 0).toFixed(2) + '%';

      // 7) Official action. Legacy raw decision remains available in model.html.
      if (actionState) {
        const decCls = String(actionState).toLowerCase();
        const title = legacyDecision && legacyDecision !== actionState
          ? `Legado: ${decisionLabel(legacyDecision)}`
          : '';
        document.querySelector('#tb-decision .tb-value').innerHTML = 
          `<span class="decision-badge ${decCls}" title="${title}">${actionLabel}</span>`;
      }

      // 8) Última Atualização
      document.querySelector('#tb-update .tb-value').textContent = fmtRunDate(runId);

      // Pipeline Status
      const pStatus = progress?.pipeline_run_status;
      if (pStatus && pStatus.start_time && !pStatus.end_time) {
        const pEl = document.getElementById('pipeline-status');
        pEl.style.display = 'flex';
        pEl.innerHTML = `<div class="status-dot running"></div><span>${pStatus.current_stage || 'Executando...'}</span>`;
      }

    } catch (err) {
      console.error('Header render error:', err);
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
