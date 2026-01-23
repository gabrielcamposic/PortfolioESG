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
  let recommendedPortfolio = { stocks: [], weights: [] };
  let processedNotesData = null;
  let portfolioHistoryData = null;
  let allocationChart = null;
  let evolutionChart = null;

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
