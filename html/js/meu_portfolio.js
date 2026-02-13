(function(){
  'use strict';

  // ═══════════════════════════════════════════════════════════════════════════
  // CONFIGURAÇÃO E PATHS
  // ═══════════════════════════════════════════════════════════════════════════
  const LEDGER_POSITIONS_PATH = './data/ledger_positions.json';
  const LEDGER_CSV_PATH = './data/ledger.csv';
  const SCORED_TARGETS_PATH = './data/scored_targets.json';
  const LATEST_RUN_PATH = './data/latest_run_summary.json';
  const PROCESSED_NOTES_PATH = './data/processed_notes.json';
  const PORTFOLIO_HISTORY_PATH = './data/portfolio_history.json';
  const OPTIMIZED_RECOMMENDATION_PATH = './data/optimized_recommendation.json';
  const PORTFOLIO_RESULTS_DB_PATH = './data/portfolio_results_db.csv';
  const TICKERS_PATH = './data/tickers.txt';
  const SCORED_STOCKS_CSV_PATH = './data/scored_stocks.csv';

  // ═══════════════════════════════════════════════════════════════════════════
  // UTILIDADES
  // ═══════════════════════════════════════════════════════════════════════════
  function formatCurrency(value) {
    if (value == null || isNaN(value)) return '—';
    return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(value);
  }

  function formatPercent(value, decimals = 1) {
    if (value == null || isNaN(value)) return '—';
    const sign = value >= 0 ? '+' : '';
    return sign + value.toFixed(decimals) + '%';
  }

  function formatNumber(value, decimals = 2) {
    if (value == null || isNaN(value)) return '—';
    return new Intl.NumberFormat('pt-BR', { minimumFractionDigits: decimals, maximumFractionDigits: decimals }).format(value);
  }

  function normalizeTickerKey(s) {
    if (!s) return '';
    return s.toUpperCase().replace(/[^A-Z0-9]/g, '');
  }

  function parseCSVLine(line) {
    const result = [];
    let current = '';
    let inQuotes = false;
    for (let i = 0; i < line.length; i++) {
      const ch = line[i];
      if (ch === '"') {
        inQuotes = !inQuotes;
      } else if (ch === ',' && !inQuotes) {
        result.push(current.trim());
        current = '';
      } else {
        current += ch;
      }
    }
    result.push(current.trim());
    return result;
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // CARREGAMENTO DE DADOS
  // ═══════════════════════════════════════════════════════════════════════════
  let positionsData = null;
  let transactionsData = [];
  let targetsData = {};
  let recommendedPortfolio = { stocks: [], weights: [], sharpe: null, expectedReturn: null };
  let processedNotesData = null;
  let portfolioHistoryData = null;
  let optimizedRecommendation = null;
  let portfolioResultsData = [];
  let scoredStocksHistory = [];  // Historical scored stocks data with CurrentPrice, TargetPrice per date
  let brokerNameToSymbol = {};  // Maps broker names (from tickers.txt) to symbols
  let allocationChart = null;
  let evolutionChart = null;
  let returnComparisonChart = null;

  async function loadAllData() {
    try {
      // Load positions
      const posResp = await fetch(LEDGER_POSITIONS_PATH + '?_=' + Date.now());
      if (posResp.ok) {
        positionsData = await posResp.json();
      }

      // Load targets
      const targetsResp = await fetch(SCORED_TARGETS_PATH + '?_=' + Date.now());
      if (targetsResp.ok) {
        const td = await targetsResp.json();
        targetsData = td.targets || td;
      }

      // Load recommended portfolio
      const recResp = await fetch(LATEST_RUN_PATH + '?_=' + Date.now());
      if (recResp.ok) {
        const recData = await recResp.json();
        const bp = recData.best_portfolio_details || {};
        recommendedPortfolio.stocks = bp.stocks || [];
        recommendedPortfolio.weights = bp.weights || [];
        recommendedPortfolio.sharpe = bp.sharpe_ratio || null;
        recommendedPortfolio.expectedReturn = bp.expected_return_annual_pct || null;
      }

      // Load processed notes info
      const notesResp = await fetch(PROCESSED_NOTES_PATH + '?_=' + Date.now());
      if (notesResp.ok) {
        processedNotesData = await notesResp.json();
      }

      // Load portfolio history
      const historyResp = await fetch(PORTFOLIO_HISTORY_PATH + '?_=' + Date.now());
      if (historyResp.ok) {
        portfolioHistoryData = await historyResp.json();
      }

      // Load optimized recommendation from C_OptimizedPortfolio
      const optResp = await fetch(OPTIMIZED_RECOMMENDATION_PATH + '?_=' + Date.now());
      if (optResp.ok) {
        optimizedRecommendation = await optResp.json();
      }

      // Load portfolio results history (ideal portfolio returns)
      const resultsResp = await fetch(PORTFOLIO_RESULTS_DB_PATH + '?_=' + Date.now());
      if (resultsResp.ok) {
        const csvText = await resultsResp.text();
        portfolioResultsData = parsePortfolioResultsCSV(csvText);
      }

      // Load scored_stocks.csv for historical CurrentPrice and TargetPrice per stock per run
      const scoredResp = await fetch(SCORED_STOCKS_CSV_PATH + '?_=' + Date.now());
      if (scoredResp.ok) {
        const csvText = await scoredResp.text();
        scoredStocksHistory = parseScoredStocksCSV(csvText);
      }

      // Load tickers.txt for BrokerName to Symbol mapping
      const tickersResp = await fetch(TICKERS_PATH + '?_=' + Date.now());
      if (tickersResp.ok) {
        const tickersText = await tickersResp.text();
        brokerNameToSymbol = parseTickersMapping(tickersText);
      }

      // Load transactions CSV
      const txResp = await fetch(LEDGER_CSV_PATH + '?_=' + Date.now());
      if (txResp.ok) {
        const csvText = await txResp.text();
        transactionsData = parseTransactionsCSV(csvText);
      }

      renderAll();
    } catch (err) {
      console.error('Error loading data:', err);
    }
  }

  function parseTransactionsCSV(csvText) {
    const lines = csvText.trim().split('\n');
    if (lines.length < 2) return [];

    const header = parseCSVLine(lines[0]);
    const indices = {
      date: header.findIndex(h => h.toLowerCase().includes('trade_date') || h.toLowerCase() === 'date'),
      ticker: header.findIndex(h => h.toLowerCase() === 'ticker' || h.toLowerCase() === 'symbol'),
      side: header.findIndex(h => h.toLowerCase() === 'side' || h.toLowerCase() === 'type'),
      qty: header.findIndex(h => h.toLowerCase() === 'quantity' || h.toLowerCase() === 'qty'),
      price: header.findIndex(h => h.toLowerCase() === 'unit_price' || h.toLowerCase() === 'price'),
      gross: header.findIndex(h => h.toLowerCase() === 'gross_value' || h.toLowerCase() === 'gross'),
      fees: header.findIndex(h => h.toLowerCase().includes('fees') || h.toLowerCase() === 'allocated_fees'),
      total: header.findIndex(h => h.toLowerCase() === 'total_cost' || h.toLowerCase() === 'total')
    };

    const transactions = [];
    for (let i = 1; i < lines.length; i++) {
      const row = parseCSVLine(lines[i]);
      if (row.length < 5) continue;

      transactions.push({
        date: row[indices.date] || '',
        ticker: row[indices.ticker] || '',
        side: (row[indices.side] || '').toUpperCase(),
        qty: parseFloat(row[indices.qty]) || 0,
        price: parseFloat(row[indices.price]) || 0,
        gross: parseFloat(row[indices.gross]) || 0,
        fees: parseFloat(row[indices.fees]) || 0,
        total: parseFloat(row[indices.total]) || 0
      });
    }

    // Sort by date descending (most recent first)
    transactions.sort((a, b) => b.date.localeCompare(a.date));
    return transactions;
  }

  function parsePortfolioResultsCSV(csvText) {
    const lines = csvText.trim().split('\n');
    if (lines.length < 2) return [];

    const header = parseCSVLine(lines[0]);

    // Find column indices
    const indices = {
      run_id: header.findIndex(h => h.toLowerCase() === 'run_id'),
      timestamp: header.findIndex(h => h.toLowerCase() === 'timestamp'),
      stocks: header.findIndex(h => h.toLowerCase() === 'stocks'),
      weights: header.findIndex(h => h.toLowerCase() === 'weights'),
      sharpe: header.findIndex(h => h.toLowerCase() === 'sharpe_ratio'),
      expectedReturn: header.findIndex(h => h.toLowerCase() === 'expected_return_annual_pct'),
      volatility: header.findIndex(h => h.toLowerCase() === 'expected_volatility_annual_pct')
    };

    const results = [];
    for (let i = 1; i < lines.length; i++) {
      const row = parseCSVLine(lines[i]);
      if (row.length < 5) continue;

      const timestamp = row[indices.timestamp] || '';
      const date = timestamp.split(' ')[0]; // Get just the date part

      // Handle inconsistent CSV structure:
      // Some rows have 12 columns (with final_value, roi_percent)
      // Some rows have 10 columns (without final_value, roi_percent)
      // We need to detect which format and adjust indices accordingly

      let expectedReturn = 0;
      let volatility = 0;
      let sharpe = 0;

      // Check if row has the expected number of columns
      if (row.length >= 12) {
        // Full format: use standard indices
        expectedReturn = parseFloat(row[indices.expectedReturn]) || 0;
        volatility = parseFloat(row[indices.volatility]) || 0;
        sharpe = parseFloat(row[indices.sharpe]) || 0;
      } else if (row.length >= 10) {
        // Short format (missing final_value and roi_percent)
        // expected_return is at index 8 (0-based), volatility at 9
        sharpe = parseFloat(row[7]) || 0;
        expectedReturn = parseFloat(row[8]) || 0;
        volatility = parseFloat(row[9]) || 0;
      }

      // Skip if no valid return data
      if (expectedReturn === 0 && sharpe === 0) continue;

      results.push({
        run_id: row[indices.run_id] || '',
        timestamp: timestamp,
        date: date,
        stocks: row[indices.stocks] || '',
        weights: row[indices.weights] || '',
        sharpe: sharpe,
        expectedReturn: expectedReturn,
        volatility: volatility
      });
    }

    // Sort by timestamp ascending
    results.sort((a, b) => a.timestamp.localeCompare(b.timestamp));
    return results;
  }

  function parseScoredStocksCSV(csvText) {
    // Parse scored_stocks.csv to get historical CurrentPrice and TargetPrice per stock per run
    // Format: run_id,run_timestamp,scoring_version,Stock,Name,Sector,Industry,...,CurrentPrice,TargetPrice,...
    const lines = csvText.trim().split('\n');
    if (lines.length < 2) return [];

    const header = parseCSVLine(lines[0]);
    const indices = {
      run_id: header.findIndex(h => h.toLowerCase() === 'run_id'),
      run_timestamp: header.findIndex(h => h.toLowerCase() === 'run_timestamp'),
      stock: header.findIndex(h => h.toLowerCase() === 'stock'),
      currentPrice: header.findIndex(h => h.toLowerCase() === 'currentprice'),
      targetPrice: header.findIndex(h => h.toLowerCase() === 'targetprice'),
      forwardPE: header.findIndex(h => h.toLowerCase() === 'forwardpe'),
      sectorMedianPE: header.findIndex(h => h.toLowerCase() === 'sectormedianpe')
    };

    // Validate required columns exist
    if (indices.stock < 0 || indices.currentPrice < 0 || indices.targetPrice < 0) {
      console.warn('scored_stocks.csv missing required columns. Found:', header);
      return [];
    }

    const results = [];
    for (let i = 1; i < lines.length; i++) {
      const row = parseCSVLine(lines[i]);
      if (row.length < 10) continue;

      const timestamp = row[indices.run_timestamp] || '';
      const date = timestamp.split(' ')[0]; // Get just the date part

      const currentPrice = parseFloat(row[indices.currentPrice]);
      const targetPrice = parseFloat(row[indices.targetPrice]);

      // Skip rows with invalid prices
      if (isNaN(currentPrice) || isNaN(targetPrice) || currentPrice <= 0) continue;

      results.push({
        run_id: row[indices.run_id] || '',
        date: date,
        timestamp: timestamp,
        stock: row[indices.stock] || '',
        currentPrice: currentPrice,
        targetPrice: targetPrice,
        forwardPE: parseFloat(row[indices.forwardPE]) || null,
        sectorMedianPE: parseFloat(row[indices.sectorMedianPE]) || null
      });
    }

    return results;
  }

  function parseTickersMapping(csvText) {
    // Parse tickers.txt to extract BrokerName -> Symbol mapping
    // Format: Ticker,Name,Sector,Industry,BrokerName
    const mapping = {};
    const lines = csvText.trim().split('\n');
    if (lines.length < 2) return mapping;

    const header = parseCSVLine(lines[0]);
    const tickerIdx = header.findIndex(h => h.toLowerCase() === 'ticker');
    const brokerNameIdx = header.findIndex(h => h.toLowerCase() === 'brokername');

    if (tickerIdx < 0) return mapping;

    for (let i = 1; i < lines.length; i++) {
      const row = parseCSVLine(lines[i]);
      const symbol = row[tickerIdx];
      const brokerName = brokerNameIdx >= 0 ? row[brokerNameIdx] : null;

      if (symbol) {
        // Always map symbol to itself
        mapping[symbol.toUpperCase()] = symbol;
        mapping[normalizeTickerKey(symbol)] = symbol;

        // Map broker name if present
        if (brokerName && brokerName.trim()) {
          mapping[brokerName.toUpperCase()] = symbol;
          mapping[brokerName.toUpperCase().replace(/\s+/g, '')] = symbol;
        }
      }
    }

    return mapping;
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // CÁLCULOS
  // ═══════════════════════════════════════════════════════════════════════════
  function getTargetPrice(ticker, symbol) {
    // Try multiple key formats to find target price
    const keysToTry = [];

    if (symbol) {
      keysToTry.push(normalizeTickerKey(symbol));  // VULC3SA from VULC3.SA
      keysToTry.push(symbol);                       // VULC3.SA as-is
      keysToTry.push(symbol.replace('.SA', '') + 'SA');  // VULC3.SA -> VULC3SA
    }
    if (ticker) {
      keysToTry.push(normalizeTickerKey(ticker));  // VULCABRAS -> VULCABRAS
      keysToTry.push(ticker);                       // VULCABRAS as-is
    }

    for (const key of keysToTry) {
      if (key && targetsData[key] != null) {
        // Make sure it's a number, not a string (symbol map has string values)
        const val = targetsData[key];
        if (typeof val === 'number') return val;
      }
    }

    // Try partial match if exact match fails
    if (symbol) {
      const normalizedSymbol = normalizeTickerKey(symbol);
      for (const [key, val] of Object.entries(targetsData)) {
        if (typeof val === 'number' && normalizeTickerKey(key) === normalizedSymbol) {
          return val;
        }
      }
    }

    return null;
  }

  function calculatePortfolioMetrics() {
    if (!positionsData || !positionsData.positions) {
      return { totalInvested: 0, totalCurrent: 0, totalProjected: 0, positions: [] };
    }

    let totalInvested = 0;
    let totalCurrent = 0;
    let totalProjected = 0;
    const enrichedPositions = [];

    for (const pos of positionsData.positions) {
      if (pos.net_qty <= 0) continue; // Only open long positions

      const invested = pos.net_invested || 0;
      const currentPrice = pos.current_price || null;
      const targetPrice = getTargetPrice(pos.ticker, pos.symbol);
      const avgCost = pos.net_qty > 0 ? invested / pos.net_qty : 0;

      const currentValue = currentPrice ? pos.net_qty * currentPrice : null;
      const projectedValue = targetPrice ? pos.net_qty * targetPrice : null;

      const pl = currentValue != null ? currentValue - invested : null;
      const plPct = invested > 0 && pl != null ? (pl / invested) * 100 : null;

      const upside = currentPrice && targetPrice ? ((targetPrice - currentPrice) / currentPrice) * 100 : null;

      totalInvested += invested;
      if (currentValue != null) totalCurrent += currentValue;
      if (projectedValue != null) totalProjected += projectedValue;

      enrichedPositions.push({
        ...pos,
        avgCost,
        currentPrice,
        targetPrice,
        currentValue,
        projectedValue,
        pl,
        plPct,
        upside
      });
    }

    // Calculate weights
    for (const pos of enrichedPositions) {
      pos.weight = totalCurrent > 0 && pos.currentValue ? (pos.currentValue / totalCurrent) * 100 : 0;
    }

    // Sort by current value descending
    enrichedPositions.sort((a, b) => (b.currentValue || 0) - (a.currentValue || 0));

    return { totalInvested, totalCurrent, totalProjected, positions: enrichedPositions };
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // RENDERIZAÇÃO
  // ═══════════════════════════════════════════════════════════════════════════
  function renderAll() {
    renderMeta();
    renderSummary();
    renderEvolution();
    renderProjection();
    renderPositions();
    renderAllocation();
    renderTransactions();
    renderOptimizedRecommendation();
    renderReturnComparisonChart();
    renderComparison();
  }

  function renderMeta() {
    const lastUpdatedEl = document.getElementById('lastUpdated');
    const notesCountEl = document.getElementById('notesCount');
    const footerDateEl = document.getElementById('footerDate');

    if (positionsData && positionsData.generated_at) {
      const date = new Date(positionsData.generated_at);
      const formatted = date.toLocaleString('pt-BR');
      if (lastUpdatedEl) lastUpdatedEl.textContent = formatted;
      if (footerDateEl) footerDateEl.textContent = formatted;
    }

    if (processedNotesData && processedNotesData.processed) {
      if (notesCountEl) notesCountEl.textContent = processedNotesData.processed.length;
    }
  }

  function renderSummary() {
    const metrics = calculatePortfolioMetrics();

    document.getElementById('totalInvested').textContent = formatCurrency(metrics.totalInvested);
    document.getElementById('totalCurrent').textContent = formatCurrency(metrics.totalCurrent);

    const pl = metrics.totalCurrent - metrics.totalInvested;
    const plPct = metrics.totalInvested > 0 ? (pl / metrics.totalInvested) * 100 : 0;

    const plEl = document.getElementById('totalPL');
    const plPctEl = document.getElementById('totalPLPct');

    plEl.textContent = formatCurrency(pl);
    plEl.classList.toggle('positive', pl >= 0);
    plEl.classList.toggle('negative', pl < 0);

    plPctEl.textContent = formatPercent(plPct);
    plPctEl.classList.toggle('positive', plPct >= 0);
    plPctEl.classList.toggle('negative', plPct < 0);

    const openPositions = metrics.positions.filter(p => p.net_qty > 0).length;
    document.getElementById('positionsCount').textContent = openPositions;
    document.getElementById('transactionsCount').textContent = transactionsData.length;
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // GRÁFICO DE EVOLUÇÃO DO PATRIMÔNIO
  // ═══════════════════════════════════════════════════════════════════════════
  let currentRange = 'all';

  function filterHistoryByRange(history, range) {
    if (!history || history.length === 0) return [];

    const now = new Date();
    let cutoffDate;

    switch (range) {
      case '1m':
        cutoffDate = new Date(now);
        cutoffDate.setMonth(cutoffDate.getMonth() - 1);
        break;
      case '3m':
        cutoffDate = new Date(now);
        cutoffDate.setMonth(cutoffDate.getMonth() - 3);
        break;
      default: // 'all'
        return history;
    }

    return history.filter(d => new Date(d.date) >= cutoffDate);
  }

  function renderEvolution(range = currentRange) {
    const canvas = document.getElementById('portfolioEvolutionChart');
    if (!canvas) return;

    const history = portfolioHistoryData?.history || [];
    const filteredHistory = filterHistoryByRange(history, range);

    if (filteredHistory.length === 0) {
      if (evolutionChart) {
        try { evolutionChart.destroy(); } catch(e) {}
      }
      const ctx = canvas.getContext('2d');
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.fillStyle = '#888';
      ctx.textAlign = 'center';
      ctx.fillText('Sem dados históricos', canvas.width / 2, canvas.height / 2);
      return;
    }

    // Prepare data
    const labels = filteredHistory.map(d => d.date);
    const marketValues = filteredHistory.map(d => d.market_value);
    const costBases = filteredHistory.map(d => d.cost_basis);
    const profitLoss = filteredHistory.map(d => d.profit_loss);

    // Find transaction days for annotations
    const transactionDays = filteredHistory
      .filter(d => d.transactions && d.transactions.length > 0)
      .map(d => ({
        date: d.date,
        transactions: d.transactions,
        marketValue: d.market_value
      }));

    // Destroy previous chart
    if (evolutionChart) {
      try { evolutionChart.destroy(); } catch(e) {}
    }

    evolutionChart = new Chart(canvas, {
      type: 'line',
      data: {
        labels: labels,
        datasets: [
          {
            label: 'Valor de Mercado',
            data: marketValues,
            borderColor: '#4fc3f7',
            backgroundColor: 'rgba(79, 195, 247, 0.1)',
            fill: false,
            tension: 0.2,
            pointRadius: 2,
            pointHoverRadius: 6,
            borderWidth: 2
          },
          {
            label: 'Custo Base',
            data: costBases,
            borderColor: '#68b36b',
            backgroundColor: 'rgba(104, 179, 107, 0.1)',
            fill: false,
            tension: 0,
            pointRadius: 0,
            borderWidth: 2,
            borderDash: [5, 5]
          },
          {
            label: 'Lucro/Prejuízo',
            data: profitLoss,
            borderColor: profitLoss[profitLoss.length - 1] >= 0 ? '#2b8a3e' : '#d9534f',
            backgroundColor: profitLoss[profitLoss.length - 1] >= 0
              ? 'rgba(43, 138, 62, 0.2)'
              : 'rgba(217, 83, 79, 0.2)',
            fill: true,
            tension: 0.2,
            pointRadius: 0,
            borderWidth: 1,
            hidden: true // Hidden by default, can be toggled
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: {
          mode: 'index',
          intersect: false
        },
        plugins: {
          legend: {
            display: false // Using custom legend
          },
          tooltip: {
            backgroundColor: 'rgba(30, 30, 30, 0.95)',
            titleColor: '#fff',
            bodyColor: '#fff',
            padding: 12,
            displayColors: true,
            callbacks: {
              title: function(context) {
                const date = context[0].label;
                const d = new Date(date);
                return d.toLocaleDateString('pt-BR', {
                  weekday: 'short',
                  day: 'numeric',
                  month: 'short',
                  year: 'numeric'
                });
              },
              label: function(context) {
                const value = context.raw;
                const label = context.dataset.label;
                return `${label}: ${formatCurrency(value)}`;
              },
              afterBody: function(context) {
                const dateStr = context[0].label;
                const dayData = filteredHistory.find(d => d.date === dateStr);

                if (!dayData) return [];

                const lines = [];
                lines.push(`Retorno: ${formatPercent(dayData.profit_loss_pct)}`);

                // Show transactions if any
                if (dayData.transactions && dayData.transactions.length > 0) {
                  lines.push('');
                  lines.push('📊 Transações:');
                  dayData.transactions.forEach(tx => {
                    const icon = tx.side === 'BUY' ? '🟢' : '🔴';
                    lines.push(`${icon} ${tx.side === 'BUY' ? 'Compra' : 'Venda'} ${tx.qty}x ${tx.symbol} @ ${formatCurrency(tx.price)}`);
                  });
                }

                return lines;
              }
            }
          }
        },
        scales: {
          x: {
            display: true,
            grid: {
              display: false
            },
            ticks: {
              maxTicksLimit: 10,
              callback: function(value, index) {
                const date = new Date(this.getLabelForValue(value));
                return date.toLocaleDateString('pt-BR', { day: '2-digit', month: 'short' });
              }
            }
          },
          y: {
            display: true,
            grid: {
              color: 'rgba(255, 255, 255, 0.1)'
            },
            ticks: {
              callback: function(value) {
                return formatCurrency(value);
              }
            }
          }
        }
      }
    });

    // Setup range buttons
    setupRangeButtons();
  }

  function setupRangeButtons() {
    document.querySelectorAll('.range-btn').forEach(btn => {
      btn.addEventListener('click', function() {
        document.querySelectorAll('.range-btn').forEach(b => b.classList.remove('active'));
        this.classList.add('active');
        currentRange = this.getAttribute('data-range');
        renderEvolution(currentRange);
      });
    });
  }

  function renderProjection() {
    const metrics = calculatePortfolioMetrics();

    const projectedValueEl = document.getElementById('projectedValue');
    const projectedUpsideEl = document.getElementById('projectedUpside');
    const projectedProfitEl = document.getElementById('projectedProfit');

    projectedValueEl.textContent = formatCurrency(metrics.totalProjected);

    const upside = metrics.totalCurrent > 0
      ? ((metrics.totalProjected - metrics.totalCurrent) / metrics.totalCurrent) * 100
      : 0;
    projectedUpsideEl.textContent = formatPercent(upside);
    projectedUpsideEl.classList.toggle('positive', upside >= 0);
    projectedUpsideEl.classList.toggle('negative', upside < 0);

    const projectedProfit = metrics.totalProjected - metrics.totalInvested;
    projectedProfitEl.textContent = formatCurrency(projectedProfit);
    projectedProfitEl.classList.toggle('positive', projectedProfit >= 0);
    projectedProfitEl.classList.toggle('negative', projectedProfit < 0);
  }

  function renderPositions() {
    const metrics = calculatePortfolioMetrics();
    const tbody = document.getElementById('positionsBody');
    if (!tbody) return;

    tbody.innerHTML = '';

    for (const pos of metrics.positions) {
      if (pos.net_qty <= 0) continue;

      const tr = document.createElement('tr');

      const plClass = pos.pl != null ? (pos.pl >= 0 ? 'positive' : 'negative') : '';
      const upsideClass = pos.upside != null ? (pos.upside >= 0 ? 'positive' : 'negative') : '';

      tr.innerHTML = `
        <td><strong>${pos.symbol || pos.ticker}</strong></td>
        <td>${pos.net_qty}</td>
        <td>${formatCurrency(pos.avgCost)}</td>
        <td>${pos.currentPrice ? formatCurrency(pos.currentPrice) : '<span class="muted">—</span>'}</td>
        <td>${pos.targetPrice ? formatCurrency(pos.targetPrice) : '<span class="muted">—</span>'}</td>
        <td>${formatCurrency(pos.net_invested)}</td>
        <td>${pos.currentValue ? formatCurrency(pos.currentValue) : '<span class="muted">—</span>'}</td>
        <td class="${plClass}">${pos.pl != null ? formatCurrency(pos.pl) + ' (' + formatPercent(pos.plPct) + ')' : '<span class="muted">—</span>'}</td>
        <td class="${upsideClass}">${pos.upside != null ? formatPercent(pos.upside) : '<span class="muted">—</span>'}</td>
        <td>${formatPercent(pos.weight, 1).replace('+', '')}</td>
      `;
      tbody.appendChild(tr);
    }

    if (metrics.positions.filter(p => p.net_qty > 0).length === 0) {
      tbody.innerHTML = '<tr><td colspan="10" class="no-data">Nenhuma posição aberta</td></tr>';
    }
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // RECOMENDAÇÃO OTIMIZADA (Script C)
  // ═══════════════════════════════════════════════════════════════════════════
  function renderOptimizedRecommendation() {
    const verdictEl = document.getElementById('optimizedVerdict');
    const metricsEl = document.getElementById('optimizedMetrics');
    const transactionsEl = document.getElementById('optimizedTransactions');

    if (!optimizedRecommendation) {
      if (verdictEl) {
        verdictEl.className = 'rebalance-verdict';
        verdictEl.innerHTML = `
          <div class="verdict-icon">⚠️</div>
          <div class="verdict-text">Recomendação não disponível. Execute C_OptimizedPortfolio.sh para gerar.</div>
        `;
      }
      return;
    }

    const rec = optimizedRecommendation;
    const decision = rec.decision || 'UNKNOWN';
    const isRebalance = decision === 'REBALANCE';
    const comparison = rec.comparison || {};
    const holdings = comparison.holdings || {};
    const optimal = comparison.optimal || {};

    // Render verdict
    if (verdictEl) {
      const iconMap = {
        'REBALANCE': '🔄',
        'HOLD': '✅',
        'UNKNOWN': '❓'
      };
      const classMap = {
        'REBALANCE': 'recommend',
        'HOLD': 'hold',
        'UNKNOWN': ''
      };

      verdictEl.className = 'rebalance-verdict ' + (classMap[decision] || '');
      verdictEl.innerHTML = `
        <div class="verdict-icon">${iconMap[decision] || '❓'}</div>
        <div class="verdict-content">
          <div class="verdict-text">${decision === 'REBALANCE' ? 'Recomendado Rebalancear' : 'Manter Portfolio Atual'}</div>
          <div class="verdict-detail">${rec.reason || ''}</div>
        </div>
      `;
    }

    // Show metrics
    if (metricsEl) {
      metricsEl.style.display = 'grid';

      const holdingsReturnEl = document.getElementById('optHoldingsReturn');
      const optimalReturnEl = document.getElementById('optOptimalReturn');
      const excessReturnEl = document.getElementById('optExcessReturn');
      const transitionCostEl = document.getElementById('optTransitionCost');

      if (holdingsReturnEl) {
        holdingsReturnEl.textContent = formatPercent(holdings.expected_return_pct || 0);
      }
      if (optimalReturnEl) {
        optimalReturnEl.textContent = formatPercent(optimal.net_return_pct || 0);
        optimalReturnEl.className = 'metric-value ' + ((optimal.net_return_pct || 0) >= 0 ? 'positive' : 'negative');
      }
      if (excessReturnEl) {
        const excess = rec.excess_return_pct || 0;
        excessReturnEl.textContent = formatPercent(excess);
        excessReturnEl.className = 'metric-value ' + (excess >= 0 ? 'positive' : 'negative');
      }
      if (transitionCostEl) {
        transitionCostEl.textContent = formatPercent(optimal.transition_cost_pct || 0);
        transitionCostEl.className = 'metric-value negative';
      }
    }

    // Show transactions if REBALANCE
    const transactions = rec.transactions || [];
    if (transactionsEl && transactions.length > 0 && isRebalance) {
      transactionsEl.style.display = 'block';
      const tbody = document.getElementById('optimizedTransactionsBody');
      if (tbody) {
        tbody.innerHTML = '';
        transactions.forEach(tx => {
          const tr = document.createElement('tr');
          const actionClass = tx.action === 'BUY' ? 'positive' : 'negative';
          const weightChange = ((tx.target_weight - tx.current_weight) * 100).toFixed(1);
          tr.innerHTML = `
            <td><strong>${tx.symbol}</strong></td>
            <td class="${actionClass}">${tx.action === 'BUY' ? '🟢 Comprar' : '🔴 Vender'}</td>
            <td>${(tx.current_weight * 100).toFixed(1)}%</td>
            <td>${(tx.target_weight * 100).toFixed(1)}%</td>
            <td class="${actionClass}">${weightChange > 0 ? '+' : ''}${weightChange}%</td>
          `;
          tbody.appendChild(tr);
        });
      }
    } else if (transactionsEl) {
      transactionsEl.style.display = 'none';
    }

    // Update timestamp
    const timestampEl = document.getElementById('optTimestamp');
    if (timestampEl && rec.timestamp) {
      timestampEl.textContent = rec.timestamp;
    }
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // GRÁFICO: COMPARAÇÃO DE RETORNOS (Ideal vs Implementado)
  // ═══════════════════════════════════════════════════════════════════════════
  function renderReturnComparisonChart() {
    const canvas = document.getElementById('returnComparisonChart');
    if (!canvas) return;

    // Destroy existing chart
    if (returnComparisonChart) {
      try { returnComparisonChart.destroy(); } catch(e) {}
    }

    if (!portfolioResultsData || portfolioResultsData.length === 0) {
      const ctx = canvas.getContext('2d');
      ctx.font = '14px Arial';
      ctx.fillStyle = '#888';
      ctx.textAlign = 'center';
      ctx.fillText('Sem dados históricos disponíveis', canvas.width / 2, canvas.height / 2);
      return;
    }

    // Prepare ideal portfolio data (from Script A results)
    const idealData = portfolioResultsData.map(r => ({
      date: r.date,
      timestamp: r.timestamp,
      run_id: r.run_id,
      return: r.expectedReturn,
      stocks: r.stocks,
      weights: r.weights
    }));

    // Calculate implemented portfolio returns at each trade date
    // This also builds the portfolio state over time
    const { returns: implementedData, portfolioByDate } = calculateImplementedReturnsWithState();

    // Get transaction cost percentage from parameters or use default
    const transactionCostPct = optimizedRecommendation?.transaction_cost_pct_used || 0.0285;

    // Merge all dates from both datasets
    const allDates = [...new Set([
      ...idealData.map(d => d.date),
      ...implementedData.map(d => d.date)
    ])].sort();

    // Build datasets - ideal shows NET return (after transition cost from current holdings)
    const labels = [];
    const idealNetValues = [];  // Ideal return MINUS cost to transition from implemented
    const implementedValues = [];

    let lastImplementedReturn = null;
    let lastImplementedPortfolio = null;  // Track current portfolio state

    allDates.forEach(date => {
      const idealPoint = idealData.find(d => d.date === date);
      const implPoint = implementedData.find(d => d.date === date);

      // Update last implemented return and portfolio if we have new data
      if (implPoint) {
        lastImplementedReturn = implPoint.return;
        lastImplementedPortfolio = portfolioByDate[date] || lastImplementedPortfolio;
      }

      // Calculate net ideal return (ideal return - transition cost)
      let idealNetReturn = null;
      if (idealPoint && idealPoint.return != null) {
        // Calculate transition cost from current holdings to ideal
        const transitionCost = calculateTransitionCost(
          lastImplementedPortfolio,
          idealPoint.stocks,
          idealPoint.weights,
          transactionCostPct
        );
        idealNetReturn = idealPoint.return - transitionCost;
      }

      // Add data point
      labels.push(date);
      idealNetValues.push(idealNetReturn);
      implementedValues.push(lastImplementedReturn);
    });

    returnComparisonChart = new Chart(canvas, {
      type: 'line',
      data: {
        labels: labels,
        datasets: [
          {
            label: 'Portfolio Ideal (líquido de custos)',
            data: idealNetValues,
            borderColor: '#2196F3',
            backgroundColor: 'rgba(33, 150, 243, 0.1)',
            fill: false,
            tension: 0.3,
            pointRadius: 2,
            pointHoverRadius: 6,
            borderWidth: 2,
            spanGaps: true
          },
          {
            label: 'Portfolio Implementado',
            data: implementedValues,
            borderColor: '#4CAF50',
            backgroundColor: 'rgba(76, 175, 80, 0.15)',
            fill: true,
            stepped: 'before',  // Step interpolation - constant until next change
            pointRadius: 3,
            pointHoverRadius: 6,
            borderWidth: 2,
            spanGaps: true
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: {
          mode: 'index',
          intersect: false
        },
        plugins: {
          legend: {
            display: true,
            position: 'top'
          },
          tooltip: {
            backgroundColor: 'rgba(30, 30, 30, 0.95)',
            titleColor: '#fff',
            bodyColor: '#fff',
            padding: 12,
            callbacks: {
              title: function(context) {
                return context[0].label;
              },
              label: function(context) {
                const value = context.parsed.y;
                if (value == null) return context.dataset.label + ': —';
                return context.dataset.label + ': ' + value.toFixed(2) + '%';
              },
              afterBody: function(context) {
                // Show recommendation based on comparison
                const idealVal = context[0]?.parsed?.y;
                const implVal = context[1]?.parsed?.y;
                if (idealVal != null && implVal != null) {
                  const diff = idealVal - implVal;
                  if (diff > 0) {
                    return ['', '⚠️ Rebalancear (+' + diff.toFixed(1) + '% ganho)'];
                  } else {
                    return ['', '✅ Manter (' + diff.toFixed(1) + '%)'];
                  }
                }
                return [];
              }
            }
          }
        },
        scales: {
          x: {
            display: true,
            title: {
              display: true,
              text: 'Data'
            },
            ticks: {
              maxRotation: 45,
              minRotation: 45,
              autoSkip: true,
              maxTicksLimit: 12
            }
          },
          y: {
            display: true,
            title: {
              display: true,
              text: 'Retorno Anual (%)'
            },
            ticks: {
              callback: function(value) {
                return value.toFixed(1) + '%';
              }
            }
          }
        }
      }
    });
  }

  function calculateImplementedReturnsWithState() {
    // Calculate the expected annual return of the implemented portfolio at each trade date
    // Also returns the portfolio state (weights) at each date for transition cost calculation
    // Logic:
    // 1. Group transactions by date
    // 2. At each date, calculate portfolio composition after trades
    // 3. Calculate expected return based on target prices for that composition
    // 4. Return stays constant until next trade date

    const returns = [];
    const portfolioByDate = {};  // Track portfolio weights at each date

    if (!transactionsData || transactionsData.length === 0) {
      console.warn('No transaction data for implemented returns');
      return { returns, portfolioByDate };
    }

    if (!targetsData || Object.keys(targetsData).length === 0) {
      console.warn('No target data available for implemented returns calculation');
      return { returns, portfolioByDate };
    }

    // Build ticker to symbol mapping from positionsData
    const tickerToSymbol = {};
    if (positionsData && positionsData.positions) {
      positionsData.positions.forEach(pos => {
        // Map both ticker name and symbol variations
        if (pos.ticker && pos.symbol) {
          const ticker = pos.ticker.toUpperCase();
          const symbol = pos.symbol;

          // Only add if symbol looks like a valid ticker (contains numbers)
          if (/\d/.test(symbol)) {
            tickerToSymbol[ticker] = symbol;
            tickerToSymbol[symbol.toUpperCase()] = symbol;
            // Also map without spaces
            tickerToSymbol[ticker.replace(/\s+/g, '')] = symbol;
            // Map first word (e.g., "COPASA" from "COPASA ON NM")
            const firstWord = ticker.split(/\s+/)[0];
            if (firstWord) {
              tickerToSymbol[firstWord] = symbol;
            }
          }
        }
      });
    }

    // Merge with brokerNameToSymbol from tickers.txt (loaded at startup)
    if (brokerNameToSymbol && Object.keys(brokerNameToSymbol).length > 0) {
      Object.assign(tickerToSymbol, brokerNameToSymbol);
    }

    // Add fallback mappings for ledger names - these OVERRIDE any incorrect mappings
    // These are the exact names used in ledger.csv -> ticker symbols
    const ledgerFallbacks = {
      'COPASA ON NM': 'CSMG3.SA',
      'COPASA': 'CSMG3.SA',
      'PLANOEPLANO ON NM': 'PLPL3.SA',
      'PLANOEPLANO': 'PLPL3.SA',
      'VULCABRAS ON NM': 'VULC3.SA',
      'VULCABRAS ON ED NM': 'VULC3.SA',
      'VULCABRAS ON EDS NM': 'VULC3.SA',
      'VULCABRAS': 'VULC3.SA',
      'LAVVI ON NM': 'LAVV3.SA',
      'LAVVI': 'LAVV3.SA',
      'AXIA ENERGIAPNB EX N1': 'AXIA6.SA',
      'AXIA ENERGIA': 'AXIA6.SA',
      'MOURA DUBEUXON ED NM': 'MDNE3.SA',
      'MOURA DUBEUX': 'MDNE3.SA',
      'TENDA ON ED NM': 'TEND3.SA',
      'TENDA': 'TEND3.SA',
      'VALE ON NM': 'VALE3.SA',
      'VALE': 'VALE3.SA',
      'AURA 360 DR3': 'AURA33.SA',
      'AURA 360': 'AURA33.SA',
      'CEMIG ON N1': 'CMIG3.SA',
      'CEMIG': 'CMIG3.SA',
      'PETROBRAS ON N2': 'PETR3.SA',
      'PETROBRAS': 'PETR3.SA',
      'SANEPAR UNT N2': 'SAPR11.SA',
      'SANEPAR': 'SAPR11.SA',
    };
    // Apply fallbacks - these override any previous mappings
    Object.entries(ledgerFallbacks).forEach(([name, symbol]) => {
      tickerToSymbol[name.toUpperCase()] = symbol;
    });

    // Sort transactions by date ascending
    const sortedTx = [...transactionsData].sort((a, b) => a.date.localeCompare(b.date));

    // Build portfolio state over time
    // holdings: { symbol: { qty, totalCost } }
    const holdings = {};

    // Group transactions by date
    const txByDate = {};
    sortedTx.forEach(tx => {
      if (!txByDate[tx.date]) {
        txByDate[tx.date] = [];
      }
      txByDate[tx.date].push(tx);
    });

    const tradeDates = Object.keys(txByDate).sort();

    tradeDates.forEach(date => {
      // Apply all transactions for this date
      txByDate[date].forEach(tx => {
        const tickerName = tx.ticker;
        if (!tickerName) return;

        // Find the symbol for this ticker
        let symbol = tickerToSymbol[tickerName.toUpperCase()] ||
                     tickerToSymbol[tickerName.toUpperCase().replace(/\s+/g, '')] ||
                     tickerName;

        // Normalize symbol to match targets format
        const normalizedSymbol = normalizeTickerKey(symbol);

        if (!holdings[normalizedSymbol]) {
          holdings[normalizedSymbol] = { qty: 0, totalCost: 0, originalSymbol: symbol };
        }

        if (tx.side === 'BUY' || tx.side === 'C') {
          holdings[normalizedSymbol].qty += tx.qty;
          holdings[normalizedSymbol].totalCost += tx.total || (tx.qty * tx.price);
        } else if (tx.side === 'SELL' || tx.side === 'V') {
          // FIFO-like: reduce qty and proportional cost
          const avgCost = holdings[normalizedSymbol].qty > 0
            ? holdings[normalizedSymbol].totalCost / holdings[normalizedSymbol].qty
            : tx.price;
          holdings[normalizedSymbol].qty -= tx.qty;
          holdings[normalizedSymbol].totalCost -= tx.qty * avgCost;

          // Clean up if position closed
          if (holdings[normalizedSymbol].qty <= 0) {
            holdings[normalizedSymbol].qty = 0;
            holdings[normalizedSymbol].totalCost = 0;
          }
        }
      });

      // Calculate portfolio weights at this date
      const activeStocks = Object.entries(holdings).filter(([_, pos]) => pos.qty > 0);
      const totalCost = activeStocks.reduce((sum, [_, pos]) => sum + pos.totalCost, 0);

      if (totalCost > 0) {
        const weights = {};
        activeStocks.forEach(([symbol, pos]) => {
          weights[symbol] = pos.totalCost / totalCost;
        });
        portfolioByDate[date] = weights;
      }

      // Calculate expected return for current portfolio composition using historical data for this date
      const expectedReturn = calculateExpectedReturnForHoldings(holdings, date);

      if (expectedReturn !== null) {
        returns.push({
          date: date,
          return: expectedReturn
        });
      }
    });

    // Add current date with value from optimized_recommendation.json if available
    // This ensures consistency between the chart and the KPI cards
    const today = new Date().toISOString().split('T')[0];
    if (optimizedRecommendation && optimizedRecommendation.comparison && optimizedRecommendation.comparison.holdings) {
      const holdingsReturn = optimizedRecommendation.comparison.holdings.expected_return_pct;
      if (holdingsReturn != null) {
        // Update or add today's value with the authoritative return from Python
        const existingIdx = returns.findIndex(r => r.date === today || r.date === optimizedRecommendation.date);
        if (existingIdx >= 0) {
          returns[existingIdx].return = holdingsReturn;
        } else {
          returns.push({
            date: optimizedRecommendation.date || today,
            return: holdingsReturn
          });
        }

        // Also save current portfolio weights from optimized_recommendation
        if (optimizedRecommendation.comparison.holdings.weights) {
          const currentWeights = {};
          Object.entries(optimizedRecommendation.comparison.holdings.weights).forEach(([stock, weight]) => {
            currentWeights[normalizeTickerKey(stock)] = weight;
          });
          portfolioByDate[optimizedRecommendation.date || today] = currentWeights;
        }
      }
    } else if (returns.length > 0 && returns[returns.length - 1].date !== today) {
      // Fallback: extend last known return
      returns.push({
        date: today,
        return: returns[returns.length - 1].return
      });
    }

    return { returns, portfolioByDate };
  }

  function calculateTransitionCost(currentPortfolio, idealStocksStr, idealWeightsStr, costPct) {
    // Calculate the cost of transitioning from current portfolio to ideal portfolio
    // Cost = sum of absolute weight changes * costPct

    if (!currentPortfolio || !idealStocksStr || !idealWeightsStr) {
      return 0;
    }

    // Parse ideal portfolio from strings (format: "STOCK1, STOCK2, ..." and "0.1, 0.2, ...")
    const idealStocks = idealStocksStr.split(',').map(s => normalizeTickerKey(s.trim()));
    const idealWeights = idealWeightsStr.split(',').map(w => parseFloat(w.trim()) || 0);

    if (idealStocks.length !== idealWeights.length) {
      return 0;
    }

    // Build ideal weights map
    const idealWeightsMap = {};
    idealStocks.forEach((stock, i) => {
      idealWeightsMap[stock] = idealWeights[i];
    });

    // Calculate total absolute weight change
    let totalChange = 0;

    // Changes to existing positions
    Object.entries(currentPortfolio).forEach(([stock, weight]) => {
      const idealWeight = idealWeightsMap[stock] || 0;
      totalChange += Math.abs(idealWeight - weight);
    });

    // New positions in ideal (not in current)
    Object.entries(idealWeightsMap).forEach(([stock, weight]) => {
      if (!currentPortfolio[stock]) {
        totalChange += weight;
      }
    });

    // Transition cost as percentage of return
    // Each unit of turnover costs costPct (e.g., 2.85% for buying/selling)
    // totalChange/2 because buying one stock means selling another
    const transitionCost = (totalChange / 2) * costPct * 100;

    return transitionCost;
  }

  function calculateExpectedReturnForHoldings(holdings, tradeDate) {
    // Calculate weighted expected return based on historical target prices from scored_stocks.csv
    // Uses the closest run date to the trade date for accurate historical calculation
    let totalValue = 0;
    let weightedReturn = 0;
    let stocksWithTargets = 0;

    const activeHoldings = Object.keys(holdings).filter(k => holdings[k].qty > 0);

    // Find the closest scoring run to this trade date
    // scored_stocks.csv has data per stock per run_id/date
    let closestRunDate = null;
    if (scoredStocksHistory && scoredStocksHistory.length > 0) {
      // Get unique dates from scored stocks history, sorted ascending
      const scoringDates = [...new Set(scoredStocksHistory.map(s => s.date))].sort();

      // Find the closest date <= tradeDate (use data available at that point)
      for (const d of scoringDates) {
        if (d <= tradeDate) {
          closestRunDate = d;
        } else {
          break;
        }
      }
      // If no date before tradeDate, use the first available date
      if (!closestRunDate && scoringDates.length > 0) {
        closestRunDate = scoringDates[0];
      }
    }

    // Build a map of stock -> {currentPrice, targetPrice} for the closest run date
    const stockPricesForDate = {};
    if (closestRunDate && scoredStocksHistory) {
      scoredStocksHistory
        .filter(s => s.date === closestRunDate)
        .forEach(s => {
          const normStock = normalizeTickerKey(s.stock);
          stockPricesForDate[normStock] = {
            currentPrice: s.currentPrice,
            targetPrice: s.targetPrice
          };
        });
    }

    // First pass: calculate total portfolio value using historical prices
    const positionValues = {};
    for (const [normalizedSymbol, pos] of Object.entries(holdings)) {
      if (pos.qty <= 0) continue;

      // Try to get historical price for this stock
      let currentPrice = null;
      const historicalData = findStockPriceData(normalizedSymbol, stockPricesForDate);

      if (historicalData && historicalData.currentPrice > 0) {
        currentPrice = historicalData.currentPrice;
      } else if (positionsData && positionsData.positions) {
        // Fallback to current positions data
        const found = positionsData.positions.find(p => {
          const posNorm = normalizeTickerKey(p.symbol || p.ticker || '');
          return posNorm === normalizedSymbol;
        });
        if (found && found.current_price) {
          currentPrice = found.current_price;
        }
      }

      // Final fallback to avg cost
      if (!currentPrice && pos.qty > 0) {
        currentPrice = pos.totalCost / pos.qty;
      }


      const value = pos.qty * currentPrice;
      positionValues[normalizedSymbol] = { value, currentPrice, qty: pos.qty };
      totalValue += value;
    }

    if (totalValue <= 0) return null;

    // Second pass: calculate weighted return using historical targets
    for (const [normalizedSymbol, posVal] of Object.entries(positionValues)) {
      const weight = posVal.value / totalValue;

      // Try to get historical target price
      let targetPrice = null;
      const historicalData = findStockPriceData(normalizedSymbol, stockPricesForDate);

      if (historicalData && historicalData.targetPrice > 0) {
        targetPrice = historicalData.targetPrice;
      } else {
        // Fallback to current targets data with ON/PN equivalences
        targetPrice = findTargetPriceWithEquivalences(normalizedSymbol);
      }

      if (targetPrice && posVal.currentPrice > 0) {
        const stockReturn = ((targetPrice - posVal.currentPrice) / posVal.currentPrice) * 100;
        weightedReturn += weight * stockReturn;
        stocksWithTargets++;
      }
    }

    // Only return if we have targets for at least some stocks
    if (stocksWithTargets === 0) {
      return null;
    }

    return weightedReturn;
  }

  function findStockPriceData(normalizedSymbol, stockPricesForDate) {
    // Try to find price data for this symbol, including ON/PN equivalences
    const baseSymbol = normalizedSymbol.replace(/SA$/, '');  // e.g., PETR3
    const baseWithoutNum = baseSymbol.replace(/[0-9]+$/, ''); // e.g., PETR
    const numPart = baseSymbol.match(/[0-9]+$/)?.[0] || '';   // e.g., 3

    const alternativeNums = {
      '3': ['4', '11'],
      '4': ['3', '11'],
      '6': ['3', '4'],
      '11': ['3', '4'],
    };

    const keysToTry = [
      normalizedSymbol,
      baseSymbol + 'SA',
    ];

    if (numPart && alternativeNums[numPart]) {
      alternativeNums[numPart].forEach(altNum => {
        keysToTry.push(baseWithoutNum + altNum + 'SA');
      });
    }

    for (const key of keysToTry) {
      if (stockPricesForDate[key]) {
        return stockPricesForDate[key];
      }
    }
    return null;
  }

  function findTargetPriceWithEquivalences(normalizedSymbol) {
    // Find target price in targetsData with ON/PN equivalences
    const baseSymbol = normalizedSymbol.replace(/SA$/, '');
    const baseWithoutNum = baseSymbol.replace(/[0-9]+$/, '');
    const numPart = baseSymbol.match(/[0-9]+$/)?.[0] || '';

    const alternativeNums = {
      '3': ['4', '11'],
      '4': ['3', '11'],
      '6': ['3', '4'],
      '11': ['3', '4'],
    };

    const keysToTry = [
      normalizedSymbol,
      baseSymbol + 'SA',
    ];

    if (numPart && alternativeNums[numPart]) {
      alternativeNums[numPart].forEach(altNum => {
        keysToTry.push(baseWithoutNum + altNum + 'SA');
      });
    }

    for (const key of keysToTry) {
      const val = targetsData[key];
      if (val !== undefined && val !== null && typeof val === 'number' && !isNaN(val)) {
        return val;
      }
    }
    return null;
  }


  function renderAllocation() {
    const metrics = calculatePortfolioMetrics();
    const canvas = document.getElementById('allocationChart');
    const legendEl = document.getElementById('allocationLegend');

    if (!canvas) return;

    const positions = metrics.positions.filter(p => p.net_qty > 0 && p.currentValue > 0);

    if (positions.length === 0) {
      if (legendEl) legendEl.innerHTML = '<div class="no-data">Sem dados de alocação</div>';
      return;
    }

    const labels = positions.map(p => p.symbol || p.ticker);
    const values = positions.map(p => p.currentValue || 0);
    const colors = generatePalette(positions.length);

    if (allocationChart) {
      try { allocationChart.destroy(); } catch(e) {}
    }

    allocationChart = new Chart(canvas, {
      type: 'doughnut',
      data: {
        labels: labels,
        datasets: [{
          data: values,
          backgroundColor: colors,
          borderWidth: 2,
          borderColor: 'rgba(0,0,0,0.3)'
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: true,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (ctx) => {
                const total = ctx.dataset.data.reduce((a, b) => a + b, 0);
                const pct = ((ctx.raw / total) * 100).toFixed(1);
                return `${ctx.label}: ${formatCurrency(ctx.raw)} (${pct}%)`;
              }
            }
          }
        }
      }
    });

    // Render legend
    if (legendEl) {
      legendEl.innerHTML = positions.map((p, i) => `
        <div class="legend-item">
          <span class="legend-color" style="background:${colors[i]}"></span>
          <span class="legend-label">${p.symbol || p.ticker}</span>
          <span class="legend-value">${formatPercent(p.weight, 1).replace('+', '')}</span>
        </div>
      `).join('');
    }
  }

  function generatePalette(n) {
    const base = ['#2b8a3e', '#68b36b', '#4fc3f7', '#6fe3c5', '#f2c057', '#f28c28', '#d9534f', '#6c5ce7', '#00a3e0', '#e91e63'];
    const out = [];
    for (let i = 0; i < n; i++) out.push(base[i % base.length]);
    return out;
  }

  function renderTransactions() {
    const tbody = document.getElementById('transactionsBody');
    if (!tbody) return;

    tbody.innerHTML = '';

    for (const tx of transactionsData) {
      const tr = document.createElement('tr');
      tr.setAttribute('data-side', tx.side.toLowerCase());

      const sideClass = tx.side === 'BUY' ? 'buy-badge' : 'sell-badge';
      const sideText = tx.side === 'BUY' ? 'Compra' : 'Venda';

      tr.innerHTML = `
        <td>${tx.date}</td>
        <td><strong>${tx.ticker}</strong></td>
        <td><span class="tx-badge ${sideClass}">${sideText}</span></td>
        <td>${tx.qty}</td>
        <td>${formatCurrency(tx.price)}</td>
        <td>${formatCurrency(tx.total)}</td>
        <td>${formatCurrency(tx.fees)}</td>
      `;
      tbody.appendChild(tr);
    }

    if (transactionsData.length === 0) {
      tbody.innerHTML = '<tr><td colspan="7" class="no-data">Nenhuma transação registrada</td></tr>';
    }

    // Setup filter buttons
    document.querySelectorAll('.filter-btn').forEach(btn => {
      btn.addEventListener('click', function() {
        document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
        this.classList.add('active');
        const filter = this.getAttribute('data-filter');
        filterTransactions(filter);
      });
    });
  }

  function filterTransactions(filter) {
    const rows = document.querySelectorAll('#transactionsBody tr');
    rows.forEach(row => {
      const side = row.getAttribute('data-side');
      if (filter === 'all') {
        row.style.display = '';
      } else if (filter === 'buy' && side === 'buy') {
        row.style.display = '';
      } else if (filter === 'sell' && side === 'sell') {
        row.style.display = '';
      } else {
        row.style.display = 'none';
      }
    });
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // DADOS DE CUSTOS HISTÓRICOS
  // ═══════════════════════════════════════════════════════════════════════════
  let historicalFees = {
    totalFees: 0,
    totalVolume: 0,
    notesCount: 0,
    avgFeeRate: 0.028 // Default calculado do histórico
  };

  function calculateHistoricalFees() {
    // Dados extraídos das notas de negociação
    const feesData = [
      { noteId: '15030227', fees: 0.28, volume: 987.60 },
      { noteId: '15088606', fees: 0.26, volume: 908.77 },
      { noteId: '15124347', fees: 0.46, volume: 1587.15 },
      { noteId: '15118128', fees: 0.18, volume: 641.74 },
      { noteId: '15322925', fees: 0.27, volume: 976.76 }
    ];

    let totalFees = 0;
    let totalVolume = 0;

    for (const note of feesData) {
      totalFees += note.fees;
      totalVolume += note.volume;
    }

    historicalFees = {
      totalFees: totalFees,
      totalVolume: totalVolume,
      notesCount: feesData.length,
      avgFeeRate: totalVolume > 0 ? (totalFees / totalVolume) * 100 : 0.028
    };

    return historicalFees;
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // ANÁLISE DE REBALANCEAMENTO
  // ═══════════════════════════════════════════════════════════════════════════
  function calculateRebalanceAnalysis() {
    const feeRate = parseFloat(document.getElementById('feeRate')?.value || 0.028) / 100;
    const spreadRate = parseFloat(document.getElementById('spreadRate')?.value || 0.10) / 100;
    const minGainThreshold = parseFloat(document.getElementById('minGainThreshold')?.value || 5);
    const additionalInvestment = parseFloat(document.getElementById('additionalInvestment')?.value || 0);

    const metrics = calculatePortfolioMetrics();
    const currentPortfolioValue = metrics.totalCurrent || 0;

    // Valor total considerando aporte adicional
    const totalPortfolioValue = currentPortfolioValue + additionalInvestment;

    if (currentPortfolioValue <= 0 && additionalInvestment <= 0) {
      return { valid: false, reason: 'Sem posições abertas e sem aporte adicional' };
    }

    // Build maps of current positions
    const myPositions = new Map();
    for (const pos of metrics.positions) {
      if (pos.net_qty > 0) {
        const key = normalizeTickerKey(pos.symbol || pos.ticker);
        myPositions.set(key, {
          ticker: pos.symbol || pos.ticker,
          qty: pos.net_qty,
          currentPrice: pos.currentPrice || 0,
          currentValue: pos.currentValue || 0,
          targetPrice: pos.targetPrice || pos.currentPrice,
          weight: pos.weight || 0
        });
      }
    }

    // Build map of recommended positions with target allocation
    const recommendedMap = new Map();
    for (let i = 0; i < recommendedPortfolio.stocks.length; i++) {
      const stock = recommendedPortfolio.stocks[i];
      const weight = recommendedPortfolio.weights[i] || 0;
      const key = normalizeTickerKey(stock);

      // Get current price and target price for recommended stock
      let currentPrice = null;
      let targetPrice = getTargetPrice(stock, stock);

      // Check if we already own this stock
      const existingPos = myPositions.get(key);
      if (existingPos) {
        currentPrice = existingPos.currentPrice;
        if (!targetPrice) targetPrice = existingPos.targetPrice;
      }

      recommendedMap.set(key, {
        stock: stock,
        weight: weight * 100,
        currentPrice: currentPrice,
        targetPrice: targetPrice || currentPrice
      });
    }

    // Calculate transactions needed
    const transactions = [];
    let totalSellValue = 0;
    let totalBuyValue = 0;

    // Positions to sell (in current portfolio but not in recommended, or need to reduce)
    for (const [key, pos] of myPositions) {
      const rec = recommendedMap.get(key);
      const recWeight = rec ? rec.weight : 0;
      const currentWeight = pos.weight;

      if (recWeight < currentWeight) {
        const targetValue = (recWeight / 100) * totalPortfolioValue;
        const diffValue = pos.currentValue - targetValue;
        const diffQty = pos.currentPrice > 0 ? Math.floor(diffValue / pos.currentPrice) : 0;

        if (diffQty > 0) {
          transactions.push({
            ticker: pos.ticker,
            action: 'SELL',
            currentQty: pos.qty,
            targetQty: pos.qty - diffQty,
            diffQty: -diffQty,
            value: diffValue,
            price: pos.currentPrice,
            cost: diffValue * (feeRate + spreadRate)
          });
          totalSellValue += diffValue;
        }
      }
    }

    // Positions to buy (in recommended but not in current, or need to increase)
    for (const [key, rec] of recommendedMap) {
      const pos = myPositions.get(key);
      const currentWeight = pos ? pos.weight : 0;

      if (rec.weight > currentWeight) {
        const currentValue = pos ? pos.currentValue : 0;
        const targetValue = (rec.weight / 100) * totalPortfolioValue;
        const diffValue = targetValue - currentValue;

        // Use a price estimate - try current price from our positions or from targets
        let price = rec.currentPrice;
        if (!price && rec.targetPrice) {
          price = rec.targetPrice * 0.9; // Estimate current as 90% of target
        }
        if (!price) price = 50; // Default fallback

        const diffQty = Math.ceil(diffValue / price);

        if (diffQty > 0) {
          transactions.push({
            ticker: rec.stock,
            action: 'BUY',
            currentQty: pos ? pos.qty : 0,
            targetQty: (pos ? pos.qty : 0) + diffQty,
            diffQty: diffQty,
            value: diffValue,
            price: price,
            cost: diffValue * (feeRate + spreadRate)
          });
          totalBuyValue += diffValue;
        }
      }
    }

    // Calculate total costs
    const totalTransactionCost = transactions.reduce((sum, t) => sum + t.cost, 0);

    // Calculate expected gain from switching to recommended portfolio
    // Using target prices to estimate upside
    let currentPortfolioUpside = 0;
    let recommendedPortfolioUpside = 0;

    // Current portfolio upside
    for (const [key, pos] of myPositions) {
      if (pos.currentPrice > 0 && pos.targetPrice > 0) {
        const upside = ((pos.targetPrice - pos.currentPrice) / pos.currentPrice) * pos.currentValue;
        currentPortfolioUpside += upside;
      }
    }

    // Recommended portfolio upside (estimated)
    for (const [key, rec] of recommendedMap) {
      const targetValue = (rec.weight / 100) * totalPortfolioValue;
      if (rec.currentPrice > 0 && rec.targetPrice > 0) {
        const upside = ((rec.targetPrice - rec.currentPrice) / rec.currentPrice) * targetValue;
        recommendedPortfolioUpside += upside;
      }
    }

    const additionalGain = recommendedPortfolioUpside - currentPortfolioUpside;
    const netGain = additionalGain - totalTransactionCost;
    const netGainPct = totalPortfolioValue > 0 ? (netGain / totalPortfolioValue) * 100 : 0;

    // Calcular valores finais de cada cenário
    const currentFinalValue = currentPortfolioValue + currentPortfolioUpside;
    const recommendedFinalValue = totalPortfolioValue + recommendedPortfolioUpside - totalTransactionCost;

    // Determine recommendation
    let verdict = 'neutral';
    let verdictText = 'Análise inconclusiva';
    let verdictIcon = '🤔';

    if (netGainPct >= minGainThreshold) {
      verdict = 'recommend';
      verdictText = `✅ Recomendado rebalancear (ganho líquido estimado: ${formatPercent(netGainPct)})`;
      verdictIcon = '✅';
    } else if (netGainPct < 0) {
      verdict = 'not-recommend';
      verdictText = `❌ Não vale rebalancear (custo supera o ganho)`;
      verdictIcon = '❌';
    } else {
      verdict = 'neutral';
      verdictText = `⚠️ Ganho marginal (${formatPercent(netGainPct)}) - abaixo do threshold de ${minGainThreshold}%`;
      verdictIcon = '⚠️';
    }

    return {
      valid: true,
      currentPortfolioValue,
      additionalInvestment,
      totalPortfolioValue,
      totalTransactionCost,
      totalSellValue,
      totalBuyValue,
      currentPortfolioUpside,
      recommendedPortfolioUpside,
      currentFinalValue,
      recommendedFinalValue,
      additionalGain,
      netGain,
      netGainPct,
      transactions,
      verdict,
      verdictText,
      verdictIcon,
      sharpe: recommendedPortfolio.sharpe,
      expectedReturn: recommendedPortfolio.expectedReturn
    };
  }

  function renderRebalance() {
    // Calcular custos históricos primeiro
    calculateHistoricalFees();

    // Atualizar resumo dos parâmetros históricos
    const histFeeEl = document.getElementById('historicalFeeRate');
    const notesAnalyzedEl = document.getElementById('notesAnalyzed');
    const totalVolumeEl = document.getElementById('totalVolume');
    const feeRateHintEl = document.getElementById('feeRateHint');

    if (histFeeEl) histFeeEl.textContent = historicalFees.avgFeeRate.toFixed(4) + '%';
    if (notesAnalyzedEl) notesAnalyzedEl.textContent = historicalFees.notesCount;
    if (totalVolumeEl) totalVolumeEl.textContent = formatCurrency(historicalFees.totalVolume);
    if (feeRateHintEl) feeRateHintEl.textContent = `Histórico: ${historicalFees.avgFeeRate.toFixed(4)}%`;

    const analysis = calculateRebalanceAnalysis();

    // Update verdict
    const verdictEl = document.getElementById('rebalanceVerdict');
    if (verdictEl) {
      verdictEl.className = 'rebalance-verdict ' + (analysis.valid ? analysis.verdict : '');

      let verdictContent = '';
      if (analysis.valid) {
        verdictContent = `
          <div class="verdict-icon">${analysis.verdictIcon}</div>
          <div class="verdict-content">
            <div class="verdict-text">${analysis.verdictText}</div>
            ${analysis.additionalInvestment > 0 ?
              `<div class="verdict-detail">Considerando aporte de ${formatCurrency(analysis.additionalInvestment)} (Portfolio final: ${formatCurrency(analysis.totalPortfolioValue)})</div>` : ''}
            <div class="verdict-scenarios">
              <span class="scenario">📊 Manter atual → ${formatCurrency(analysis.currentFinalValue)}</span>
              <span class="scenario">🎯 Rebalancear → ${formatCurrency(analysis.recommendedFinalValue)}</span>
            </div>
          </div>`;
      } else {
        verdictContent = `
          <div class="verdict-icon">⚠️</div>
          <div class="verdict-text">${analysis.reason || 'Dados insuficientes'}</div>`;
      }
      verdictEl.innerHTML = verdictContent;
    }

    if (!analysis.valid) {
      // Clear all metrics
      ['rebalanceCost', 'rebalanceGain', 'rebalanceNetGain', 'rebalanceSharpe',
       'volumeToSell', 'volumeToBuy', 'numOperations'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.textContent = '—';
      });
      const tbody = document.getElementById('rebalanceBody');
      if (tbody) tbody.innerHTML = '<tr><td colspan="7" class="no-data">Sem dados para análise</td></tr>';
      return;
    }

    // Update metrics
    const costEl = document.getElementById('rebalanceCost');
    if (costEl) {
      costEl.textContent = formatCurrency(analysis.totalTransactionCost);
      costEl.className = 'metric-value negative';
    }
    document.getElementById('rebalanceCostDetail').textContent =
      `${((parseFloat(document.getElementById('feeRate')?.value || 0.03) + parseFloat(document.getElementById('spreadRate')?.value || 0.10)).toFixed(2))}% sobre R$ ${formatNumber(analysis.totalSellValue + analysis.totalBuyValue, 0)}`;

    const gainEl = document.getElementById('rebalanceGain');
    if (gainEl) {
      gainEl.textContent = formatCurrency(analysis.additionalGain);
      gainEl.className = 'metric-value ' + (analysis.additionalGain >= 0 ? 'positive' : 'negative');
    }
    document.getElementById('rebalanceGainDetail').textContent =
      `Upside rec: ${formatCurrency(analysis.recommendedPortfolioUpside)} vs atual: ${formatCurrency(analysis.currentPortfolioUpside)}`;

    const netGainEl = document.getElementById('rebalanceNetGain');
    if (netGainEl) {
      netGainEl.textContent = `${formatCurrency(analysis.netGain)} (${formatPercent(analysis.netGainPct)})`;
      netGainEl.className = 'metric-value ' + (analysis.netGain >= 0 ? 'positive' : 'negative');
    }
    document.getElementById('rebalanceNetDetail').textContent =
      `Ganho esperado menos custos de transação`;

    const sharpeEl = document.getElementById('rebalanceSharpe');
    if (sharpeEl && analysis.sharpe != null) {
      sharpeEl.textContent = analysis.sharpe.toFixed(2);
    }

    // Update summary row
    document.getElementById('volumeToSell').textContent = formatCurrency(analysis.totalSellValue);
    document.getElementById('volumeToBuy').textContent = formatCurrency(analysis.totalBuyValue);
    document.getElementById('numOperations').textContent = analysis.transactions.length;

    // Render transactions table
    const tbody = document.getElementById('rebalanceBody');
    if (!tbody) return;

    tbody.innerHTML = '';

    // Sort: sells first, then buys
    const sortedTransactions = [...analysis.transactions].sort((a, b) => {
      if (a.action === 'SELL' && b.action === 'BUY') return -1;
      if (a.action === 'BUY' && b.action === 'SELL') return 1;
      return Math.abs(b.value) - Math.abs(a.value);
    });

    for (const tx of sortedTransactions) {
      const tr = document.createElement('tr');
      const actionClass = tx.action === 'BUY' ? 'action-buy' : 'action-sell';
      const actionText = tx.action === 'BUY' ? 'Comprar' : 'Vender';

      tr.innerHTML = `
        <td><strong>${tx.ticker}</strong></td>
        <td><span class="${actionClass}">${actionText}</span></td>
        <td>${tx.currentQty}</td>
        <td>${tx.targetQty}</td>
        <td class="${tx.diffQty >= 0 ? 'positive' : 'negative'}">${tx.diffQty > 0 ? '+' : ''}${tx.diffQty}</td>
        <td>${formatCurrency(tx.value)}</td>
        <td class="negative">${formatCurrency(tx.cost)}</td>
      `;
      tbody.appendChild(tr);
    }

    if (analysis.transactions.length === 0) {
      tbody.innerHTML = '<tr><td colspan="7" class="no-data">Portfolios já estão alinhados</td></tr>';
    }
  }

  function setupRebalanceControls() {
    // Setup recalculate button
    const recalcBtn = document.getElementById('recalculateBtn');
    if (recalcBtn) {
      recalcBtn.addEventListener('click', function() {
        renderRebalance();
        // Feedback visual
        this.textContent = '✓ Recalculado!';
        this.classList.add('recalculated');
        setTimeout(() => {
          this.textContent = '🔄 Recalcular Análise';
          this.classList.remove('recalculated');
        }, 1500);
      });
    }

    // Também recalcular quando os inputs mudam
    ['feeRate', 'spreadRate', 'additionalInvestment', 'minGainThreshold'].forEach(id => {
      const input = document.getElementById(id);
      if (input) {
        input.addEventListener('change', function() {
          renderRebalance();
        });
      }
    });
  }

  function renderComparison() {
    const metrics = calculatePortfolioMetrics();
    const tbody = document.getElementById('comparisonBody');
    if (!tbody) return;

    // Build maps
    const myPositions = new Map();
    for (const pos of metrics.positions) {
      if (pos.net_qty > 0) {
        const key = normalizeTickerKey(pos.symbol || pos.ticker);
        myPositions.set(key, pos);
      }
    }

    const recommended = new Map();
    for (let i = 0; i < recommendedPortfolio.stocks.length; i++) {
      const stock = recommendedPortfolio.stocks[i];
      const weight = recommendedPortfolio.weights[i] || 0;
      const key = normalizeTickerKey(stock);
      recommended.set(key, { stock, weight: weight * 100 });
    }

    // Find matches, missing, extra
    const comparison = [];
    let matchCount = 0;
    let missingCount = 0;
    let extraCount = 0;

    // Check recommended
    for (const [key, rec] of recommended) {
      const myPos = myPositions.get(key);
      if (myPos) {
        matchCount++;
        const diff = myPos.weight - rec.weight;
        comparison.push({
          ticker: rec.stock,
          status: 'match',
          realWeight: myPos.weight,
          recWeight: rec.weight,
          diff: diff,
          action: diff > 2 ? 'Reduzir' : diff < -2 ? 'Aumentar' : 'OK'
        });
      } else {
        missingCount++;
        comparison.push({
          ticker: rec.stock,
          status: 'missing',
          realWeight: 0,
          recWeight: rec.weight,
          diff: -rec.weight,
          action: 'Comprar'
        });
      }
    }

    // Check my positions not in recommended
    for (const [key, pos] of myPositions) {
      if (!recommended.has(key)) {
        extraCount++;
        comparison.push({
          ticker: pos.symbol || pos.ticker,
          status: 'extra',
          realWeight: pos.weight,
          recWeight: 0,
          diff: pos.weight,
          action: 'Vender'
        });
      }
    }

    // Update counts
    document.getElementById('matchCount').textContent = matchCount;
    document.getElementById('missingCount').textContent = missingCount;
    document.getElementById('extraCount').textContent = extraCount;

    // Sort: matches first, then missing, then extra
    comparison.sort((a, b) => {
      const order = { match: 0, missing: 1, extra: 2 };
      return order[a.status] - order[b.status];
    });

    // Render table
    tbody.innerHTML = '';
    for (const item of comparison) {
      const tr = document.createElement('tr');
      tr.classList.add('comparison-' + item.status);

      const statusBadge = {
        match: '<span class="status-badge match">✓ Em comum</span>',
        missing: '<span class="status-badge missing">⚠ Falta</span>',
        extra: '<span class="status-badge extra">✗ Não recomendada</span>'
      }[item.status];

      const actionClass = {
        'Comprar': 'action-buy',
        'Vender': 'action-sell',
        'Aumentar': 'action-buy',
        'Reduzir': 'action-sell',
        'OK': 'action-ok'
      }[item.action];

      tr.innerHTML = `
        <td><strong>${item.ticker}</strong></td>
        <td>${statusBadge}</td>
        <td>${formatPercent(item.realWeight, 1).replace('+', '')}</td>
        <td>${formatPercent(item.recWeight, 1).replace('+', '')}</td>
        <td class="${item.diff >= 0 ? 'positive' : 'negative'}">${formatPercent(item.diff, 1)}</td>
        <td><span class="action-badge ${actionClass}">${item.action}</span></td>
      `;
      tbody.appendChild(tr);
    }

    if (comparison.length === 0) {
      tbody.innerHTML = '<tr><td colspan="6" class="no-data">Sem dados para comparação</td></tr>';
    }
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // INICIALIZAÇÃO
  // ═══════════════════════════════════════════════════════════════════════════
  document.getElementById('refreshBtn')?.addEventListener('click', loadAllData);

  // Initial load
  loadAllData();
})();
