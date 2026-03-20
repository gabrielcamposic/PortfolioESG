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
    .header-logo {
      font-size: 18px;
      font-weight: 700;
      letter-spacing: -0.3px;
      color: var(--text-primary);
      white-space: nowrap;
      text-decoration: none;
    }
    .header-logo span { color: var(--accent-blue); }
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
    .pipeline-status { display: flex; align-items: center; gap: 6px; font-size: 13px; }
    .status-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
    .status-dot.completed { background: var(--accent-green); }
    .status-dot.running   { background: var(--accent-yellow); animation: hdr-pulse 1.2s ease-in-out infinite; }
    .status-dot.error     { background: var(--accent-red); }
    .status-dot.idle      { background: var(--text-muted); }
    @keyframes hdr-pulse { 0%,100%{opacity:1} 50%{opacity:.3} }
    .status-text { color: var(--text-secondary); }
    .decision-badge {
      display: inline-flex; align-items: center; gap: 5px;
      padding: 4px 12px; border-radius: 6px;
      font-size: 12px; font-weight: 700; letter-spacing: .5px; text-transform: uppercase;
    }
    .decision-badge.rebalance {
      background: rgba(201,42,42,.1); color: var(--accent-red);
      border: 1px solid rgba(201,42,42,.3);
    }
    .decision-badge.hold {
      background: rgba(47,158,68,.1); color: var(--accent-green);
      border: 1px solid rgba(47,158,68,.3);
    }
    .portfolio-value { margin-left: auto; text-align: right; }
    .portfolio-value .label {
      font-size: 11px; color: var(--text-muted);
      text-transform: uppercase; letter-spacing: .5px;
    }
    .portfolio-value .amount {
      font-size: 20px; font-weight: 700;
      font-family: var(--font-mono); color: var(--text-primary);
    }
    .portfolio-value .pnl { font-size: 12px; font-family: var(--font-mono); }
    .portfolio-value .pnl.positive { color: var(--accent-green); }
    .portfolio-value .pnl.negative { color: var(--accent-red); }
    .portfolio-value .run-meta {
      font-size: 10px; color: var(--text-muted);
      font-family: var(--font-mono); margin-top: 3px;
    }
    @media (max-width: 640px) {
      .header-bar { padding: 12px 14px; gap: 8px; }
      .header-separator { display: none; }
      .portfolio-value { margin-left: 0; width: 100%; text-align: left; margin-top: 4px; }
      .nav-tab  { padding: 4px 10px; font-size: 12px; }
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
  ];

  function buildHeader() {
    const navHTML = PAGES.map(p =>
      `<a class="nav-tab${p.id === currentPage ? ' active' : ''}" href="${p.href}">${p.label}</a>`
    ).join('');
    const el = document.createElement('div');
    el.id = 'header-bar';
    el.className = 'header-bar';
    el.innerHTML = `
      <a class="header-logo" href="1_portfolio.html">Portfolio<span>ESG</span></a>
      <div class="header-separator"></div>
      <nav class="nav-tabs">${navHTML}</nav>
      <div class="header-separator"></div>
      <div id="pipeline-status" class="pipeline-status">
        <div class="status-dot idle"></div>
        <span class="status-text">—</span>
      </div>
      <div id="decision-container"></div>
      <div class="portfolio-value" id="portfolio-value">
        <div class="label">Patrimônio Real</div>
        <div class="amount">—</div>
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
  function fmtRunId(rid) {
    if (!rid) return '—';
    const m = rid.match(/^(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})(\d{2})$/);
    if (!m) return rid;
    return `${m[3]}/${m[2]}/${m[1]} ${m[4]}:${m[5]}`;
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

      // Run info
      const runId = dashboard.model?.meta?.run_id;

      // Pipeline status
      const pStatus = progress?.pipeline_run_status;
      if (pStatus) {
        const stage = (pStatus.current_stage || '').toLowerCase();
        let dotClass = 'idle';
        let text = pStatus.status_message || pStatus.current_stage || 'Desconhecido';
        if (stage === 'completed' || pStatus.status_message === 'Completed') {
          dotClass = 'completed'; text = 'Concluído';
        } else if (pStatus.end_time) {
          dotClass = 'completed';
        } else if (pStatus.start_time && !pStatus.end_time) {
          dotClass = 'running';
          text = pStatus.current_stage || 'Em execução...';
        }
        document.getElementById('pipeline-status').innerHTML = `
          <div class="status-dot ${dotClass}"></div>
          <span class="status-text">${text}</span>
        `;
      }

      // Decision badge
      const verdict = dashboard.model?.decision?.verdict;
      if (verdict) {
        const cls   = verdict.toUpperCase() === 'REBALANCE' ? 'rebalance' : 'hold';
        const label = verdict.toUpperCase() === 'REBALANCE' ? 'Rebalancear' : 'Manter';
        document.getElementById('decision-container').innerHTML =
          `<span class="decision-badge ${cls}">${label}</span>`;
      }

      // Portfolio value
      const market   = positions.total_current_market;
      const invested = positions.total_invested_cash;
      const pnl      = positions.total_unrealized_pnl;
      const pnlClass = pnl >= 0 ? 'positive' : 'negative';
      const pnlSign  = pnl >= 0 ? '+' : '';
      const pnlPct   = invested ? pnl / invested : 0;
      document.getElementById('portfolio-value').innerHTML = `
        <div class="label">Patrimônio Real</div>
        <div class="amount">${fmtBRL(market)}</div>
        <div class="pnl ${pnlClass}">${pnlSign}${fmtBRL(pnl)} (${pnlSign}${fmtPct(pnlPct)})</div>
        <div class="run-meta">${runId ? `Run ID: ${runId} | Data: ${fmtRunId(runId)}` : '—'}</div>
      `;

    } catch (err) {
      console.error('Header render error:', err);
      document.getElementById('portfolio-value').innerHTML =
        `<div class="label">Patrimônio Real</div><div class="amount">—</div><div class="run-meta error-msg">Erro: ${err.message}</div>`;
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
