/**
 * Unified portfolio & analysis script
 * Handles all data loading, parsing, and rendering for portfolio.html
 */

// --- CONFIGURATION: Paths to the data files ---
const SUMMARY_CSV_PATH = 'data/portfolio_results_db.csv';
const HISTORY_CSV_PATH = 'data/portfolio_value_db.csv';
const LATEST_RUN_SUMMARY_JSON_PATH = 'data/latest_run_summary.json';
const ANALYSIS_CSV_PATH = 'data/portfolio_timeseries.csv';
const ATTRIBUTION_JSON_PATH = 'data/performance_attribution.json';

// --- UTILITY FUNCTIONS ---
function formatNumber(num, decimals = 2) {
    if (num === undefined || num === null || isNaN(num)) return 'N/A';
    return Number(num).toLocaleString(undefined, {minimumFractionDigits: decimals, maximumFractionDigits: decimals});
}
function formatDate(dateStr) {
    if (!dateStr) return 'N/A';
    const d = new Date(dateStr);
    return d.toISOString().slice(0, 10);
}
function stddev(arr) {
    const n = arr.length;
    if (n < 2) return 0;
    const mean = arr.reduce((a, b) => a + b, 0) / n;
    return Math.sqrt(arr.reduce((a, b) => a + Math.pow(b - mean, 2), 0) / (n - 1));
}
function parseCSVRow(row, colCount) {
    // Simple CSV row parser
    let cols = [], curr = '', inQuotes = false;
    for (let i = 0; i < row.length; i++) {
        let c = row[i];
        if (c === '"') inQuotes = !inQuotes;
        else if (c === ',' && !inQuotes) { cols.push(curr); curr = ''; }
        else curr += c;
    }
    cols.push(curr);
    while (cols.length < colCount) cols.push('');
    return cols;
}
async function fetchAndParseCsv(path) {
    const response = await fetch(path);
    if (!response.ok) throw new Error('CSV not found: ' + path);
    const text = await response.text();
    let rows = text.split('\n').filter(r => r.trim().length > 0);
    let header = rows[0].split(',');
    let data = rows.slice(1).map(r => parseCSVRow(r, header.length));
    return data.map(row => {
        let obj = {};
        header.forEach((h, i) => obj[h] = row[i]);
        return obj;
    });
}
async function fetchAndParseCsvRobust(path) {
    const response = await fetch(path);
    if (!response.ok) throw new Error('CSV not found: ' + path);
    const text = await response.text();
    // Try object-based parsing first
    let rows = text.split('\n').filter(r => r.trim().length > 0);
    let header = rows[0].split(',');
    let data = rows.slice(1).map(r => parseCSVRow(r, header.length));
    // If header keys are not found in first row, fallback to index-based
    if (!header.includes('date')) {
        // Fallback: return array of arrays
        return {header, data};
    }
    // Return array of objects (default)
    return data.map(row => {
        let obj = {};
        header.forEach((h, i) => obj[h] = row[i]);
        return obj;
    });
}

// --- MAIN EXECUTION ---
document.addEventListener('DOMContentLoaded', main);

async function main() {
    // --- Load risk-free rate from scorpar.txt ---
    let riskFreeRateAnnual = 0.0;
    try {
        const rfTxt = await fetch('../parameters/scorpar.txt?t=' + new Date().getTime()).then(res => res.text());
        const rfMatch = rfTxt.match(/risk_free_rate\s*=\s*([0-9.]+)/);
        if (rfMatch) riskFreeRateAnnual = parseFloat(rfMatch[1]);
    } catch (e) { riskFreeRateAnnual = 0.0; }
    const riskFreeRateDaily = Math.pow(1 + riskFreeRateAnnual, 1/252) - 1;
    loadNavbar();
    await Promise.all([
        loadPortfolioSection(riskFreeRateDaily, riskFreeRateAnnual),
        loadAnalysisSectionRobust(),
        loadFactorStyleDiagnostics(),
        loadMomentumValuationMetrics(),
        loadPerformanceAttribution()
    ]);
}

// --- PORTFOLIO SECTION ---
async function loadPortfolioSection(riskFreeRateDaily, riskFreeRateAnnual) {
    try {
        const [allSummaryData, latestRunJson, analysisData] = await Promise.all([
            fetchAndParseCsv(SUMMARY_CSV_PATH + '?t=' + new Date().getTime()),
            fetch(LATEST_RUN_SUMMARY_JSON_PATH + '?t=' + new Date().getTime()).then(res => res.json()),
            fetchAndParseCsv(ANALYSIS_CSV_PATH + '?t=' + new Date().getTime())
        ]);
        const twelveMonthsAgo = new Date();
        twelveMonthsAgo.setFullYear(twelveMonthsAgo.getFullYear() - 1);
        twelveMonthsAgo.setHours(0, 0, 0, 0);
        const filteredSummaryData = allSummaryData.filter(row => {
            const timestamp = new Date(row.timestamp);
            return timestamp && timestamp >= twelveMonthsAgo;
        }).sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));
        displayMergedPortfolioSummary(latestRunJson.best_portfolio_details, latestRunJson.last_updated_run_id, analysisData, riskFreeRateDaily, riskFreeRateAnnual);
        createLastPortfolioPieChart(latestRunJson.best_portfolio_details, latestRunJson.last_updated_run_id);
        renderOptimalPortfoliosStackedBarChart(filteredSummaryData);
        // Show run ID at the bottom of the page
        const runidFootnote = document.getElementById('runid-footnote');
        runidFootnote.style.display = 'block';
        runidFootnote.innerHTML = `<b>Latest Run ID:</b> ${latestRunJson.last_updated_run_id}`;
    } catch (error) {
        document.getElementById('bestPortfolioTable').getElementsByTagName('tbody')[0].innerHTML = `<tr><td colspan="2" class="status-error-row">Error loading last portfolio details.</td></tr>`;
        document.getElementById('optimalPortfoliosStackedBarChart').textContent = 'Error loading chart data.';
    }
}

function displayMergedPortfolioSummary(details, runId, analysisData, riskFreeRateDaily, riskFreeRateAnnual) {
    const tableBody = document.getElementById('bestPortfolioTable').getElementsByTagName('tbody')[0];
    const tableHead = document.getElementById('bestPortfolioTable').getElementsByTagName('thead')[0];
    tableBody.innerHTML = '';
    // Update table header with dynamic benchmark names
    let bench1_name = details.benchmark1_name || '^BVSP';
    let bench2_name = details.benchmark2_name || 'ISUS11.SA';
    tableHead.innerHTML = `<tr>
        <th>Metric</th>
        <th>Portfolio</th>
        <th>${bench1_name}</th>
        <th>${bench2_name}</th>
    </tr>`;
    if (!details || !analysisData || analysisData.length === 0) {
        tableBody.innerHTML = `<tr><td colspan="4" style="text-align:center;">No portfolio found in the last run (ID: ${runId || 'N/A'}).</td></tr>`;
        return;
    }
    // Filter analysisData to last 12 months
    const twelveMonthsAgo = new Date();
    twelveMonthsAgo.setFullYear(twelveMonthsAgo.getFullYear() - 1);
    twelveMonthsAgo.setHours(0, 0, 0, 0);
    const filtered = analysisData.filter(r => {
        const d = new Date(r['date']);
        return d && d >= twelveMonthsAgo;
    });
    if (!filtered || filtered.length === 0) {
        tableBody.innerHTML = `<tr><td colspan="4" style="text-align:center;">No portfolio data for the last 12 months.</td></tr>`;
        return;
    }
    let lastIdx = filtered.length - 1;
    let firstIdx = 0;
    // Recalculate real values to start at 1000 for the filtered window
    function recalcRealValues(dailyReturns) {
        let values = [1000];
        for (let i = 0; i < dailyReturns.length; i++) {
            values.push(values[values.length-1] * (1 + dailyReturns[i]));
        }
        return values.slice(1); // remove initial 1000 for alignment with dates
    }
    let portfolio_real = recalcRealValues(filtered.map(r => parseFloat(r['portfolio_daily_return'])));
    let bench1_real = recalcRealValues(filtered.map(r => parseFloat(r['benchmark1_daily_return'])));
    let bench2_real = recalcRealValues(filtered.map(r => parseFloat(r['benchmark2_daily_return'])));
    let date_start = filtered[firstIdx]['date'];
    let date_end = filtered[lastIdx]['date'];
    // Daily returns
    let portfolio_daily = filtered.map(r => parseFloat(r['portfolio_daily_return']));
    let bench1_daily = filtered.map(r => parseFloat(r['benchmark1_daily_return']));
    let bench2_daily = filtered.map(r => parseFloat(r['benchmark2_daily_return']));
    // Annual return calculation
    function annualReturn(dailyReturns) {
        let prod = dailyReturns.reduce((acc, r) => acc * (1 + r), 1);
        let N = dailyReturns.length;
        return (Math.pow(prod, 252 / N) - 1) * 100;
    }
    // Annual volatility calculation
    function annualVolatility(dailyReturns) {
        return stddev(dailyReturns) * Math.sqrt(252) * 100;
    }
    // Sharpe ratio calculation (risk-free rate = 0)
    function sharpeRatio(dailyReturns) {
        let ar = annualReturn(dailyReturns) / 100;
        let av = annualVolatility(dailyReturns) / 100;
        if (av === 0) return '';
        return ar / av;
    }
    // Downside deviation calculation
    function downsideDeviation(returns, target=0) {
        // Only consider returns below the target (usually 0)
        const downside = returns.filter(r => r < target);
        if (downside.length === 0) return 0;
        const squared = downside.map(r => Math.pow(r - target, 2));
        return Math.sqrt(squared.reduce((a, b) => a + b, 0) / downside.length);
    }
    // Sortino ratio calculation
    function sortinoRatio(returns, target=0) {
        const meanReturn = returns.reduce((a, b) => a + b, 0) / returns.length;
        const dd = downsideDeviation(returns, target);
        if (dd === 0) return '';
        return meanReturn / dd;
    }
    // Maximum Drawdown calculation
    function maxDrawdown(values) {
        if (!values || values.length < 2) return 0;
        let maxDD = 0;
        let peak = values[0];
        for (let i = 1; i < values.length; i++) {
            if (values[i] > peak) peak = values[i];
            const dd = (peak - values[i]) / peak;
            if (dd > maxDD) maxDD = dd;
        }
        return maxDD * 100; // as percentage
    }
    // CAGR calculation
    function CAGR(values, periodsPerYear=252) {
        const n = values.length;
        if (n < 2) return 0;
        const start = values[0];
        const end = values[n-1];
        const years = n / periodsPerYear;
        return (Math.pow(end / start, 1 / years) - 1) * 100;
    }
    // Calmar Ratio calculation
    function calmarRatio(values) {
        const cagr = CAGR(values);
        const mdd = maxDrawdown(values);
        if (mdd === 0) return '';
        return cagr / mdd;
    }
    // Value at Risk (VaR) calculation (historical, 95%)
    function valueAtRisk95(returns) {
        if (!returns || returns.length === 0) return 'N/A';
        const sorted = [...returns].sort((a, b) => a - b);
        const idx = Math.floor(returns.length * 0.05);
        return sorted[idx] * 100; // as percentage
    }
    // Beta calculation (vs benchmark 1)
    function beta(portfolioReturns, benchmarkReturns) {
        if (!portfolioReturns || !benchmarkReturns || portfolioReturns.length !== benchmarkReturns.length) return 'N/A';
        const n = portfolioReturns.length;
        const meanPortfolio = portfolioReturns.reduce((a, b) => a + b, 0) / n;
        const meanBenchmark = benchmarkReturns.reduce((a, b) => a + b, 0) / n;
        let cov = 0, varBench = 0;
        for (let i = 0; i < n; i++) {
            cov += (portfolioReturns[i] - meanPortfolio) * (benchmarkReturns[i] - meanBenchmark);
            varBench += Math.pow(benchmarkReturns[i] - meanBenchmark, 2);
        }
        cov /= n;
        varBench /= n;
        if (varBench === 0) return 'N/A';
        return cov / varBench;
    }
    // Alpha (Jensen's Alpha) calculation (vs benchmark 1, using risk-free rate)
    function alpha(portfolioReturns, benchmarkReturns, rfDaily) {
        if (!portfolioReturns || !benchmarkReturns || portfolioReturns.length !== benchmarkReturns.length) return 'N/A';
        const n = portfolioReturns.length;
        const meanPortfolio = portfolioReturns.reduce((a, b) => a + b, 0) / n;
        const meanBenchmark = benchmarkReturns.reduce((a, b) => a + b, 0) / n;
        const b = beta(portfolioReturns, benchmarkReturns);
        if (b === 'N/A') return 'N/A';
        // Jensen's Alpha: meanPortfolio - [rfDaily + b * (meanBenchmark - rfDaily)]
        return (meanPortfolio - (rfDaily + b * (meanBenchmark - rfDaily))) * 100; // as percentage
    }
    // Metrics
    const metrics = [
        {
            name: 'Final Value',
            portfolio: formatNumber(portfolio_real[lastIdx], 1),
            bench1: formatNumber(bench1_real[lastIdx], 1),
            bench2: formatNumber(bench2_real[lastIdx], 1)
        },
        {
            name: 'Sharpe Ratio',
            portfolio: formatNumber(sharpeRatio(portfolio_daily), 3),
            bench1: formatNumber(sharpeRatio(bench1_daily), 3),
            bench2: formatNumber(sharpeRatio(bench2_daily), 3)
        },
        {
            name: 'Sortino Ratio',
            portfolio: formatNumber(sortinoRatio(portfolio_daily), 3),
            bench1: formatNumber(sortinoRatio(bench1_daily), 3),
            bench2: formatNumber(sortinoRatio(bench2_daily), 3)
        },
        {
            name: 'Daily Volatility (%)',
            portfolio: formatNumber(stddev(portfolio_daily) * 100, 2),
            bench1: formatNumber(stddev(bench1_daily) * 100, 2),
            bench2: formatNumber(stddev(bench2_daily) * 100, 2)
        },
        {
            name: 'Annualized Volatility (%)',
            portfolio: formatNumber(annualVolatility(portfolio_daily), 1),
            bench1: formatNumber(annualVolatility(bench1_daily), 1),
            bench2: formatNumber(annualVolatility(bench2_daily), 1)
        },
        {
            name: 'Maximum Drawdown (%)',
            portfolio: formatNumber(maxDrawdown(portfolio_real), 2),
            bench1: formatNumber(maxDrawdown(bench1_real), 2),
            bench2: formatNumber(maxDrawdown(bench2_real), 2)
        },
        {
            name: 'Calmar Ratio',
            portfolio: formatNumber(calmarRatio(portfolio_real), 3),
            bench1: formatNumber(calmarRatio(bench1_real), 3),
            bench2: formatNumber(calmarRatio(bench2_real), 3)
        },
        {
            name: 'Daily Return (%)',
            portfolio: formatNumber((portfolio_daily.reduce((a, b) => a + b, 0) / portfolio_daily.length) * 100, 2),
            bench1: formatNumber((bench1_daily.reduce((a, b) => a + b, 0) / bench1_daily.length) * 100, 2),
            bench2: formatNumber((bench2_daily.reduce((a, b) => a + b, 0) / bench2_daily.length) * 100, 2)
        },
        {
            name: 'CAGR (%)',
            portfolio: formatNumber(CAGR(portfolio_real), 1),
            bench1: formatNumber(CAGR(bench1_real), 1),
            bench2: formatNumber(CAGR(bench2_real), 1)
        },
        {
            name: 'Value at Risk (VaR 95%)',
            portfolio: formatNumber(valueAtRisk95(portfolio_daily), 2),
            bench1: formatNumber(valueAtRisk95(bench1_daily), 2),
            bench2: formatNumber(valueAtRisk95(bench2_daily), 2)
        },
        {
            name: 'Beta vs Benchmark 1',
            portfolio: formatNumber(beta(portfolio_daily, bench1_daily), 3),
            bench1: '-',
            bench2: '-'
        },
        {
            name: 'Alpha (Jensen\'s Alpha)',
            portfolio: formatNumber(alpha(portfolio_daily, bench1_daily, riskFreeRateDaily), 3),
            bench1: '-',
            bench2: '-'
        }
    ];
    // --- Metric Explanations for Tooltips ---
    const metricExplanations = {
        'Final Value': {
            def: 'Valor final do portfólio ou benchmark após 12 meses.',
            formula: 'Valor inicial × (1 + retorno diário acumulado)',
            use: 'Mostra o crescimento absoluto do investimento.',
            interp: 'Quanto maior, melhor. Compare com benchmarks.'
        },
        'Sharpe Ratio': {
            def: 'Mede o retorno excedente por unidade de risco.',
            formula: '(Retorno anualizado - Taxa livre de risco) / Volatilidade anualizada',
            use: 'Avalia eficiência do risco. Útil para comparar portfólios.',
            interp: 'Maior é melhor (>1 é bom). Compare com benchmarks.'
        },
        'Sortino Ratio': {
            def: 'Similar ao Sharpe, mas penaliza apenas retornos negativos.',
            formula: '(Retorno médio - Taxa livre de risco) / Desvio padrão das quedas',
            use: 'Foca no risco de queda. Útil para investidores avessos a perdas.',
            interp: 'Maior é melhor. Compare com benchmarks.'
        },
        'Daily Volatility (%)': {
            def: 'Desvio padrão dos retornos diários.',
            formula: 'Desvio padrão dos retornos × 100',
            use: 'Mede a variação diária dos retornos.',
            interp: 'Menor é melhor. Compare com benchmarks.'
        },
        'Annualized Volatility (%)': {
            def: 'Volatilidade projetada para 1 ano.',
            formula: 'Volatilidade diária × √252 × 100',
            use: 'Compara o risco anualizado.',
            interp: 'Menor é melhor. Compare com benchmarks.'
        },
        'Maximum Drawdown (%)': {
            def: 'Maior queda percentual do pico ao fundo.',
            formula: '(Pico - Fundo) / Pico × 100',
            use: 'Avalia o pior cenário de perda.',
            interp: 'Menor é melhor. Compare com benchmarks.'
        },
        'Calmar Ratio': {
            def: 'Retorno ajustado pelo risco de drawdown.',
            formula: 'CAGR / Maximum Drawdown',
            use: 'Compara retorno e risco extremo.',
            interp: 'Maior é melhor. Compare com benchmarks.'
        },
        'Daily Return (%)': {
            def: 'Retorno médio diário.',
            formula: 'Média dos retornos diários × 100',
            use: 'Mostra o crescimento médio diário.',
            interp: 'Maior é melhor. Compare com benchmarks.'
        },
        'CAGR (%)': {
            def: 'Taxa de crescimento anual composta.',
            formula: '[(Valor final / Valor inicial)^(1/anos)] - 1 × 100',
            use: 'Compara crescimento anualizado.',
            interp: 'Maior é melhor. Compare com benchmarks.'
        },
        'Value at Risk (VaR 95%)': {
            def: 'Pior perda esperada em 1 dia com 95% de confiança.',
            formula: 'Percentil 5% dos retornos diários × 100',
            use: 'Avalia risco de perdas extremas.',
            interp: 'Menor (menos negativo) é melhor.'
        },
        'Beta vs Benchmark 1': {
            def: 'Sensibilidade do portfólio ao benchmark 1.',
            formula: 'Covariância(portfólio, benchmark) / Variância(benchmark)',
            use: 'Mede exposição ao risco de mercado.',
            interp: 'Beta ≈ 1: igual ao mercado; <1: menos volátil; >1: mais volátil.'
        },
        "Alpha (Jensen's Alpha)": {
            def: 'Retorno excedente ajustado ao risco.',
            formula: 'Retorno portfólio - [Taxa livre de risco + Beta × (Retorno benchmark - Taxa livre de risco)]',
            use: 'Avalia se o portfólio superou o esperado pelo risco.',
            interp: 'Maior é melhor. Compare com benchmarks.'
        },
        'Annual Risk Free Rate (%)': {
            def: 'Taxa livre de risco anual utilizada nas métricas.',
            formula: 'Definida em scorpar.txt',
            use: 'Referência para Sharpe, Sortino, Alpha.',
            interp: 'Não se compara, é parâmetro de referência.'
        }
    };
    const rowsHtml = metrics.map(row => {
        let portfolioCellStyle = '';
        // Compare as numbers for all metrics
        const pf = parseFloat(row.portfolio.replace(/[^0-9.-]+/g, ''));
        const b1 = parseFloat(row.bench1.replace(/[^0-9.-]+/g, ''));
        const b2 = parseFloat(row.bench2.replace(/[^0-9.-]+/g, ''));
        let color = '';
        if (!isNaN(pf) && !isNaN(b1) && !isNaN(b2)) {
            // For metrics where higher is better
            const higherIsBetter = [
                'Final Value',
                'Sharpe Ratio',
                'Sortino Ratio',
                'Daily Return (%)',
                'CAGR (%)',
                'Calmar Ratio'
            ];
            // For metrics where lower is better
            const lowerIsBetter = [
                'Daily Volatility (%)',
                'Annualized Volatility (%)',
                'Maximum Drawdown (%)'
            ];
            if (higherIsBetter.includes(row.name)) {
                if (pf === Math.max(pf, b1, b2)) {
                    portfolioCellStyle = 'color:green !important;font-weight:bold !important;';
                    color = 'green';
                } else if (pf === Math.min(pf, b1, b2)) {
                    portfolioCellStyle = 'color:red !important;font-weight:bold !important;';
                    color = 'red';
                } else {
                    portfolioCellStyle = 'color:#222 !important;font-weight:normal !important;';
                    color = 'black';
                }
            } else if (lowerIsBetter.includes(row.name)) {
                if (pf === Math.min(pf, b1, b2)) {
                    portfolioCellStyle = 'color:green !important;font-weight:bold !important;';
                    color = 'green';
                } else if (pf === Math.max(pf, b1, b2)) {
                    portfolioCellStyle = 'color:red !important;font-weight:bold !important;';
                    color = 'red';
                } else {
                    portfolioCellStyle = 'color:#222 !important;font-weight:normal !important;';
                    color = 'black';
                }
            }
        }
        return `
            <tr>
                <td>${row.name}</td>
                <td style="text-align:right;${portfolioCellStyle}">${row.portfolio}</td>
                <td style="text-align:right;">${row.bench1}</td>
                <td style="text-align:right;">${row.bench2}</td>
            </tr>
        `;
    }).join('');
    tableBody.innerHTML = rowsHtml;
    // --- Render metrics table without info/helper text or icons ---
    metrics.forEach(m => {
        tableBody.innerHTML += `<tr><td>${m.name}</td><td>${m.portfolio}</td><td>${m.bench1}</td><td>${m.bench2}</td></tr>`;
    });
    // Add risk-free rate row at the end (no tooltip)
    tableBody.innerHTML += `<tr><td>Annual Risk Free Rate (%)</td><td style='text-align:right;'>${(riskFreeRateAnnual * 100).toFixed(2)}</td><td></td><td></td></tr>`;

    // --- Populate the new compact metrics panel (if present in DOM) ---
    try {
        const setText = (id, txt) => {
            const el = document.getElementById(id);
            if (el) el.textContent = (txt === undefined || txt === null) ? 'N/A' : String(txt);
        };
        // Performance
        setText('perf_final_value', formatNumber(portfolio_real[lastIdx], 1));
        setText('perf_daily_return', formatNumber((portfolio_daily.reduce((a, b) => a + b, 0) / portfolio_daily.length) * 100, 2));
        setText('perf_cagr', formatNumber(CAGR(portfolio_real), 1));
        setText('perf_alpha', formatNumber(alpha(portfolio_daily, bench1_daily, riskFreeRateDaily), 3));
        setText('perf_beta', formatNumber(beta(portfolio_daily, bench1_daily), 3));
        setText('perf_rf_rate', (riskFreeRateAnnual * 100).toFixed(2));
        // Risk
        setText('risk_daily_vol', formatNumber(stddev(portfolio_daily) * 100, 2));
        setText('risk_annual_vol', formatNumber(annualVolatility(portfolio_daily), 1));
        setText('risk_max_drawdown', formatNumber(maxDrawdown(portfolio_real), 2));
        setText('risk_var95', formatNumber(valueAtRisk95(portfolio_daily), 2));
        // Risk-adjusted
        setText('ra_sharpe', formatNumber(sharpeRatio(portfolio_daily), 3));
        setText('ra_sortino', formatNumber(sortinoRatio(portfolio_daily), 3));
        setText('ra_calmar', formatNumber(calmarRatio(portfolio_real), 3));
    } catch (e) {
        // Fail silently - page will still show table fallback
        console.warn('Could not populate compact metrics panel:', e);
    }
}
// --- GLOBAL COLOR MAP FOR TICKERS ---
const COLOR_PALETTE = [
    '#1f77b4','#ff7f0e','#2ca02c','#d62728','#9467bd','#8c564b','#e377c2','#7f7f7f','#bcbd22','#17becf',
    '#f44336','#9c27b0','#3f51b5','#03a9f4','#009688','#4caf50','#cddc39','#ffeb3b','#ffc107','#ff9800',
    '#bdbdbd','#607d8b','#795548','#b71c1c','#880e4f','#4a148c','#01579b','#006064','#1b5e20','#827717',
    '#fbc02d','#e65100','#3e2723','#263238'
];
const TICKER_COLOR_MAP = {};
let colorIndex = 0;
function getColorForTicker(ticker) {
    if (!TICKER_COLOR_MAP[ticker]) {
        TICKER_COLOR_MAP[ticker] = COLOR_PALETTE[colorIndex % COLOR_PALETTE.length];
        colorIndex++;
    }
    return TICKER_COLOR_MAP[ticker];
}
function createLastPortfolioPieChart(details, runId) {
    const pieDiv = document.getElementById('lastPortfolioPieChart');
    pieDiv.innerHTML = '';
    if (!details || !details.stocks || !details.weights) return;
    // Use standardized color for each stock
    const colors = details.stocks.map(ticker => getColorForTicker(ticker));
    Plotly.newPlot(pieDiv, [{
        type: 'bar',
        orientation: 'h',
        x: details.weights,
        y: details.stocks,
        marker: {color: colors},
        text: details.weights.map(w => (parseFloat(w) * 100).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2}) + '%'),
        textposition: 'auto',
        hoverinfo: 'y+x'
    }], {
        title: {
            text: 'Portfolio Composition',
            font: {size: 20}
        },
        annotations: [{
            text: `Run ID: <span style='font-size:13px;'>${runId || 'N/A'}</span>`,
            xref: 'paper', yref: 'paper',
            x: 1, y: 1.13, showarrow: false, xanchor: 'right', yanchor: 'top',
            font: {size: 13, color: '#666'}
        }],
        height: 300,
        showlegend: false,
        margin: {l: 120, r: 40, t: 70, b: 40},
        xaxis: {visible: false},
        yaxis: {title: 'Stock'},
    }, {responsive: true});
}

function renderOptimalPortfoliosStackedBarChart(summaryData) {
    const chartDiv = document.getElementById('optimalPortfoliosStackedBarChart');
    chartDiv.innerHTML = '';
    if (!summaryData || summaryData.length === 0) {
        chartDiv.textContent = 'No portfolio data found for the last 12 months.';
        return;
    }
    // Parse stocks and weights for each run
    const xLabels = summaryData.map(row => {
        const runId = row.run_id || row.runID || '';
        return runId ? `<span style='font-size:13px;color:#222;'>${runId}</span>` : '';
    });
    let allStocks = new Set();
    summaryData.forEach(row => {
        let stocks = row.stocks.replace(/"/g, '').split(',');
        stocks.forEach(s => allStocks.add(s));
    });
    allStocks = Array.from(allStocks);
    // Build traces for each stock, using standardized color
    const traces = allStocks.map((stock) => {
        return {
            x: xLabels,
            y: summaryData.map(row => {
                let stocks = row.stocks.replace(/"/g, '').split(',');
                let weights = row.weights.replace(/"/g, '').split(',').map(parseFloat);
                let i = stocks.indexOf(stock);
                return i >= 0 ? weights[i] * 100 : 0;
            }),
            name: stock,
            type: 'bar',
            marker: {color: getColorForTicker(stock)}
        };
    });
    // Check if the last bar (latest run) is missing any stocks from the latest run
    const lastRow = summaryData[summaryData.length - 1];
    let lastStocks = lastRow.stocks.replace(/"/g, '').split(',');
    let missingStocks = allStocks.filter(s => !lastStocks.includes(s));
    let annotations = [];
    if (missingStocks.length > 0) {
        annotations.push({
            text: `Note: Some stocks (e.g., ${missingStocks.slice(0,3).join(', ')}${missingStocks.length>3?', ...':''}) are not present in the latest run.`,
            xref: 'paper', yref: 'paper',
            x: 0, y: 1.18, showarrow: false, xanchor: 'left', yanchor: 'top',
            font: {size: 12, color: '#b00'}
        });
    }
    Plotly.newPlot(chartDiv, traces, {
        barmode: 'stack',
        title: {
            text: 'Portfolio Composition (Last 12 Months)',
            font: {size: 18}
        },
        xaxis: {title: 'Run ID', tickangle: -30, automargin: true},
        yaxis: {title: 'Weight (%)', range: [0, 100]},
        legend: {
            orientation: 'h',
            y: -0.25, // below x-axis
            x: 0.5,
            xanchor: 'center',
            yanchor: 'top',
            font: {size: 11},
            bgcolor: 'rgba(255,255,255,0.95)',
            bordercolor: '#ccc',
            borderwidth: 1
        },
        height: 360,
        margin: {b: 110, t: 80, l: 60, r: 20}, // more bottom margin for legend
        annotations: annotations
    }, {responsive: true});
}

// --- ANALYSIS SECTION ---
async function loadAnalysisSectionRobust() {
    try {
        let analysisData = await fetchAndParseCsvRobust(ANALYSIS_CSV_PATH + '?t=' + new Date().getTime());
        // If fallback, convert to object array
        if (Array.isArray(analysisData.data)) {
            const header = analysisData.header;
            analysisData = analysisData.data.map(row => {
                let obj = {};
                header.forEach((h, i) => obj[h] = row[i]);
                return obj;
            });
        }
        renderAnalysisChartsAndTable(analysisData);
    } catch (err) {
        document.getElementById('analysis-timeseries-chart').innerText = 'Error loading data.';
        document.getElementById('analysis-dailyreturns-chart').innerText = 'Error loading data.';
    }
}

function renderAnalysisChartsAndTable(data) {
    if (!data || data.length === 0) return;
    document.getElementById('analysis-timeseries-chart').innerHTML = '';
    document.getElementById('analysis-dailyreturns-chart').innerHTML = '';
    // Filter to last 12 months
    const twelveMonthsAgo = new Date();
    twelveMonthsAgo.setFullYear(twelveMonthsAgo.getFullYear() - 1);
    twelveMonthsAgo.setHours(0, 0, 0, 0);
    const filtered = data.filter(r => {
        const d = new Date(r['date']);
        return d && d >= twelveMonthsAgo;
    });
    if (!filtered || filtered.length === 0) return;
    // Get columns
    const header = Object.keys(filtered[0]);
    const col = name => header.indexOf(name);
    let dates = filtered.map(r => r['date']);
    let portfolio_daily = filtered.map(r => parseFloat(r['portfolio_daily_return']));
    let bench1_daily = filtered.map(r => parseFloat(r['benchmark1_daily_return']));
    let bench2_daily = filtered.map(r => parseFloat(r['benchmark2_daily_return']));
    let bench1_name = filtered[0]['benchmark1_name'];
    let bench2_name = filtered[0]['benchmark2_name'];
    let run_id = filtered[0]['run_id'];
    // Ensure first daily return is zero for correct starting value
    if (portfolio_daily.length > 0) portfolio_daily[0] = 0;
    if (bench1_daily.length > 0) bench1_daily[0] = 0;
    if (bench2_daily.length > 0) bench2_daily[0] = 0;
    // Recalculate cumulative returns so first value is 1000
    function recalcAccumReturns(dailyReturns) {
        let values = [1000];
        for (let i = 0; i < dailyReturns.length; i++) {
            values.push(values[values.length-1] * (1 + dailyReturns[i]));
        }
        return values.slice(1); // remove initial 1000 for alignment with dates
    }
    let portfolio_accum = recalcAccumReturns(portfolio_daily);
    let bench1_accum = recalcAccumReturns(bench1_daily);
    let bench2_accum = recalcAccumReturns(bench2_daily);
    Plotly.newPlot('analysis-timeseries-chart', [
        {x: dates, y: portfolio_accum, name: `Portfolio (${run_id})`, mode: 'lines', line: {color: '#1f77b4'}},
        {x: dates, y: bench1_accum, name: bench1_name, mode: 'lines', line: {color: '#ff7f0e'}},
        {x: dates, y: bench2_accum, name: bench2_name, mode: 'lines', line: {color: '#2ca02c'}}
    ], {
        title: 'Value Over Time (Last 12 Months)',
        xaxis: {title: 'Date'},
        yaxis: {title: 'Value', tickformat: '.2f', separatethousands: true},
        legend: {orientation: 'h'},
        height: 500,
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(0,0,0,0)',
        font: { color: '#333' }
    }, {responsive: true});
    // Daily returns chart
    Plotly.newPlot('analysis-dailyreturns-chart', [
        {x: dates, y: portfolio_daily, name: `Portfolio (${run_id})`, mode: 'lines', line: {color: '#1f77b4'}},
        {x: dates, y: bench1_daily, name: bench1_name, mode: 'lines', line: {color: '#ff7f0e'}},
        {x: dates, y: bench2_daily, name: bench2_name, mode: 'lines', line: {color: '#2ca02c'}}
    ], {
        title: 'Daily Returns (Last 12 Months)',
        xaxis: {title: 'Date'},
        yaxis: {title: 'Daily Return', tickformat: ',.2%', separatethousands: true},
        legend: {orientation: 'h'},
        height: 400,
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(0,0,0,0)',
        font: { color: '#333' }
    }, {responsive: true});
}

// --- FACTOR & STYLE DIAGNOSTICS SECTION ---
async function loadFactorStyleDiagnostics() {
    try {
        const latestRunJson = await fetch(LATEST_RUN_SUMMARY_JSON_PATH + '?t=' + new Date().getTime()).then(res => res.json());
        const details = latestRunJson.best_portfolio_details;

        // Render Sector Exposure Chart
        renderSectorExposureChart(details.sector_exposure);

        // Render Concentration Risk Metrics
        renderConcentrationRisk(details.concentration_risk);

        // Render Factor Tilts Table
        await renderFactorTilts(details);
    } catch (error) {
        console.error('Error loading Factor & Style Diagnostics:', error);
        document.getElementById('sectorExposureChart').textContent = 'Error loading data.';
        document.getElementById('concentrationRiskTable').getElementsByTagName('tbody')[0].innerHTML =
            '<tr><td colspan="2" class="status-error-row">Error loading data.</td></tr>';
        document.getElementById('factorTiltsTable').getElementsByTagName('tbody')[0].innerHTML =
            '<tr><td colspan="5" class="status-error-row">Error loading data.</td></tr>';
    }
}

function renderSectorExposureChart(sectorExposure) {
    if (!sectorExposure) {
        document.getElementById('sectorExposureChart').textContent = 'No sector data available.';
        return;
    }

    const sectors = Object.keys(sectorExposure);
    const weights = Object.values(sectorExposure).map(w => w * 100); // Convert to percentage

    const data = [{
        type: 'bar',
        x: sectors,
        y: weights,
        marker: {
            color: sectors.map(s => getColorForTicker(s)), // Reuse color function
            line: {color: '#333', width: 1}
        },
        text: weights.map(w => w.toFixed(2) + '%'),
        textposition: 'outside',
        hovertemplate: '%{x}<br>%{y:.2f}%<extra></extra>'
    }];

    const layout = {
        title: {
            text: 'Portfolio Allocation by Sector',
            font: {size: 18}
        },
        xaxis: {
            title: 'Sector',
            tickangle: -45,
            automargin: true
        },
        yaxis: {
            title: 'Allocation (%)',
            tickformat: '.1f'
        },
        height: 400,
        margin: {b: 120, t: 60, l: 60, r: 40},
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(0,0,0,0)',
        font: { color: '#333' }
    };

    Plotly.newPlot('sectorExposureChart', data, layout, {responsive: true});
}

function renderConcentrationRisk(concentrationRisk) {
    if (!concentrationRisk) {
        document.getElementById('concentrationRiskTable').getElementsByTagName('tbody')[0].innerHTML =
            '<tr><td colspan="2" style="text-align: center;">No concentration risk data available.</td></tr>';
        return;
    }

    // Concentration Risk Metrics Table
    const tbody = document.getElementById('concentrationRiskTable').getElementsByTagName('tbody')[0];
    const hhi = concentrationRisk.hhi;
    const top5Pct = concentrationRisk.top_5_holdings_pct * 100;

    // Interpret HHI
    let hhiInterpretation = '';
    if (hhi < 0.15) {
        hhiInterpretation = 'Low concentration (diversified)';
    } else if (hhi < 0.25) {
        hhiInterpretation = 'Moderate concentration';
    } else {
        hhiInterpretation = 'High concentration';
    }

    tbody.innerHTML = `
        <tr>
            <td>Herfindahl-Hirschman Index (HHI)</td>
            <td style="text-align: right;">${formatNumber(hhi, 4)}</td>
        </tr>
        <tr>
            <td>HHI Interpretation</td>
            <td style="text-align: right;">${hhiInterpretation}</td>
        </tr>
        <tr>
            <td>Top 5 Holdings %</td>
            <td style="text-align: right;">${formatNumber(top5Pct, 2)}%</td>
        </tr>
    `;

    // Top 5 Holdings Table
    const top5Tbody = document.getElementById('top5HoldingsTable').getElementsByTagName('tbody')[0];
    const top5Holdings = concentrationRisk.top_5_holdings || [];

    if (top5Holdings.length === 0) {
        top5Tbody.innerHTML = '<tr><td colspan="2" style="text-align: center;">No data available.</td></tr>';
    } else {
        top5Tbody.innerHTML = top5Holdings.map(h => `
            <tr>
                <td>${h.stock}</td>
                <td style="text-align: right;">${formatNumber(h.weight * 100, 2)}%</td>
            </tr>
        `).join('');
    }
}

async function renderFactorTilts(portfolioDetails) {
    const tbody = document.getElementById('factorTiltsTable').getElementsByTagName('tbody')[0];

    try {
        // Load analysis data to calculate factor tilts
        const analysisData = await fetchAndParseCsv(ANALYSIS_CSV_PATH + '?t=' + new Date().getTime());

        if (!analysisData || analysisData.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" style="text-align: center;">No analysis data available for factor comparison.</td></tr>';
            return;
        }

        // Filter to last 12 months
        const twelveMonthsAgo = new Date();
        twelveMonthsAgo.setFullYear(twelveMonthsAgo.getFullYear() - 1);
        const filtered = analysisData.filter(r => {
            const d = new Date(r['date']);
            return d && d >= twelveMonthsAgo;
        });

        if (filtered.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" style="text-align: center;">Insufficient data for factor comparison.</td></tr>';
            return;
        }

        // Calculate annualized returns for portfolio and benchmarks
        function calculateCAGR(dailyReturns) {
            let prod = dailyReturns.reduce((acc, r) => acc * (1 + parseFloat(r)), 1);
            let N = dailyReturns.length;
            return (Math.pow(prod, 252 / N) - 1) * 100;
        }

        const portfolioReturns = filtered.map(r => parseFloat(r['portfolio_daily_return']));
        const portfolioCagr = calculateCAGR(portfolioReturns);

        // Get benchmark names
        const bench1Name = filtered[0]['benchmark1_name'] || '^BVSP';
        const bench2Name = filtered[0]['benchmark2_name'] || 'ISUS11.SA';

        // Load benchmark data for Small Cap (SMAL11.SA) and Dividend (IDIV.SA) if available
        const benchmarkData = await loadBenchmarkComparison(filtered);

        // Portfolio-weighted P/E (Value tilt)
        const portfolioPE = portfolioDetails.portfolio_weighted_pe;

        // Build Factor Tilts rows
        const rows = [];

        // 1. Small vs Large Cap (if SMAL11.SA data is available)
        if (benchmarkData.smal11) {
            const tilt = portfolioCagr - benchmarkData.smal11.cagr;
            const interpretation = tilt > 0 ? 'Outperforming small caps' : tilt < 0 ? 'Underperforming small caps (large cap tilt)' : 'Neutral';
            rows.push({
                factor: 'Small vs Large Cap',
                portfolio: formatNumber(portfolioCagr, 2) + '%',
                benchmark: `SMAL11.SA: ${formatNumber(benchmarkData.smal11.cagr, 2)}%`,
                tilt: formatNumber(tilt, 2) + '%',
                interpretation: interpretation
            });
        } else {
            rows.push({
                factor: 'Small vs Large Cap',
                portfolio: 'N/A',
                benchmark: 'SMAL11.SA data not available',
                tilt: 'N/A',
                interpretation: 'Unable to calculate'
            });
        }

        // 2. Dividend Tilt (if IDIV.SA data is available)
        if (benchmarkData.idiv) {
            const tilt = portfolioCagr - benchmarkData.idiv.cagr;
            const interpretation = tilt > 0 ? 'Outperforming dividend stocks' : tilt < 0 ? 'Underperforming dividend stocks' : 'Neutral';
            rows.push({
                factor: 'Dividend Tilt',
                portfolio: formatNumber(portfolioCagr, 2) + '%',
                benchmark: `IDIV.SA: ${formatNumber(benchmarkData.idiv.cagr, 2)}%`,
                tilt: formatNumber(tilt, 2) + '%',
                interpretation: interpretation
            });
        } else {
            rows.push({
                factor: 'Dividend Tilt',
                portfolio: 'N/A',
                benchmark: 'IDIV.SA data not available',
                tilt: 'N/A',
                interpretation: 'Unable to calculate'
            });
        }

        // 3. Value vs Growth (Forward P/E)
        if (portfolioPE) {
            // Lower P/E = Value tilt, Higher P/E = Growth tilt
            // Typical market P/E is around 10-15 for Brazilian stocks
            const marketPE = 12; // Approximate market average
            const interpretation = portfolioPE < marketPE ?
                'Value tilt (lower P/E than market)' :
                portfolioPE > marketPE ?
                'Growth tilt (higher P/E than market)' :
                'Neutral';
            rows.push({
                factor: 'Value vs Growth',
                portfolio: `Forward P/E: ${formatNumber(portfolioPE, 2)}`,
                benchmark: `Market avg: ~${marketPE}`,
                tilt: formatNumber(portfolioPE - marketPE, 2),
                interpretation: interpretation
            });
        } else {
            rows.push({
                factor: 'Value vs Growth',
                portfolio: 'N/A',
                benchmark: 'Forward P/E not available',
                tilt: 'N/A',
                interpretation: 'Unable to calculate'
            });
        }

        // Render table
        tbody.innerHTML = rows.map(row => `
            <tr>
                <td>${row.factor}</td>
                <td style="text-align: right;">${row.portfolio}</td>
                <td style="text-align: right;">${row.benchmark}</td>
                <td style="text-align: right;">${row.tilt}</td>
                <td>${row.interpretation}</td>
            </tr>
        `).join('');

    } catch (error) {
        console.error('Error rendering factor tilts:', error);
        tbody.innerHTML = '<tr><td colspan="5" class="status-error-row">Error calculating factor tilts.</td></tr>';
    }
}

async function loadBenchmarkComparison(analysisData) {
    // Try to load SMAL11.SA and IDIV.SA data from the analysis timeseries
    // Since these are factor benchmarks, they might be in the benchmark columns
    // We'll check if they're available in the stock data

    const result = {smal11: null, idiv: null};

    try {
        // Load the full stock database to check if we have SMAL11.SA and IDIV.SA
        const stockDb = await fetchAndParseCsv('../data/findb/StockDataDB.csv?t=' + new Date().getTime());

        const smal11Data = stockDb.filter(r => r.Stock === 'SMAL11.SA');
        const idivData = stockDb.filter(r => r.Stock === 'IDIV.SA');

        // Filter to last 12 months and calculate CAGR
        const twelveMonthsAgo = new Date();
        twelveMonthsAgo.setFullYear(twelveMonthsAgo.getFullYear() - 1);

        if (smal11Data.length > 0) {
            const filtered = smal11Data.filter(r => {
                const d = new Date(r.Date);
                return d && d >= twelveMonthsAgo;
            }).sort((a, b) => new Date(a.Date) - new Date(b.Date));

            if (filtered.length > 1) {
                const prices = filtered.map(r => parseFloat(r.Close));
                const returns = [];
                for (let i = 1; i < prices.length; i++) {
                    returns.push((prices[i] - prices[i-1]) / prices[i-1]);
                }
                const prod = returns.reduce((acc, r) => acc * (1 + r), 1);
                const cagr = (Math.pow(prod, 252 / returns.length) - 1) * 100;
                result.smal11 = {cagr: cagr};
            }
        }

        if (idivData.length > 0) {
            const filtered = idivData.filter(r => {
                const d = new Date(r.Date);
                return d && d >= twelveMonthsAgo;
            }).sort((a, b) => new Date(a.Date) - new Date(b.Date));

            if (filtered.length > 1) {
                const prices = filtered.map(r => parseFloat(r.Close));
                const returns = [];
                for (let i = 1; i < prices.length; i++) {
                    returns.push((prices[i] - prices[i-1]) / prices[i-1]);
                }
                const prod = returns.reduce((acc, r) => acc * (1 + r), 1);
                const cagr = (Math.pow(prod, 252 / returns.length) - 1) * 100;
                result.idiv = {cagr: cagr};
            }
        }
    } catch (error) {
        console.warn('Could not load benchmark comparison data:', error);
    }

    return result;
}

// --- MOMENTUM & VALUATION METRICS SECTION ---
async function loadMomentumValuationMetrics() {
    try {
        const latestRunJson = await fetch(LATEST_RUN_SUMMARY_JSON_PATH + '?t=' + new Date().getTime()).then(res => res.json());
        const momentumValuation = latestRunJson.best_portfolio_details.momentum_valuation;

        if (!momentumValuation) {
            throw new Error('Momentum & valuation data not available');
        }

        // Render table and chart
        renderMomentumValuationTable(momentumValuation);
        renderMomentumValuationChart(momentumValuation);
    } catch (error) {
        console.error('Error loading Momentum & Valuation Metrics:', error);
        document.getElementById('momentumValuationTable').getElementsByTagName('tbody')[0].innerHTML =
            '<tr><td colspan="4" style="text-align: center; color: #999;">Data not available</td></tr>';
        document.getElementById('momentumValuationChart').innerHTML =
            '<div style="display: flex; align-items: center; justify-content: center; height: 100%; color: #999;">' +
            'Data not available</div>';
    }
}

function renderMomentumValuationTable(data) {
    const tbody = document.getElementById('momentumValuationTable').getElementsByTagName('tbody')[0];

    // Prepare rows
    const rows = [];

    // Momentum Signal
    if (data.portfolio_momentum !== null && data.portfolio_momentum !== undefined) {
        rows.push({
            metric: 'Momentum Signal',
            portfolio: formatNumber(data.portfolio_momentum, 4),
            benchmark: 'N/A',
            difference: 'N/A',
            interpretation: data.portfolio_momentum > 0 ? 'Positive momentum' : 'Negative momentum'
        });
    }

    // Forward P/E
    if (data.portfolio_forward_pe !== null && data.benchmark_forward_pe !== null) {
        const diff = data.portfolio_forward_pe - data.benchmark_forward_pe;
        const diffPct = (diff / data.benchmark_forward_pe) * 100;
        rows.push({
            metric: 'Forward P/E',
            portfolio: formatNumber(data.portfolio_forward_pe, 2),
            benchmark: formatNumber(data.benchmark_forward_pe, 2),
            difference: formatNumber(diff, 2),
            interpretation: diff < 0 ?
                `${Math.abs(diffPct).toFixed(1)}% cheaper (value tilt)` :
                `${diffPct.toFixed(1)}% more expensive (growth tilt)`
        });
    } else if (data.portfolio_forward_pe !== null) {
        rows.push({
            metric: 'Forward P/E',
            portfolio: formatNumber(data.portfolio_forward_pe, 2),
            benchmark: 'N/A',
            difference: 'N/A',
            interpretation: 'Benchmark data unavailable'
        });
    }

    // Dividend Yield
    if (data.portfolio_dividend_yield !== null && data.portfolio_dividend_yield !== undefined) {
        rows.push({
            metric: 'Dividend Yield (%)',
            portfolio: formatNumber(data.portfolio_dividend_yield, 2) + '%',
            benchmark: 'N/A',
            difference: 'N/A',
            interpretation: data.portfolio_dividend_yield > 4 ?
                'High dividend yield (income-focused)' :
                data.portfolio_dividend_yield > 2 ?
                'Moderate dividend yield' :
                'Low dividend yield (growth-focused)'
        });
    }

    // Render rows
    tbody.innerHTML = rows.map(row => {
        const diffColor = row.difference !== 'N/A' && parseFloat(row.difference) !== 0 ?
            (parseFloat(row.difference) > 0 ? 'color: #d62728;' : 'color: #2ca02c;') : '';
        return `
            <tr>
                <td>${row.metric}</td>
                <td style="text-align: right;">${row.portfolio}</td>
                <td style="text-align: right;">${row.benchmark}</td>
                <td style="text-align: right; ${diffColor}">${row.difference}</td>
            </tr>
        `;
    }).join('');
}

function renderMomentumValuationChart(data) {
    // Create a grouped bar chart comparing portfolio metrics
    const metrics = [];
    const portfolioValues = [];
    const benchmarkValues = [];

    // Momentum (normalize to 0-100 scale for visualization)
    if (data.portfolio_momentum !== null) {
        metrics.push('Momentum<br>Signal');
        portfolioValues.push(data.portfolio_momentum * 100); // Scale for visualization
        benchmarkValues.push(null); // No benchmark
    }

    // Forward P/E
    if (data.portfolio_forward_pe !== null) {
        metrics.push('Forward<br>P/E');
        portfolioValues.push(data.portfolio_forward_pe);
        benchmarkValues.push(data.benchmark_forward_pe || null);
    }

    // Dividend Yield
    if (data.portfolio_dividend_yield !== null) {
        metrics.push('Dividend<br>Yield (%)');
        portfolioValues.push(data.portfolio_dividend_yield);
        benchmarkValues.push(null); // No benchmark
    }

    const traces = [
        {
            name: 'Portfolio',
            type: 'bar',
            x: metrics,
            y: portfolioValues,
            marker: {color: '#1f77b4'},
            text: portfolioValues.map((v, i) => {
                if (metrics[i].includes('Momentum')) return (v / 100).toFixed(4);
                return v !== null ? v.toFixed(2) : 'N/A';
            }),
            textposition: 'outside'
        }
    ];

    // Add benchmark trace if we have benchmark data
    if (benchmarkValues.some(v => v !== null)) {
        traces.push({
            name: 'Benchmark',
            type: 'bar',
            x: metrics,
            y: benchmarkValues,
            marker: {color: '#ff7f0e'},
            text: benchmarkValues.map(v => v !== null ? v.toFixed(2) : ''),
            textposition: 'outside'
        });
    }

    const layout = {
        title: {
            text: 'Momentum & Valuation Comparison',
            font: {size: 18}
        },
        xaxis: {
            title: 'Metric'
        },
        yaxis: {
            title: 'Value'
        },
        barmode: 'group',
        height: 350,
        margin: {b: 80, t: 60, l: 60, r: 40},
        showlegend: benchmarkValues.some(v => v !== null),
        legend: {
            orientation: 'h',
            y: 1.1,
            x: 0.5,
            xanchor: 'center'
        },
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(0,0,0,0)',
        font: { color: '#333' }
    };

    Plotly.newPlot('momentumValuationChart', traces, layout, {responsive: true});
}

// --- PERFORMANCE ATTRIBUTION SECTION ---
async function loadPerformanceAttribution() {
    try {
        const response = await fetch(ATTRIBUTION_JSON_PATH + '?t=' + new Date().getTime());
        if (!response.ok) {
            throw new Error('Attribution data not available');
        }
        const attributionData = await response.json();

        // Render Attribution Chart
        renderAttributionChart(attributionData);

        // Render Attribution Table
        renderAttributionTable(attributionData);
    } catch (error) {
        console.error('Error loading Performance Attribution:', error);
        document.getElementById('attributionChart').innerHTML =
            '<div style="display: flex; align-items: center; justify-content: center; height: 100%; color: #999;">' +
            'Attribution data not available. Run the pipeline to generate attribution analysis.</div>';
        document.getElementById('attributionTable').getElementsByTagName('tbody')[0].innerHTML =
            '<tr><td colspan="3" style="text-align: center; color: #999;">Data not available</td></tr>';
    }
}

function renderAttributionChart(data) {
    const effects = [
        {name: 'Stock Selection', value: data.selection_effect, color: '#2ca02c'},
        {name: 'Allocation', value: data.allocation_effect, color: '#ff7f0e'},
        {name: 'Interaction', value: data.interaction_effect, color: '#d62728'}
    ];

    const chartData = [{
        type: 'bar',
        x: effects.map(e => e.name),
        y: effects.map(e => e.value),
        marker: {
            color: effects.map(e => e.color),
            line: {color: '#333', width: 1}
        },
        text: effects.map(e => e.value.toFixed(2) + '%'),
        textposition: 'outside',
        hovertemplate: '%{x}<br>%{y:.2f}%<extra></extra>'
    }];

    // Add reference line at y=0
    const shapes = [{
        type: 'line',
        x0: -0.5,
        x1: 2.5,
        y0: 0,
        y1: 0,
        line: {
            color: '#333',
            width: 2,
            dash: 'dash'
        }
    }];

    const layout = {
        title: {
            text: 'Attribution Effects Breakdown',
            font: {size: 18}
        },
        xaxis: {
            title: 'Attribution Component'
        },
        yaxis: {
            title: 'Contribution to Active Return (%)',
            zeroline: true,
            zerolinewidth: 2,
            zerolinecolor: '#999'
        },
        height: 300,
        margin: {b: 80, t: 60, l: 60, r: 40},
        shapes: shapes,
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(0,0,0,0)',
        font: { color: '#333' }
    };

    Plotly.newPlot('attributionChart', chartData, layout, {responsive: true});
}

function renderAttributionTable(data) {
    const tbody = document.getElementById('attributionTable').getElementsByTagName('tbody')[0];

    // Interpret each effect
    function interpretEffect(name, value) {
        if (Math.abs(value) < 0.1) return 'Neutral impact';
        const direction = value > 0 ? 'positive' : 'negative';
        const magnitude = Math.abs(value) < 1 ? 'Small' : Math.abs(value) < 3 ? 'Moderate' : 'Large';

        if (name === 'Stock Selection') {
            return value > 0 ?
                `${magnitude} ${direction} - your stock picks outperformed their sectors` :
                `${magnitude} ${direction} - your stock picks underperformed their sectors`;
        } else if (name === 'Allocation') {
            return value > 0 ?
                `${magnitude} ${direction} - you overweighted outperforming sectors` :
                `${magnitude} ${direction} - you overweighted underperforming sectors`;
        } else if (name === 'Interaction') {
            return value > 0 ?
                `${magnitude} ${direction} - combined allocation & selection worked well together` :
                `${magnitude} ${direction} - allocation & selection effects offset each other`;
        } else {
            return value > 0 ?
                `Portfolio outperformed benchmark` :
                `Portfolio underperformed benchmark`;
        }
    }

    const rows = [
        {name: 'Stock Selection Effect', value: data.selection_effect},
        {name: 'Allocation Effect', value: data.allocation_effect},
        {name: 'Interaction Effect', value: data.interaction_effect},
        {name: 'Total Active Return', value: data.total_active_return, isTotal: true}
    ];

    tbody.innerHTML = rows.map(row => {
        const valueColor = row.value > 0 ? 'green' : row.value < 0 ? 'red' : '#333';
        const style = row.isTotal ? 'border-top: 2px solid #333; font-weight: bold;' : '';
        return `
            <tr style="${style}">
                <td>${row.name}</td>
                <td style="text-align: right; color: ${valueColor}; font-weight: ${row.value !== 0 ? 'bold' : 'normal'};">
                    ${formatNumber(row.value, 2)}%
                </td>
                <td>${interpretEffect(row.name, row.value)}</td>
            </tr>
        `;
    }).join('');
}

async function loadPortfolioDiagnostics() {
  try {
    const response = await fetch('data/portfolio_diagnostics.json');
    const data = await response.json();

    const mom = data.momentum_and_valuation;
    const diag = data.practical_diagnostics;

    document.getElementById("momentum-signal").textContent = (mom.momentum_signal_strength * 100).toFixed(2) + "%";
    document.getElementById("pe-upside").textContent = (mom.forward_pe_implied_upside * 100).toFixed(1) + "%";
    document.getElementById("div-yield").textContent = (mom.weighted_dividend_yield * 100).toFixed(2) + "%";

    document.getElementById("turnover").textContent = (diag.turnover * 100).toFixed(1) + "%";
    document.getElementById("liquidity").textContent = diag.liquidity_score.toFixed(2);
    document.getElementById("tracking-error").textContent = (diag.tracking_error * 100).toFixed(2) + "%";
    document.getElementById("info-ratio").textContent = diag.information_ratio.toFixed(2);
  } catch (error) {
    console.error("Failed to load portfolio diagnostics:", error);
  }
}

document.addEventListener("DOMContentLoaded", loadPortfolioDiagnostics);

// --- Render metrics table with info icon and tooltip ---
// Only render into legacy `bestPortfolioTable` if it exists (page may have removed it)
(function renderLegacyMetricsTooltips(){
    const bestTable = document.getElementById('bestPortfolioTable');
    if (!bestTable) return; // nothing to do
    const tableBody = bestTable.getElementsByTagName('tbody')[0];
    if (!tableBody) return;

    metrics.forEach(m => {
        let info = '';
        if (metricExplanations[m.name]) {
            const e = metricExplanations[m.name];
            info = `<span class="info-wrapper"><span class="info-icon" tabindex="0">&#9432;</span><span class="info-text"><b>Definição:</b> ${e.def}<br><b>Fórmula:</b> ${e.formula}<br><b>Uso:</b> ${e.use}<br><b>Interpretação:</b> ${e.interp}</span></span>`;
        }
        tableBody.innerHTML += `<tr><td>${m.name}${info}</td><td>${m.portfolio}</td><td>${m.bench1}</td><td>${m.bench2}</td></tr>`;
    });
})();
