/**
 * modelo.js - JavaScript for modelo.html
 * Painel Estratégico do Motor Quantitativo
 *
 * ARQUITETURA:
 * - Fonte Única de Verdade: normalize_model_output()
 * - Todos os blocos consomem o objeto normalizado
 * - Sem cálculos redundantes no front-end
 *
 * Consome:
 * - optimized_recommendation.json
 * - latest_run_summary.json
 * - pipeline_latest.json
 */

(function() {
  'use strict';

  // ═══════════════════════════════════════════════════════════════════════════
  // CONFIGURATION & MODEL ASSUMPTIONS
  // ═══════════════════════════════════════════════════════════════════════════

  const MODEL_ASSUMPTIONS = {
    // Horizonte temporal
    horizon_description: '12 meses (Forward 12M)',
    horizon_days: 252, // Trading days

    // Risk-free rate (SELIC aproximada anualizada)
    risk_free_rate_annual: 0.1175, // 11.75% a.a.
    risk_free_source: 'SELIC Meta (BCB)',

    // Método de Expected Return
    expected_return_method: 'Target Price Consensus (Forward P/E × EPS)',

    // Método de Volatilidade
    volatility_method: 'Rolling 252-day historical standard deviation (annualized)',

    // Regime Detection
    regime_detection_method: 'Momentum Signal threshold (>0.3 Bull, <-0.3 Bear)',
    regime_lookback_days: 60,

    // Decision Threshold
    decision_threshold_pct: 0.5, // Minimum excess return to recommend rebalance

    // Scoring Weights (default)
    scoring_weights: {
      expected_return: 0.4,
      sharpe_ratio: 0.4,
      momentum: 0.2
    },

    // Risk Profile
    risk_profile: 'moderado',
    profile_strength: 0.4
  };

  // ═══════════════════════════════════════════════════════════════════════════
  // DATA STORAGE
  // ═══════════════════════════════════════════════════════════════════════════

  let rawData = {
    optimized: null,
    latestRun: null,
    pipeline: null
  };

  // Normalized model output - SINGLE SOURCE OF TRUTH
  let MODEL = null;

  // ═══════════════════════════════════════════════════════════════════════════
  // DATA LOADING
  // ═══════════════════════════════════════════════════════════════════════════

  async function loadAllData() {
    try {
      const [optResp, latestResp, pipelineResp] = await Promise.all([
        fetch('./data/optimized_recommendation.json?_=' + Date.now()),
        fetch('./data/latest_run_summary.json?_=' + Date.now()),
        fetch('./data/pipeline_latest.json?_=' + Date.now())
      ]);

      if (optResp.ok) rawData.optimized = await optResp.json();
      if (latestResp.ok) rawData.latestRun = await latestResp.json();
      if (pipelineResp.ok) rawData.pipeline = await pipelineResp.json();

      // Normalize and consolidate all data
      MODEL = normalizeModelOutput(rawData);

      console.log('[modelo.js] Normalized MODEL:', MODEL);

      renderAll();
    } catch (err) {
      console.error('Error loading data:', err);
    }
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // NORMALIZE MODEL OUTPUT - SINGLE SOURCE OF TRUTH
  // ═══════════════════════════════════════════════════════════════════════════

  function normalizeModelOutput(raw) {
    const opt = raw.optimized || {};
    const latest = raw.latestRun || {};
    const pipeline = raw.pipeline || {};

    const comparison = opt.comparison || {};
    const holdings = comparison.holdings || {};
    const ideal = comparison.ideal || {};
    const optimal = comparison.optimal || {};
    const bestPortfolio = latest.best_portfolio_details || {};
    const momentumVal = bestPortfolio.momentum_valuation || {};

    // Update scoring weights from parameters if available
    if (opt.parameters) {
      MODEL_ASSUMPTIONS.scoring_weights.expected_return = opt.parameters.weight_expected_return || 0.4;
      MODEL_ASSUMPTIONS.scoring_weights.sharpe_ratio = opt.parameters.weight_sharpe_ratio || 0.4;
      MODEL_ASSUMPTIONS.scoring_weights.momentum = opt.parameters.weight_momentum || 0.2;
    }

    // Update decision threshold from data
    if (opt.min_threshold_pct != null) {
      MODEL_ASSUMPTIONS.decision_threshold_pct = opt.min_threshold_pct;
    }

    // ═══════════════════════════════════════════════════════════════════════
    // 1) UNIFIED RETURN CONCEPTS (Forward 12M)
    // ═══════════════════════════════════════════════════════════════════════

    // Holdings (current portfolio)
    const expected_return_hold_12m = holdings.expected_return_pct ?? 0;

    // Ideal (full model recommendation - GROSS)
    const expected_return_gross_12m = ideal.expected_return_pct ?? 0;

    // Historical return (backtest) - DIFFERENT CONCEPT
    const historical_return_annual = ideal.historical_return_pct ?? bestPortfolio.expected_return_annual_pct ?? 0;

    // Portfolio value
    const portfolio_total_value = holdings.total_value || 0;

    // ═══════════════════════════════════════════════════════════════════════
    // 2) SHARPE RATIO CALCULATION (Consistent)
    // ═══════════════════════════════════════════════════════════════════════

    const expected_volatility_annual = bestPortfolio.expected_volatility_annual_pct ?? 0;
    const risk_free_rate_12m = MODEL_ASSUMPTIONS.risk_free_rate_annual * 100; // Convert to %

    // Calculate Sharpe from forward metrics (if we have volatility)
    let sharpe_forward_calculated = null;
    if (expected_volatility_annual > 0) {
      sharpe_forward_calculated = (expected_return_gross_12m - risk_free_rate_12m) / expected_volatility_annual;
    }

    // Sharpe from backtest (historical)
    const sharpe_backtest = ideal.sharpe_ratio ?? bestPortfolio.sharpe_ratio ?? null;

    // Use forward calculated if available and valid, otherwise backtest
    const sharpe_displayed = sharpe_forward_calculated ?? sharpe_backtest;
    const sharpe_source = sharpe_forward_calculated != null ? 'forward' : 'backtest';

    // ═══════════════════════════════════════════════════════════════════════
    // 3) WEIGHT VECTORS (Current and Full Model)
    // ═══════════════════════════════════════════════════════════════════════

    // Current holdings weights
    const weights_current = normalizeWeights(holdings.weights || {});

    // Full model target weights (ideal - 100% model)
    const weights_target_full_model = normalizeWeights(ideal.weights || {});

    // ═══════════════════════════════════════════════════════════════════════
    // 4) THEORETICAL COSTS (For decision calculation - assumes 100% intensity)
    // ═══════════════════════════════════════════════════════════════════════

    const transaction_cost_rate = opt.transaction_cost_pct_used || 0.0003; // Cost per BRL traded
    const decision_threshold = MODEL_ASSUMPTIONS.decision_threshold_pct;
    const intensity_theoretical = (optimal.blend_ratio ?? 0) * 100;

    // Calculate theoretical turnover (if we migrate 100% to model)
    const allStocksTheoretical = new Set([
      ...Object.keys(weights_current),
      ...Object.keys(weights_target_full_model)
    ]);

    let totalWeightChangeTheoretical = 0;
    allStocksTheoretical.forEach(stock => {
      const currentW = weights_current[stock] || 0;
      const targetW = weights_target_full_model[stock] || 0;
      totalWeightChangeTheoretical += Math.abs(targetW - currentW);
    });

    const turnover_pct_theoretical = totalWeightChangeTheoretical / 2;
    const gross_turnover_theoretical = turnover_pct_theoretical * portfolio_total_value;
    const cost_theoretical = gross_turnover_theoretical * transaction_cost_rate;
    const cost_pct_on_portfolio_theoretical = portfolio_total_value > 0
      ? (cost_theoretical / portfolio_total_value) * 100
      : 0;

    // ═══════════════════════════════════════════════════════════════════════
    // 5) DECISION CALCULATION (Based on theoretical costs)
    // ═══════════════════════════════════════════════════════════════════════

    // NET return = GROSS return - theoretical cost impact
    const expected_return_net_12m = expected_return_gross_12m - cost_pct_on_portfolio_theoretical;

    // UNIFIED Excess return (NET vs HOLD) - SINGLE SOURCE OF TRUTH
    const excess_return_net_12m = expected_return_net_12m - expected_return_hold_12m;

    // Decision is based EXCLUSIVELY on excess_return_net_12m vs threshold
    const decision = excess_return_net_12m > decision_threshold ? 'REBALANCE' : 'HOLD';

    // Reason is constructed using the SAME calculated value
    const decision_reason = decision === 'HOLD'
      ? `Excess return (${excess_return_net_12m >= 0 ? '+' : ''}${excess_return_net_12m.toFixed(2)}%) below threshold (${decision_threshold}%)`
      : `Excess return (${excess_return_net_12m >= 0 ? '+' : ''}${excess_return_net_12m.toFixed(2)}%) exceeds threshold (${decision_threshold}%)`;

    // Applied intensity (must be 0 if decision is HOLD)
    const intensity_applied = decision === 'HOLD' ? 0 : intensity_theoretical;

    // ═══════════════════════════════════════════════════════════════════════
    // 6) ACTUAL WEIGHTS & COSTS (Based on applied intensity)
    // ═══════════════════════════════════════════════════════════════════════

    // Calculate weights_target_after_intensity
    // If intensity_applied = 0 (HOLD), then weights_target_after_intensity = weights_current
    const weights_target_after_intensity = calculateBlendedWeights(
      weights_current,
      weights_target_full_model,
      intensity_applied / 100 // Convert to 0-1 scale
    );

    // Calculate actual turnover based on applied weights
    let gross_turnover_value_applied = 0;
    let turnover_pct_applied = 0;

    if (intensity_applied > 0) {
      const allStocks = new Set([
        ...Object.keys(weights_current),
        ...Object.keys(weights_target_after_intensity)
      ]);

      let totalWeightChange = 0;
      allStocks.forEach(stock => {
        const currentW = weights_current[stock] || 0;
        const targetW = weights_target_after_intensity[stock] || 0;
        totalWeightChange += Math.abs(targetW - currentW);
      });

      turnover_pct_applied = totalWeightChange / 2;
      gross_turnover_value_applied = turnover_pct_applied * portfolio_total_value;
    }
    // If HOLD (intensity_applied = 0), turnover stays at 0

    const transition_cost_total_value_applied = gross_turnover_value_applied * transaction_cost_rate;

    // Cost percentages (based on applied values)
    const transition_cost_pct_on_turnover = gross_turnover_value_applied > 0
      ? transition_cost_total_value_applied / gross_turnover_value_applied
      : 0;

    const transition_cost_pct_on_portfolio_total = portfolio_total_value > 0
      ? transition_cost_total_value_applied / portfolio_total_value
      : 0;


    // ═══════════════════════════════════════════════════════════════════════
    // BUILD NORMALIZED MODEL OBJECT
    // ═══════════════════════════════════════════════════════════════════════

    return {
      // Meta
      meta: {
        run_id: latest.last_updated_run_id || opt.comparison?.ideal?.run_id || '—',
        timestamp: latest.last_updated_timestamp || opt.timestamp || '—',
        date: opt.date || '—'
      },

      // Returns (Forward 12M) - UNIFIED CONCEPTS
      returns: {
        // Holdings (what you currently hold)
        hold_12m: expected_return_hold_12m,

        // Ideal portfolio (model recommendation)
        gross_12m: expected_return_gross_12m,
        net_12m: expected_return_net_12m,

        // Historical backtest (DIFFERENT from forward)
        historical_annual: historical_return_annual,

        // UNIFIED Excess return - SINGLE SOURCE OF TRUTH
        excess_net_12m: excess_return_net_12m
      },

      // Risk metrics
      risk: {
        volatility_annual: expected_volatility_annual,
        risk_free_annual: risk_free_rate_12m,
        sharpe: sharpe_displayed,
        sharpe_source: sharpe_source, // 'forward' or 'backtest'

        // Concentration
        hhi_current: calculateHHI(weights_current),
        hhi_ideal: bestPortfolio.concentration_risk?.hhi ?? calculateHHI(weights_target_full_model),
        top5_current: calculateTop5(weights_current),
        top5_ideal: bestPortfolio.concentration_risk?.top_5_holdings_pct ?? calculateTop5(weights_target_full_model)
      },

      // Transition costs - Based on APPLIED intensity (0 if HOLD)
      costs: {
        turnover_pct: turnover_pct_applied * 100, // As percentage
        gross_turnover_value: gross_turnover_value_applied,
        total_cost_brl: transition_cost_total_value_applied,
        cost_pct_on_turnover: transition_cost_pct_on_turnover * 100,
        cost_pct_on_portfolio: transition_cost_pct_on_portfolio_total * 100,
        cost_rate_per_trade: transaction_cost_rate * 100
      },

      // Portfolio values
      portfolio: {
        total_value: portfolio_total_value,
        total_invested: holdings.total_invested || 0,
        stocks_current: holdings.stocks || [],
        stocks_ideal: ideal.stocks || [],
        stocks_optimal: optimal.stocks || []
      },

      // Weights (all normalized to sum = 100%)
      weights: {
        current: weights_current,
        target_full_model: weights_target_full_model,
        target_after_intensity: weights_target_after_intensity
      },

      // Decision
      decision: {
        verdict: decision,
        reason: decision_reason,
        threshold_pct: decision_threshold,
        intensity_theoretical: intensity_theoretical,
        intensity_applied: intensity_applied
      },

      // Transactions - Applied (respects HOLD decision)
      transactions_applied: buildNormalizedTransactions(
        weights_current,
        weights_target_after_intensity,
        portfolio_total_value
      ),

      // Transactions - Theoretical (100% model, for "Ver rebalanceamento teórico")
      transactions_theoretical: buildNormalizedTransactions(
        weights_current,
        weights_target_full_model,
        portfolio_total_value
      ),

      // Valuation & Momentum
      valuation: {
        portfolio_pe: momentumVal.portfolio_forward_pe ?? bestPortfolio.portfolio_weighted_pe ?? null,
        benchmark_pe: momentumVal.benchmark_forward_pe ?? null,
        dividend_yield: momentumVal.portfolio_dividend_yield ?? null,
        momentum_signal: momentumVal.portfolio_momentum ?? null
      },

      // Regime & Profile
      regime: {
        detected: detectRegime(momentumVal.portfolio_momentum),
        momentum_value: momentumVal.portfolio_momentum ?? 0
      },

      // Scoring
      scoring: {
        weights: MODEL_ASSUMPTIONS.scoring_weights,
        profile: MODEL_ASSUMPTIONS.risk_profile,
        profile_strength: MODEL_ASSUMPTIONS.profile_strength
      },

      // Model Assumptions (for transparency)
      assumptions: MODEL_ASSUMPTIONS
    };
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // HELPER FUNCTIONS
  // ═══════════════════════════════════════════════════════════════════════════

  function normalizeWeights(weightsObj) {
    const entries = Object.entries(weightsObj);
    if (entries.length === 0) return {};

    // Calculate sum
    const sum = entries.reduce((s, [_, w]) => s + w, 0);
    if (sum === 0) return weightsObj;

    // Normalize to sum = 1.0
    const normalized = {};
    entries.forEach(([stock, w]) => {
      normalized[stock] = w / sum;
    });

    return normalized;
  }

  /**
   * Calculate blended weights based on intensity
   * weights_blended = weights_current + intensity * (weights_target - weights_current)
   * If intensity = 0, returns weights_current
   */
  function calculateBlendedWeights(weightsCurrent, weightsTarget, intensity) {
    if (intensity === 0) {
      return { ...weightsCurrent };
    }

    // Get all unique stocks
    const allStocks = new Set([
      ...Object.keys(weightsCurrent),
      ...Object.keys(weightsTarget)
    ]);

    const blended = {};
    allStocks.forEach(stock => {
      const current = weightsCurrent[stock] || 0;
      const target = weightsTarget[stock] || 0;
      blended[stock] = current + intensity * (target - current);
    });

    // Normalize to ensure sum = 1.0
    return normalizeWeights(blended);
  }

  function calculateHHI(weights) {
    const vals = Object.values(weights);
    if (vals.length === 0) return null;
    return vals.reduce((sum, w) => sum + w * w, 0);
  }

  function calculateTop5(weights) {
    const vals = Object.values(weights).sort((a, b) => b - a);
    if (vals.length === 0) return null;
    return vals.slice(0, 5).reduce((s, v) => s + v, 0);
  }

  function detectRegime(momentum) {
    if (momentum == null) return 'NEUTRAL';
    if (momentum > 0.3) return 'BULL';
    if (momentum < -0.3) return 'BEAR';
    return 'NEUTRAL';
  }

  /**
   * Build transactions from weight differences
   * @param {Object} weightsCurrent - Current portfolio weights
   * @param {Object} weightsTarget - Target portfolio weights
   * @param {number} portfolioValue - Total portfolio value in BRL
   * @returns {Array} Array of transaction objects
   */
  function buildNormalizedTransactions(weightsCurrent, weightsTarget, portfolioValue) {
    // Get all unique stocks
    const allStocks = new Set([
      ...Object.keys(weightsCurrent),
      ...Object.keys(weightsTarget)
    ]);

    const transactions = [];

    allStocks.forEach(stock => {
      const currentW = weightsCurrent[stock] || 0;
      const targetW = weightsTarget[stock] || 0;
      const weightChange = targetW - currentW;

      // Only include if there's a meaningful change (> 0.01%)
      if (Math.abs(weightChange) > 0.0001) {
        transactions.push({
          symbol: stock,
          action: weightChange > 0 ? 'BUY' : 'SELL',
          current_weight: currentW,
          target_weight: targetW,
          weight_change: weightChange,
          value_change: Math.abs(weightChange) * portfolioValue
        });
      }
    });

    // Sort by absolute weight change (largest first)
    return transactions.sort((a, b) => Math.abs(b.weight_change) - Math.abs(a.weight_change));
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // RENDERING FUNCTIONS (All consume MODEL)
  // ═══════════════════════════════════════════════════════════════════════════

  function renderAll() {
    if (!MODEL) return;

    renderRunInfo();
    renderDecision();
    renderComparison();
    renderPortfolio();
    renderTurnoverCosts();
    renderDiagnostics();
    renderValuation();
    renderAssumptions();
  }

  function renderRunInfo() {
    document.getElementById('runId').textContent = MODEL.meta.run_id;
    document.getElementById('lastUpdated').textContent = MODEL.meta.timestamp;
  }

  function renderDecision() {
    const card = document.getElementById('decisao');
    const verdictEl = document.getElementById('decisionVerdict');
    const reasonEl = document.getElementById('decisionReason');

    const isRebalance = MODEL.decision.verdict === 'REBALANCE';
    card.classList.remove('decision-hold', 'decision-rebalance');
    card.classList.add(isRebalance ? 'decision-rebalance' : 'decision-hold');

    verdictEl.textContent = MODEL.decision.verdict;
    verdictEl.className = 'decision-verdict ' + (isRebalance ? 'rebalance' : 'hold');
    reasonEl.textContent = MODEL.decision.reason;

    // Retorno Ideal (NET) - Forward 12M
    const idealReturnEl = document.getElementById('idealReturn');
    idealReturnEl.textContent = formatReturn(MODEL.returns.net_12m);
    idealReturnEl.className = 'decision-metric-value ' + (MODEL.returns.net_12m > 0 ? 'positive' : 'negative');

    // Retorno Hold - Forward 12M
    const holdReturnEl = document.getElementById('holdReturn');
    holdReturnEl.textContent = formatReturn(MODEL.returns.hold_12m);
    holdReturnEl.className = 'decision-metric-value ' + (MODEL.returns.hold_12m > 0 ? 'positive' : 'neutral');

    // Excess Return (NET) - SINGLE SOURCE OF TRUTH
    const excessReturnEl = document.getElementById('excessReturn');
    excessReturnEl.textContent = formatReturn(MODEL.returns.excess_net_12m);
    excessReturnEl.className = 'decision-metric-value ' + (MODEL.returns.excess_net_12m > 0 ? 'positive' : 'negative');

    // Custo de Transição (% sobre portfolio total)
    const transitionCostPctEl = document.getElementById('transitionCostPct');
    transitionCostPctEl.textContent = `-${MODEL.costs.cost_pct_on_portfolio.toFixed(3)}%`;
    transitionCostPctEl.className = 'decision-metric-value neutral';

    // Custo de Transição (BRL)
    const transitionCostBRLEl = document.getElementById('transitionCostBRL');
    transitionCostBRLEl.textContent = `R$ ${MODEL.costs.total_cost_brl.toFixed(2)}`;
    transitionCostBRLEl.className = 'decision-metric-value neutral';

    // Intensidade Aplicada (0 if HOLD)
    const blendRatioEl = document.getElementById('blendRatio');
    blendRatioEl.textContent = `${MODEL.decision.intensity_applied.toFixed(0)}%`;
    blendRatioEl.className = 'decision-metric-value neutral';
  }

  function formatReturn(value) {
    if (value == null) return '—';
    const sign = value >= 0 ? '+' : '';
    return `${sign}${value.toFixed(2)}%`;
  }

  function renderComparison() {
    const tbody = document.getElementById('comparisonBody');

    const metrics = [
      {
        label: 'Expected Return (Forward 12M) - Bruto',
        hold: MODEL.returns.hold_12m,
        ideal: MODEL.returns.gross_12m,
        format: v => v != null ? `${v.toFixed(2)}%` : '—',
        higherBetter: true
      },
      {
        label: 'Expected Return (Forward 12M) - Líquido',
        hold: MODEL.returns.hold_12m, // Hold has no transition cost
        ideal: MODEL.returns.net_12m,
        format: v => v != null ? `${v.toFixed(2)}%` : '—',
        higherBetter: true
      },
      {
        label: `Sharpe Ratio (${MODEL.risk.sharpe_source === 'forward' ? 'Forward' : 'Backtest'})`,
        hold: null,
        ideal: MODEL.risk.sharpe,
        format: v => v != null ? v.toFixed(2) : '—',
        higherBetter: true
      },
      {
        label: 'Volatilidade Esperada (Ann.)',
        hold: null,
        ideal: MODEL.risk.volatility_annual,
        format: v => v != null ? `${v.toFixed(2)}%` : '—',
        higherBetter: false
      },
      {
        label: 'Retorno Histórico (Backtest Ann.)',
        hold: null,
        ideal: MODEL.returns.historical_annual,
        format: v => v != null ? `${v.toFixed(2)}%` : '—',
        higherBetter: true,
        note: 'backtest'
      },
      {
        label: 'HHI (Concentração)',
        hold: MODEL.risk.hhi_current,
        ideal: MODEL.risk.hhi_ideal,
        format: v => v != null ? v.toFixed(4) : '—',
        higherBetter: false
      },
      {
        label: 'Top 5 Holdings %',
        hold: MODEL.risk.top5_current,
        ideal: MODEL.risk.top5_ideal,
        format: v => v != null ? `${(v * 100).toFixed(1)}%` : '—',
        higherBetter: false
      },
      {
        label: 'Qtd. Ações',
        hold: MODEL.portfolio.stocks_current.length,
        ideal: MODEL.portfolio.stocks_ideal.length,
        format: v => v != null ? v : '—',
        higherBetter: null
      }
    ];

    tbody.innerHTML = metrics.map(m => {
      const holdVal = m.format(m.hold);
      const idealVal = m.format(m.ideal);

      let holdClass = '';
      let idealClass = '';

      if (m.higherBetter !== null && m.hold != null && m.ideal != null) {
        if (m.higherBetter) {
          holdClass = m.hold > m.ideal ? 'better' : (m.hold < m.ideal ? 'worse' : '');
          idealClass = m.ideal > m.hold ? 'better' : (m.ideal < m.hold ? 'worse' : '');
        } else {
          holdClass = m.hold < m.ideal ? 'better' : (m.hold > m.ideal ? 'worse' : '');
          idealClass = m.ideal < m.hold ? 'better' : (m.ideal > m.hold ? 'worse' : '');
        }
      }

      const noteHtml = m.note ? ` <span style="font-size:9px;color:var(--muted);">(${m.note})</span>` : '';

      return `<tr>
        <td>${m.label}${noteHtml}</td>
        <td class="${holdClass}">${holdVal}</td>
        <td class="${idealClass}">${idealVal}</td>
      </tr>`;
    }).join('');
  }

  function renderPortfolio() {
    // Use weights_target_after_intensity for consistency with transactions
    const weights = MODEL.decision.verdict === 'HOLD'
      ? MODEL.weights.target_full_model  // Show full model if HOLD
      : MODEL.weights.target_after_intensity;

    const stocks = Object.keys(weights);
    const pipelineRows = rawData.pipeline?.rows || [];
    const stockData = {};
    pipelineRows.forEach(r => { stockData[r.ticker] = r; });

    const portfolioItems = stocks.map(stock => {
      const weight = weights[stock] || 0;
      const data = stockData[stock] || {};
      return {
        ticker: stock,
        weight: weight,
        current: data.current || null,
        target: data.target || null,
        upside: data.current && data.target ? ((data.target / data.current - 1) * 100) : null
      };
    }).sort((a, b) => b.weight - a.weight);

    // Verify sum = 100%
    const sumWeights = portfolioItems.reduce((s, item) => s + item.weight, 0);
    console.log(`[modelo.js] Portfolio weights sum: ${(sumWeights * 100).toFixed(4)}%`);

    // Render horizontal bars
    const barsContainer = document.getElementById('weightBars');
    barsContainer.innerHTML = portfolioItems.slice(0, 10).map(item => {
      const pct = (item.weight * 100).toFixed(1);
      const widthPct = Math.min(item.weight * 100 / 25 * 100, 100);
      return `<div class="h-bar-row">
        <div class="h-bar-label">${item.ticker.replace('.SA', '')}</div>
        <div class="h-bar-track">
          <div class="h-bar-fill" style="width: ${widthPct}%">${pct}%</div>
        </div>
      </div>`;
    }).join('');

    // Render table
    const tbody = document.getElementById('portfolioBody');
    tbody.innerHTML = portfolioItems.map(item => {
      const weightPct = (item.weight * 100).toFixed(2) + '%';
      const current = item.current != null ? `R$ ${item.current.toFixed(2)}` : '—';
      const target = item.target != null ? `R$ ${item.target.toFixed(2)}` : '—';
      const upside = item.upside != null ? `${item.upside >= 0 ? '+' : ''}${item.upside.toFixed(1)}%` : '—';
      const upsideStyle = item.upside != null ? (item.upside > 0 ? 'style="color:#4CAF50"' : 'style="color:#f44336"') : '';

      return `<tr>
        <td>${item.ticker}</td>
        <td>${weightPct}</td>
        <td>—</td>
        <td>${current}</td>
        <td>${target}</td>
        <td ${upsideStyle}>${upside}</td>
      </tr>`;
    }).join('');
  }

  function renderTurnoverCosts() {
    // Turnover metrics (will be 0 if HOLD)
    document.getElementById('turnoverPct').textContent = `${MODEL.costs.turnover_pct.toFixed(1)}%`;
    document.getElementById('turnoverBRL').textContent = `R$ ${MODEL.costs.gross_turnover_value.toFixed(2)}`;
    document.getElementById('costBRL').textContent = `R$ ${MODEL.costs.total_cost_brl.toFixed(2)}`;
    document.getElementById('costPct').textContent = `${MODEL.costs.cost_pct_on_turnover.toFixed(4)}%`;

    // Blend ratio gauge - use APPLIED intensity (0 if HOLD)
    const markerEl = document.getElementById('blendMarker');
    markerEl.style.left = `${MODEL.decision.intensity_applied}%`;

    // Show both theoretical and applied if different
    const blendLargeEl = document.getElementById('blendRatioLarge');
    if (MODEL.decision.verdict === 'HOLD' && MODEL.decision.intensity_theoretical > 0) {
      blendLargeEl.innerHTML = `<span style="text-decoration:line-through;color:var(--muted);font-size:16px;">${MODEL.decision.intensity_theoretical.toFixed(0)}%</span> → 0%`;
    } else {
      blendLargeEl.textContent = `${MODEL.decision.intensity_applied.toFixed(0)}%`;
    }

    // Transactions table - uses transactions_applied (respects HOLD decision)
    const tbody = document.getElementById('transactionsBody');
    const transactions = MODEL.transactions_applied;

    // If HOLD and no transactions, show message
    if (MODEL.decision.verdict === 'HOLD' || transactions.length === 0) {
      tbody.innerHTML = `<tr>
        <td colspan="6" style="text-align:center;color:var(--muted);padding:24px;">
          <div style="margin-bottom:8px;">Sem transações recomendadas — decisão <strong style="color:#4fc3f7;">HOLD</strong></div>
          <button id="showTheoreticalBtn" style="background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.1);color:var(--muted);padding:6px 12px;border-radius:6px;cursor:pointer;font-size:11px;">
            Ver rebalanceamento teórico (100% modelo)
          </button>
        </td>
      </tr>`;

      // Add event listener for theoretical button
      setTimeout(() => {
        const btn = document.getElementById('showTheoreticalBtn');
        if (btn) {
          btn.addEventListener('click', () => {
            renderTheoreticalTransactions(tbody);
          });
        }
      }, 0);
    } else {
      // Render actual transactions
      tbody.innerHTML = transactions.map(t => {
        const actionClass = t.action === 'BUY' ? 'action-buy' : 'action-sell';
        const currentW = (t.current_weight * 100).toFixed(2) + '%';
        const targetW = (t.target_weight * 100).toFixed(2) + '%';
        const changeSign = t.weight_change >= 0 ? '+' : '';
        const changeW = `${changeSign}${(t.weight_change * 100).toFixed(2)}%`;
        const valueBRL = `R$ ${Math.abs(t.value_change).toFixed(2)}`;

        return `<tr>
          <td>${t.symbol}</td>
          <td class="${actionClass}">${t.action}</td>
          <td>${currentW}</td>
          <td>${targetW}</td>
          <td>${changeW}</td>
          <td>${valueBRL}</td>
        </tr>`;
      }).join('');
    }
  }

  function renderTheoreticalTransactions(tbody) {
    const transactions = MODEL.transactions_theoretical;

    if (transactions.length === 0) {
      tbody.innerHTML = `<tr>
        <td colspan="6" style="text-align:center;color:var(--muted);padding:24px;">
          Nenhuma transação teórica (portfolio atual = portfolio ideal)
        </td>
      </tr>`;
      return;
    }

    const headerRow = `<tr style="background:rgba(255,193,7,0.1);">
      <td colspan="6" style="text-align:center;color:#FFC107;padding:8px;font-size:11px;">
        ⚠ TEÓRICO — Transações se 100% do modelo fosse aplicado
        <button id="hideTheoreticalBtn" style="margin-left:12px;background:transparent;border:1px solid rgba(255,193,7,0.3);color:#FFC107;padding:3px 8px;border-radius:4px;cursor:pointer;font-size:10px;">
          Ocultar
        </button>
      </td>
    </tr>`;

    const rows = transactions.map(t => {
      const actionClass = t.action === 'BUY' ? 'action-buy' : 'action-sell';
      const currentW = (t.current_weight * 100).toFixed(2) + '%';
      const targetW = (t.target_weight * 100).toFixed(2) + '%';
      const changeSign = t.weight_change >= 0 ? '+' : '';
      const changeW = `${changeSign}${(t.weight_change * 100).toFixed(2)}%`;
      const valueBRL = `R$ ${Math.abs(t.value_change).toFixed(2)}`;

      return `<tr style="opacity:0.7;">
        <td>${t.symbol}</td>
        <td class="${actionClass}">${t.action}</td>
        <td>${currentW}</td>
        <td>${targetW}</td>
        <td>${changeW}</td>
        <td>${valueBRL}</td>
      </tr>`;
    }).join('');

    tbody.innerHTML = headerRow + rows;

    // Add event listener to hide button
    setTimeout(() => {
      const btn = document.getElementById('hideTheoreticalBtn');
      if (btn) {
        btn.addEventListener('click', () => {
          renderTurnoverCosts(); // Re-render with HOLD message
        });
      }
    }, 0);
  }

  function renderDiagnostics() {
    // Sharpe with source label
    const sharpeEl = document.getElementById('diagSharpe');
    if (MODEL.risk.sharpe != null) {
      sharpeEl.innerHTML = `${MODEL.risk.sharpe.toFixed(2)} <span style="font-size:9px;color:var(--muted);">(${MODEL.risk.sharpe_source})</span>`;
    } else {
      sharpeEl.textContent = '—';
    }

    // Historical return (backtest)
    const histReturnEl = document.getElementById('diagHistReturn');
    histReturnEl.textContent = MODEL.returns.historical_annual != null
      ? `${MODEL.returns.historical_annual.toFixed(2)}%`
      : '—';

    // Volatility
    const volEl = document.getElementById('diagVolatility');
    volEl.textContent = MODEL.risk.volatility_annual != null
      ? `${MODEL.risk.volatility_annual.toFixed(2)}%`
      : '—';

    // Model turnover
    document.getElementById('diagTurnover').textContent = `${MODEL.costs.turnover_pct.toFixed(1)}%`;

    // Regime badge
    const regimeBadge = document.getElementById('regimeBadge');
    const regime = MODEL.regime.detected;
    let regimeClass = 'regime-neutral';
    if (regime === 'BULL') regimeClass = 'regime-bull';
    else if (regime === 'BEAR') regimeClass = 'regime-bear';
    regimeBadge.textContent = regime;
    regimeBadge.className = 'regime-badge ' + regimeClass;

    // Profile badge
    const profileBadge = document.getElementById('profileBadge');
    const profile = MODEL.scoring.profile.toUpperCase();
    let profileClass = 'profile-moderate';
    if (profile === 'CONSERVADOR') profileClass = 'profile-conservative';
    else if (profile === 'AGRESSIVO') profileClass = 'profile-aggressive';
    profileBadge.textContent = profile;
    profileBadge.className = 'profile-badge ' + profileClass;

    // Scoring weights
    const weightsContainer = document.getElementById('scoringWeights');
    const sw = MODEL.scoring.weights;
    weightsContainer.innerHTML = `
      <div class="weight-chip">
        <span class="weight-chip-label">Retorno:</span>
        <span class="weight-chip-value">${(sw.expected_return * 100).toFixed(0)}%</span>
      </div>
      <div class="weight-chip">
        <span class="weight-chip-label">Sharpe:</span>
        <span class="weight-chip-value">${(sw.sharpe_ratio * 100).toFixed(0)}%</span>
      </div>
      <div class="weight-chip">
        <span class="weight-chip-label">Momentum:</span>
        <span class="weight-chip-value">${(sw.momentum * 100).toFixed(0)}%</span>
      </div>
    `;
  }

  function renderValuation() {
    // Portfolio P/E
    document.getElementById('portfolioPE').textContent = MODEL.valuation.portfolio_pe != null
      ? MODEL.valuation.portfolio_pe.toFixed(2)
      : '—';

    // Benchmark P/E
    document.getElementById('benchmarkPE').textContent = MODEL.valuation.benchmark_pe != null
      ? MODEL.valuation.benchmark_pe.toFixed(2)
      : '—';

    // P/E Deviation
    const devEl = document.getElementById('peDeviation');
    if (MODEL.valuation.portfolio_pe != null && MODEL.valuation.benchmark_pe != null && MODEL.valuation.benchmark_pe !== 0) {
      const deviation = ((MODEL.valuation.portfolio_pe / MODEL.valuation.benchmark_pe - 1) * 100);
      devEl.textContent = `${deviation >= 0 ? '+' : ''}${deviation.toFixed(1)}%`;
      devEl.style.color = deviation < 0 ? '#4CAF50' : '#f44336';
    } else {
      devEl.textContent = '—';
    }

    // Dividend Yield
    document.getElementById('divYield').textContent = MODEL.valuation.dividend_yield != null
      ? `${MODEL.valuation.dividend_yield.toFixed(2)}%`
      : '—';

    // Momentum Signal
    const momEl = document.getElementById('momentumSignal');
    if (MODEL.valuation.momentum_signal != null) {
      momEl.textContent = MODEL.valuation.momentum_signal.toFixed(2);
      momEl.style.color = MODEL.valuation.momentum_signal > 0 ? '#4CAF50' : (MODEL.valuation.momentum_signal < 0 ? '#f44336' : '#fff');
    } else {
      momEl.textContent = '—';
    }

    // HHI
    document.getElementById('hhiValue').textContent = MODEL.risk.hhi_ideal != null
      ? MODEL.risk.hhi_ideal.toFixed(4)
      : '—';
  }

  function renderAssumptions() {
    const container = document.getElementById('assumptionsContent');
    if (!container) return;

    const a = MODEL.assumptions;

    container.innerHTML = `
      <div class="assumption-item">
        <span class="assumption-label">Horizonte Temporal:</span>
        <span class="assumption-value">${a.horizon_description}</span>
      </div>
      <div class="assumption-item">
        <span class="assumption-label">Método Expected Return:</span>
        <span class="assumption-value">${a.expected_return_method}</span>
      </div>
      <div class="assumption-item">
        <span class="assumption-label">Método Volatilidade:</span>
        <span class="assumption-value">${a.volatility_method}</span>
      </div>
      <div class="assumption-item">
        <span class="assumption-label">Risk-Free Rate:</span>
        <span class="assumption-value">${(a.risk_free_rate_annual * 100).toFixed(2)}% a.a. (${a.risk_free_source})</span>
      </div>
      <div class="assumption-item">
        <span class="assumption-label">Regime Detection:</span>
        <span class="assumption-value">${a.regime_detection_method}</span>
      </div>
      <div class="assumption-item">
        <span class="assumption-label">Threshold Decisório:</span>
        <span class="assumption-value">Excess Return ≥ ${a.decision_threshold_pct}%</span>
      </div>
      <div class="assumption-item">
        <span class="assumption-label">Sharpe Calculado:</span>
        <span class="assumption-value">(Expected Return - Risk-Free) / Volatilidade</span>
      </div>
    `;
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // EVENT HANDLERS
  // ═══════════════════════════════════════════════════════════════════════════

  function setupEventHandlers() {
    const refreshBtn = document.getElementById('refreshBtn');
    if (refreshBtn) {
      refreshBtn.addEventListener('click', loadAllData);
    }

    // Collapsible assumptions section
    const assumptionsToggle = document.getElementById('assumptionsToggle');
    const assumptionsContent = document.getElementById('assumptionsContent');
    if (assumptionsToggle && assumptionsContent) {
      assumptionsToggle.addEventListener('click', () => {
        const isHidden = assumptionsContent.style.display === 'none';
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
    loadAllData();
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // EXPOSE MODEL GLOBALLY FOR OTHER PAGES (portfolio.html, etc.)
  // ═══════════════════════════════════════════════════════════════════════════

  // Expose MODEL as the single source of truth
  window.getPortfolioModel = function() {
    return MODEL;
  };

  // Expose loadAllData for external refresh
  window.loadPortfolioModel = loadAllData;

  // Expose MODEL_ASSUMPTIONS for transparency
  window.getModelAssumptions = function() {
    return MODEL_ASSUMPTIONS;
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();

