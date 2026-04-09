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
      gap: 12px;
      padding: 14px 20px;
      background: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: 10px;
      margin-bottom: 16px;
    }
    /* Logo + date stacked vertically */
    .header-logo-block {
      display: flex;
      flex-direction: column;
      gap: 2px;
    }
    .header-logo {
      font-size: 18px;
      font-weight: 700;
      letter-spacing: -0.3px;
      color: var(--text-primary);
      white-space: nowrap;
      text-decoration: none;
    }
    .header-logo span { color: var(--accent-blue); }
    .header-date {
      font-size: 11px;
      color: var(--text-muted);
      font-family: var(--font-mono);
    }
    .header-separator {
      width: 1px;
      height: 24px;
      background: var(--border);
      flex-shrink: 0;
    }
    .nav-tabs { display: flex; align-items: center; gap: 4px; }
    .nav-tab {
      display: inline-flex;
      align-items: center;
      padding: 5px 14px;
      border-radius: 6px;
      font-size: 13px;
      font-weight: 500;
      color: var(--text-secondary);
      text-decoration: none;
      border: 1px solid transparent;
      transition: color .15s, background .15s, border-color .15s;
    }
    .nav-tab:hover {
      color: var(--text-primary);
      background: var(--bg-card-hover);
      border-color: var(--border);
    }
    .nav-tab.active {
      color: var(--accent-blue);
      background: rgba(25,113,194,.1);
      border-color: rgba(25,113,194,.3);
    }
    /* Pipeline status — only rendered when running or errored */
    .pipeline-status { display: flex; align-items: center; gap: 6px; font-size: 13px; }
    .status-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
    .status-dot.running { background: var(--accent-yellow); animation: hdr-pulse 1.2s ease-in-out infinite; }
    .status-dot.error   { background: var(--accent-red); }
    @keyframes hdr-pulse { 0%,100%{opacity:1} 50%{opacity:.3} }
    .status-text { color: var(--text-secondary); }
    /* Decision badge — lives inside the portfolio-value block */
    .decision-badge {
      display: inline-flex; align-items: center;
      padding: 3px 10px; border-radius: 6px;
      font-size: 11px; font-weight: 700; letter-spacing: .5px; text-transform: uppercase;
    }
    .decision-badge.rebalance {
      background: rgba(201,42,42,.1); color: var(--accent-red);
      border: 1px solid rgba(201,42,42,.3);
    }
    .decision-badge.hold {
      background: rgba(47,158,68,.1); color: var(--accent-green);
      border: 1px solid rgba(47,158,68,.3);
    }
    /* Portfolio value block — pushes to the right */
    .portfolio-value { margin-left: auto; text-align: right; }
    .portfolio-value .pv-label {
      font-size: 11px; color: var(--text-muted);
      text-transform: uppercase; letter-spacing: .5px;
    }
    .portfolio-value .pv-amount {
      font-size: 20px; font-weight: 700;
      font-family: var(--font-mono); color: var(--text-primary);
      line-height: 1.1;
    }
    .portfolio-value .pv-pnl { font-size: 12px; font-family: var(--font-mono); margin-bottom: 5px; }
    .portfolio-value .pv-pnl.positive { color: var(--accent-green); }
    .portfolio-value .pv-pnl.negative { color: var(--accent-red); }
    @media (max-width: 640px) {
      .header-bar { padding: 12px 14px; gap: 8px; }
      .header-separator { display: none; }
      .portfolio-value { margin-left: 0; width: 100%; text-align: left; margin-top: 4px; }
      .nav-tab { padding: 4px 10px; font-size: 12px; }
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
