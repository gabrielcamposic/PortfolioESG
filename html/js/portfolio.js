/**
 * portfolio.js - RENDERER ONLY
 * Painel Estratégico do Modelo Quantitativo
 *
 * ═══════════════════════════════════════════════════════════════════════════
 * ARQUITETURA:
 * - Este arquivo é APENAS um renderer
 * - NENHUMA lógica de cálculo
 * - Consome exclusivamente window.getPortfolioModel() de modelo.js
 * - Se um campo não existir, exibe "N/A"
 * ═══════════════════════════════════════════════════════════════════════════
 *
 * ENGINE: modelo.js
 * RENDERER: portfolio.js (este arquivo)
 */

(function() {
  'use strict';

  // ═══════════════════════════════════════════════════════════════════════════
  // DATA LOADING - Consumes MODEL from modelo.js
  // ═══════════════════════════════════════════════════════════════════════════

  let MODEL = null;

  async function loadModel() {
    // Load modelo.js first (it exposes window.getPortfolioModel)
    if (typeof window.loadPortfolioModel === 'function') {
      await window.loadPortfolioModel();
    }

    // Get the normalized MODEL
    if (typeof window.getPortfolioModel === 'function') {
      MODEL = window.getPortfolioModel();
    }

    if (!MODEL) {
      // Fallback: load data directly if modelo.js not available
      await loadDataDirectly();
    }

    if (MODEL) {
      console.log('[portfolio.js] MODEL loaded from modelo.js:', MODEL);
      renderAll();
    } else {
      console.error('[portfolio.js] Failed to load MODEL');
    }
  }

  // Fallback direct loader if modelo.js not loaded
  async function loadDataDirectly() {
    try {
      const [optResp, latestResp, pipelineResp] = await Promise.all([
        fetch('./data/optimized_recommendation.json?_=' + Date.now()),
        fetch('./data/latest_run_summary.json?_=' + Date.now()),
        fetch('./data/pipeline_latest.json?_=' + Date.now())
      ]);

      const opt = optResp.ok ? await optResp.json() : {};
      const latest = latestResp.ok ? await latestResp.json() : {};
      const pipeline = pipelineResp.ok ? await pipelineResp.json() : {};

      // Build minimal MODEL from raw data (read-only, no calculations)
      MODEL = buildMinimalModel(opt, latest, pipeline);
    } catch (err) {
      console.error('[portfolio.js] Error loading data directly:', err);
    }
  }

  // Build minimal MODEL from raw JSON (NO CALCULATIONS - only field mapping)
  function buildMinimalModel(opt, latest, pipeline) {
    const comparison = opt.comparison || {};
    const holdings = comparison.holdings || {};
    const ideal = comparison.ideal || {};
    const optimal = comparison.optimal || {};
    const bestPortfolio = latest.best_portfolio_details || {};
    const momentumVal = bestPortfolio.momentum_valuation || {};

    return {
      meta: {
        run_id: latest.last_updated_run_id || opt.comparison?.ideal?.run_id || '—',
        timestamp: latest.last_updated_timestamp || opt.timestamp || '—',
        date: opt.date || '—'
      },
      returns: {
        hold_12m: holdings.expected_return_pct ?? null,
        gross_12m: ideal.expected_return_pct ?? null,
        net_12m: optimal.expected_return_net_pct ?? ideal.expected_return_pct ?? null,
        historical_annual: ideal.historical_return_pct ?? bestPortfolio.expected_return_annual_pct ?? null,
        excess_net_12m: opt.excess_return_pct ?? null
      },
      risk: {
        volatility_annual: bestPortfolio.expected_volatility_annual_pct ?? null,
        sharpe: ideal.sharpe_ratio ?? bestPortfolio.sharpe_ratio ?? null,
        sharpe_source: ideal.sharpe_source ?? bestPortfolio.sharpe_source ?? null,
        hhi_current: holdings.hhi ?? null,
        hhi_ideal: bestPortfolio.concentration_risk?.hhi ?? null,
        top5_current: holdings.top5_pct ?? null,
        top5_ideal: bestPortfolio.concentration_risk?.top_5_holdings_pct ?? null
      },
      costs: {
        turnover_pct: opt.turnover_pct ?? null,
        gross_turnover_value: opt.turnover_value ?? null,
        total_cost_brl: opt.transition_cost_brl ?? null,
        cost_pct_on_portfolio: opt.transition_cost_pct ?? null
      },
      weights: {
        current: holdings.weights || {},
        target_full_model: ideal.weights || {},
        target_after_intensity: optimal.weights || holdings.weights || {}
      },
      decision: {
        verdict: opt.decision || 'HOLD',
        reason: opt.reason || '',
        threshold_pct: opt.min_threshold_pct ?? null,
        intensity_theoretical: opt.intensity_theoretical ?? null,
        intensity_applied: opt.intensity_applied ?? null
      },
      transactions_applied: opt.transactions || [],
      transactions_theoretical: [],
      portfolio: {
        total_value: holdings.total_value || 0,
        stocks_current: holdings.stocks || [],
        stocks_ideal: ideal.stocks || [],
        pipeline_rows: pipeline.rows || []
      },
      valuation: {
        portfolio_pe: momentumVal.portfolio_forward_pe ?? bestPortfolio.portfolio_weighted_pe ?? null,
        benchmark_pe: momentumVal.benchmark_forward_pe ?? null,
        pe_deviation_pct: momentumVal.pe_deviation_pct ?? null,
        dividend_yield: momentumVal.portfolio_dividend_yield ?? null,
        momentum_signal: momentumVal.portfolio_momentum ?? null
      },
      regime: {
        detected: opt.regime_detected ?? null,
        momentum_value: momentumVal.portfolio_momentum ?? null
      },
      scoring: {
        weights: opt.parameters ?? null,
        profile: opt.risk_profile ?? null,
        profile_strength: opt.profile_strength ?? null
      },
      assumptions: {
        horizon_description: opt.horizon_description ?? null,
        risk_free_rate_annual: opt.risk_free_rate ?? null,
        risk_free_source: opt.risk_free_source ?? null,
        decision_threshold_pct: opt.min_threshold_pct ?? null
      }
    };
  }


  // ═══════════════════════════════════════════════════════════════════════════
  // FORMATTING HELPERS (presentation only, no calculations)
  // ═══════════════════════════════════════════════════════════════════════════

  function fmt(value, type) {
    if (value === null || value === undefined || (typeof value === 'number' && isNaN(value))) {
      return 'N/A';
    }

    switch (type) {
      case 'pct':
        return `${value >= 0 ? '+' : ''}${Number(value).toFixed(2)}%`;
      case 'pct1':
        return `${Number(value).toFixed(1)}%`;
      case 'pct3':
        return `${Number(value).toFixed(3)}%`;
      case 'num':
        return Number(value).toFixed(2);
      case 'num4':
        return Number(value).toFixed(4);
      case 'brl':
        return `R$ ${Number(value).toFixed(2)}`;
      case 'int':
        return `${Math.round(value)}%`;
      default:
        return String(value);
    }
  }

  function getReturnClass(value) {
    if (value == null) return '';
    return value > 0 ? 'positive' : (value < 0 ? 'negative' : 'neutral');
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // RENDER FUNCTIONS (display only, no calculations)
  // ═══════════════════════════════════════════════════════════════════════════

  function renderAll() {
    if (!MODEL) return;

    renderMeta();
    renderDecision();
    renderComparison();
    renderPortfolio();
    renderDifferences();
    renderRisk();
    renderDiagnostics();
    renderValuation();
    renderAssumptions();
  }

  function renderMeta() {
    setText('runId', MODEL.meta.run_id);
    setText('lastUpdated', MODEL.meta.timestamp);
    setText('decisionDate', MODEL.meta.date);
  }

  function renderDecision() {
    const card = document.getElementById('decisao');
    const verdictEl = document.getElementById('decisionVerdict');
    const reasonEl = document.getElementById('decisionReason');

    if (!card || !verdictEl || !reasonEl) return;

    const isRebalance = MODEL.decision.verdict === 'REBALANCE';
    card.classList.remove('decision-hold', 'decision-rebalance');
    card.classList.add(isRebalance ? 'decision-rebalance' : 'decision-hold');

    verdictEl.textContent = MODEL.decision.verdict || 'N/A';
    verdictEl.className = 'decision-verdict ' + (isRebalance ? 'rebalance' : 'hold');
    reasonEl.textContent = MODEL.decision.reason || 'N/A';

    // Display values directly from MODEL
    setTextWithClass('idealReturn', fmt(MODEL.returns.net_12m, 'pct'), getReturnClass(MODEL.returns.net_12m));
    setTextWithClass('holdReturn', fmt(MODEL.returns.hold_12m, 'pct'), MODEL.returns.hold_12m > 0 ? 'positive' : 'neutral');
    setTextWithClass('excessReturn', fmt(MODEL.returns.excess_net_12m, 'pct'), getReturnClass(MODEL.returns.excess_net_12m));

    setText('blendRatio', fmt(MODEL.decision.intensity_applied, 'int'));
    setText('turnoverPct', fmt(MODEL.costs.turnover_pct, 'pct1'));
    setText('transitionCostPct', `-${fmt(MODEL.costs.cost_pct_on_portfolio, 'pct3')}`);
    setText('transitionCostBRL', fmt(MODEL.costs.total_cost_brl, 'brl'));
  }

  function renderComparison() {
    const tbody = document.getElementById('comparisonBody');
    if (!tbody) return;

    const metrics = [
      { label: 'Expected Return (Forward)', hold: MODEL.returns.hold_12m, ideal: MODEL.returns.gross_12m, benchmark: null, type: 'pct', higher: true },
      { label: 'Expected Return (Líquido)', hold: MODEL.returns.hold_12m, ideal: MODEL.returns.net_12m, benchmark: null, type: 'pct', higher: true },
      { label: 'Volatilidade Esperada', hold: null, ideal: MODEL.risk.volatility_annual, benchmark: null, type: 'pct', higher: false },
      { label: `Sharpe (${MODEL.risk.sharpe_source || 'backtest'})`, hold: null, ideal: MODEL.risk.sharpe, benchmark: null, type: 'num', higher: true },
      { label: 'HHI (Concentração)', hold: MODEL.risk.hhi_current, ideal: MODEL.risk.hhi_ideal, benchmark: null, type: 'num4', higher: false },
      { label: 'Top 5 Holdings', hold: MODEL.risk.top5_current, ideal: MODEL.risk.top5_ideal, benchmark: null, type: 'pct1', higher: false },
      { label: 'Portfolio P/E', hold: null, ideal: MODEL.valuation.portfolio_pe, benchmark: MODEL.valuation.benchmark_pe, type: 'num', higher: false },
      { label: 'Momentum Signal', hold: null, ideal: MODEL.valuation.momentum_signal, benchmark: null, type: 'num', higher: true },
      { label: 'Dividend Yield', hold: null, ideal: MODEL.valuation.dividend_yield, benchmark: null, type: 'pct', higher: true }
    ];

    tbody.innerHTML = metrics.map(m => {
      const holdVal = fmt(m.hold, m.type);
      const idealVal = fmt(m.ideal, m.type);
      const benchVal = fmt(m.benchmark, m.type);

      // Simple comparison coloring (no calculation, just display logic)
      let holdClass = '', idealClass = '';
      if (m.hold != null && m.ideal != null && m.higher != null) {
        const better = m.higher ? m.ideal > m.hold : m.ideal < m.hold;
        idealClass = better ? 'better' : 'worse';
        holdClass = better ? 'worse' : 'better';
      }

      return `<tr>
        <td>${m.label}</td>
        <td class="${holdClass}">${holdVal}</td>
        <td class="${idealClass}">${idealVal}</td>
        <td class="neutral">${benchVal}</td>
      </tr>`;
    }).join('');
  }

  function renderPortfolio() {
    const weights = MODEL.weights.target_after_intensity || {};
    const stocks = Object.keys(weights).sort((a, b) => (weights[b] || 0) - (weights[a] || 0));
    const pipelineRows = MODEL.portfolio.pipeline_rows || [];
    const stockData = {};
    pipelineRows.forEach(r => { if (r.ticker) stockData[r.ticker] = r; });

    // Bar chart
    const barsContainer = document.getElementById('weightBars');
    if (barsContainer) {
      barsContainer.innerHTML = stocks.slice(0, 8).map(stock => {
        const weight = weights[stock] || 0;
        const pct = (weight * 100).toFixed(1);
        const widthPct = Math.min(weight * 100 / 30 * 100, 100);
        return `<div class="h-bar-row">
          <div class="h-bar-label">${stock.replace('.SA', '')}</div>
          <div class="h-bar-track">
            <div class="h-bar-fill" style="width: ${widthPct}%">${pct}%</div>
          </div>
        </div>`;
      }).join('');
    }

    // Table
    const tbody = document.getElementById('portfolioBody');
    if (tbody) {
      tbody.innerHTML = stocks.map(stock => {
        const weight = weights[stock] || 0;
        const data = stockData[stock] || {};
        const weightPct = (weight * 100).toFixed(2) + '%';
        const fwdPE = fmt(data.forward_pe, 'num');
        const target = data.target != null ? fmt(data.target, 'brl') : 'N/A';
        // Use upside directly from data (no calculation)
        const upside = data.upside_pct ?? null;
        const upsideStr = upside != null ? fmt(upside, 'pct') : 'N/A';
        const upsideClass = upside != null ? (upside > 0 ? 'upside-positive' : 'upside-negative') : '';

        return `<tr>
          <td>${stock}</td>
          <td>${weightPct}</td>
          <td>${fwdPE}</td>
          <td>${target}</td>
          <td class="${upsideClass}">${upsideStr}</td>
        </tr>`;
      }).join('');
    }
  }

  function renderDifferences() {
    // Use transactions_applied from MODEL (respects HOLD decision)
    const transactions = MODEL.transactions_applied || [];

    // Summary values directly from MODEL
    setText('totalTurnover', fmt(MODEL.costs.turnover_pct, 'pct1'));
    setText('totalMoveValue', fmt(MODEL.costs.gross_turnover_value, 'brl'));

    const tbody = document.getElementById('diffBody');
    if (!tbody) return;

    if (MODEL.decision.verdict === 'HOLD' || transactions.length === 0) {
      tbody.innerHTML = `<tr><td colspan="5" style="text-align:center;color:var(--muted);padding:20px;">
        Sem transações recomendadas — decisão HOLD
      </td></tr>`;
      return;
    }

    // Display transactions from MODEL
    tbody.innerHTML = transactions.slice(0, 15).map(t => {
      const currentPct = fmt((t.current_weight || 0) * 100, 'pct1');
      const targetPct = fmt((t.target_weight || 0) * 100, 'pct1');
      const diffPct = fmt((t.weight_change || 0) * 100, 'pct');

      let actionClass = 'action-hold';
      const action = t.action || 'Manter';
      if (action === 'Comprar' || action === 'Aumentar') actionClass = 'action-buy';
      else if (action === 'Vender' || action === 'Reduzir') actionClass = 'action-sell';

      return `<tr>
        <td>${(t.symbol || t.stock || '').replace('.SA', '')}</td>
        <td>${currentPct}</td>
        <td>${targetPct}</td>
        <td>${diffPct}</td>
        <td class="${actionClass}">${action}</td>
      </tr>`;
    }).join('');
  }

  function renderRisk() {
    setText('riskSharpe', fmt(MODEL.risk.sharpe, 'num'));
    setText('riskVolatility', fmt(MODEL.risk.volatility_annual, 'pct'));
    setText('riskTE', 'N/A'); // Tracking Error not available in MODEL
    setText('riskIR', 'N/A'); // Information Ratio not available in MODEL
    setText('riskHHI', fmt(MODEL.risk.hhi_ideal, 'num4'));
    setText('riskTop5', MODEL.risk.top5_ideal != null ? fmt(MODEL.risk.top5_ideal * 100, 'pct1') : 'N/A');

    // Correlation matrix - show "not available" (no placeholder data)
    const correlationContent = document.getElementById('correlationContent');
    if (correlationContent) {
      correlationContent.innerHTML = `<p style="color: var(--muted); text-align: center; padding: 20px;">
        Matriz de correlação não disponível
      </p>`;
    }
  }

  function renderDiagnostics() {
    setText('diagHistReturn', fmt(MODEL.returns.historical_annual, 'pct'));

    const diagSharpe = document.getElementById('diagSharpe');
    if (diagSharpe) {
      diagSharpe.innerHTML = MODEL.risk.sharpe != null
        ? `${fmt(MODEL.risk.sharpe, 'num')} <span style="font-size:9px;color:var(--muted);">(${MODEL.risk.sharpe_source || 'backtest'})</span>`
        : 'N/A';
    }

    setText('diagTurnover', fmt(MODEL.costs.turnover_pct, 'pct1'));

    // Regime badge
    const regimeBadge = document.getElementById('regimeBadge');
    if (regimeBadge) {
      const regime = MODEL.regime.detected;
      if (regime) {
        let regimeClass = 'regime-neutral';
        if (regime === 'BULL') regimeClass = 'regime-bull';
        else if (regime === 'BEAR') regimeClass = 'regime-bear';
        regimeBadge.textContent = regime;
        regimeBadge.className = 'regime-badge ' + regimeClass;
      } else {
        regimeBadge.textContent = 'N/A';
        regimeBadge.className = 'regime-badge';
      }
    }

    // Profile badge
    const profileBadge = document.getElementById('profileBadge');
    if (profileBadge) {
      const profile = MODEL.scoring.profile != null ? MODEL.scoring.profile.toUpperCase() : null;
      if (profile) {
        let profileClass = 'profile-moderate';
        if (profile === 'CONSERVADOR') profileClass = 'profile-conservative';
        else if (profile === 'AGRESSIVO') profileClass = 'profile-aggressive';
        profileBadge.textContent = profile;
        profileBadge.className = 'profile-badge ' + profileClass;
      } else {
        profileBadge.textContent = 'N/A';
        profileBadge.className = 'profile-badge';
      }
    }

    // Scoring weights
    const scoringWeights = document.getElementById('scoringWeights');
    if (scoringWeights) {
      const sw = MODEL.scoring.weights;
      if (sw) {
        const ret = (sw.expected_return ?? sw.weight_expected_return) != null ? (sw.expected_return ?? sw.weight_expected_return) * 100 : null;
        const sharpe = (sw.sharpe_ratio ?? sw.weight_sharpe_ratio) != null ? (sw.sharpe_ratio ?? sw.weight_sharpe_ratio) * 100 : null;
        const mom = (sw.momentum ?? sw.weight_momentum) != null ? (sw.momentum ?? sw.weight_momentum) * 100 : null;
        scoringWeights.innerHTML = `
          <div class="weight-chip"><span class="weight-chip-label">Ret:</span><span class="weight-chip-value">${ret != null ? ret.toFixed(0) + '%' : 'N/A'}</span></div>
          <div class="weight-chip"><span class="weight-chip-label">Sharpe:</span><span class="weight-chip-value">${sharpe != null ? sharpe.toFixed(0) + '%' : 'N/A'}</span></div>
          <div class="weight-chip"><span class="weight-chip-label">Mom:</span><span class="weight-chip-value">${mom != null ? mom.toFixed(0) + '%' : 'N/A'}</span></div>
        `;
      } else {
        scoringWeights.innerHTML = '<span style="color: var(--muted);">N/A</span>';
      }
    }
  }

  function renderValuation() {
    setText('portfolioPE', fmt(MODEL.valuation.portfolio_pe, 'num'));
    setText('benchmarkPE', fmt(MODEL.valuation.benchmark_pe, 'num'));

    // Display P/E deviation from MODEL (no calculation)
    const peDeviation = document.getElementById('peDeviation');
    if (peDeviation) {
      const deviation = MODEL.valuation.pe_deviation_pct;
      if (deviation != null) {
        peDeviation.textContent = fmt(deviation, 'pct');
        peDeviation.style.color = deviation < 0 ? '#4CAF50' : '#f44336';
      } else {
        peDeviation.textContent = 'N/A';
        peDeviation.style.color = '';
      }
    }

    setText('divYield', fmt(MODEL.valuation.dividend_yield, 'pct'));

    const momentumSignal = document.getElementById('momentumSignal');
    if (momentumSignal) {
      momentumSignal.textContent = fmt(MODEL.valuation.momentum_signal, 'num');
      if (MODEL.valuation.momentum_signal != null) {
        momentumSignal.style.color = MODEL.valuation.momentum_signal > 0 ? '#4CAF50' : '#f44336';
      }
    }
  }

  function renderAssumptions() {
    const container = document.getElementById('assumptionsContent');
    if (!container) return;

    const a = MODEL.assumptions || {};

    container.innerHTML = `
      <div class="assumption-item">
        <span class="assumption-label">Horizonte Temporal:</span>
        <span class="assumption-value">${a.horizon_description ?? 'N/A'}</span>
      </div>
      <div class="assumption-item">
        <span class="assumption-label">Risk-Free Rate:</span>
        <span class="assumption-value">${a.risk_free_rate_annual != null ? (a.risk_free_rate_annual * 100).toFixed(2) + '% a.a.' : 'N/A'} (${a.risk_free_source ?? 'N/A'})</span>
      </div>
      <div class="assumption-item">
        <span class="assumption-label">Threshold Decisório:</span>
        <span class="assumption-value">${a.decision_threshold_pct != null ? 'Excess Return ≥ ' + a.decision_threshold_pct + '%' : 'N/A'}</span>
      </div>
      <div class="assumption-item">
        <span class="assumption-label">Fonte de Dados:</span>
        <span class="assumption-value">modelo.js (Single Source of Truth)</span>
      </div>
    `;
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // DOM HELPERS
  // ═══════════════════════════════════════════════════════════════════════════

  function setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
  }

  function setTextWithClass(id, value, className) {
    const el = document.getElementById(id);
    if (el) {
      el.textContent = value;
      el.className = 'decision-metric-value ' + (className || '');
    }
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // EVENT HANDLERS
  // ═══════════════════════════════════════════════════════════════════════════

  function setupEventHandlers() {
    const refreshBtn = document.getElementById('refreshBtn');
    if (refreshBtn) {
      refreshBtn.addEventListener('click', loadModel);
    }

    const assumptionsToggle = document.getElementById('assumptionsToggle');
    const assumptionsContent = document.getElementById('assumptionsContent');
    if (assumptionsToggle && assumptionsContent) {
      assumptionsToggle.addEventListener('click', () => {
        const isHidden = assumptionsContent.style.display === 'none' || assumptionsContent.style.display === '';
        assumptionsContent.style.display = isHidden ? 'block' : 'none';
        assumptionsToggle.textContent = isHidden ? '▼ Premissas do Modelo' : '▶ Premissas do Modelo';
      });
    }
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // INITIALIZATION
  // ═══════════════════════════════════════════════════════════════════════════

  function init() {
    setupEventHandlers();
    loadModel();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();

