/**
 * Fetches and displays backtesting results including an equity curve chart,
 * KPI table, and historical backtest results.
 */

// --- CONFIGURATION ---
const EQUITY_CURVE_PATH = 'data/backtesting_equity_curve.csv';
const RESULTS_HISTORY_PATH = 'data/backtesting_results.csv';

// --- MAIN EXECUTION ---
document.addEventListener('DOMContentLoaded', main);

async function main() {
    try {
        // Fetch all necessary data in parallel for efficiency
        const [equityData, resultsData] = await Promise.all([
            fetchAndParseCsv(EQUITY_CURVE_PATH),
            fetchAndParseCsv(RESULTS_HISTORY_PATH)
        ]);

        // Render components if data is available
        if (equityData && equityData.length > 0 && resultsData && resultsData.length > 0) {
            const latestResult = resultsData[resultsData.length - 1];
            renderEquityCurveChart(equityData, latestResult);
            renderKpiTable(equityData, latestResult);
            renderBacktestHistoryScatterChart(resultsData);
        } else {
            document.getElementById('equityCurveChart').innerHTML = '<p>No equity curve or results data available for the last run.</p>';
            document.getElementById('kpiTableContainer').innerHTML = '<p>No KPI data available for the last run.</p>';
            document.getElementById('backtestHistoryScatterChart').innerHTML = '<p>No historical backtesting results found.</p>';
        }

    } catch (error) {
        console.error("Error loading backtesting data:", error);
        // Display user-friendly error messages on the page
        document.getElementById('equityCurveChart').innerHTML = `<p class="error">Failed to load chart data: ${error.message}</p>`;
        document.getElementById('kpiTableContainer').innerHTML = `<p class="error">Failed to load KPI data: ${error.message}</p>`;
        document.getElementById('backtestHistoryScatterChart').innerHTML = `<p class="error">Failed to load historical data: ${error.message}</p>`;
    }
}

/**
 * Renders the equity curve chart comparing the portfolio to the benchmark.
 * @param {Array<Object>} equityData The equity curve data.
 * @param {Object} latestResult The latest result row from the history file.
 */
function renderEquityCurveChart(equityData, latestResult) {
    const chartDiv = document.getElementById('equityCurveChart');
    chartDiv.innerHTML = ''; // FIX: Explicitly clear the placeholder text

    const benchmarkTicker = latestResult.benchmark || 'Benchmark';
    document.getElementById('equityCurveChartTitle').textContent = `Performance vs. ${benchmarkTicker}`;

    const dates = equityData.map(row => row.Date);
    const portfolioValues = equityData.map(row => parseFloat(row.Portfolio));
    const benchmarkValues = equityData.map(row => parseFloat(row.Benchmark));

    const portfolioTrace = {
        x: dates,
        y: portfolioValues,
        mode: 'lines',
        name: 'Optimized Portfolio',
        line: { color: '#1f77b4', width: 2.5 }
    };

    const benchmarkTrace = {
        x: dates,
        y: benchmarkValues,
        mode: 'lines',
        name: benchmarkTicker,
        line: { color: '#ff7f0e', dash: 'dash', width: 2.5 }
    };

    const layout = {
        height: 500, // Increased height to make it less squeezed
        xaxis: {
            title: 'Date',
            type: 'date',
            gridcolor: '#e1e1e1'
        },
        yaxis: {
            title: 'Portfolio Value ($)',
            tickprefix: '$',
            gridcolor: '#e1e1e1'
        },
        legend: {
            x: 0.01,
            y: 0.99,
            bgcolor: 'rgba(255, 255, 255, 0.7)',
            bordercolor: '#000',
            borderwidth: 1
        },
        margin: { l: 70, r: 40, t: 50, b: 60 }, // Adjusted margins for more space
        paper_bgcolor: '#ffffff',
        plot_bgcolor: '#ffffff'
    };

    Plotly.newPlot(chartDiv, [portfolioTrace, benchmarkTrace], layout, { responsive: true });
}

/**
 * Renders the table of Key Performance Indicators for the latest run.
 * @param {Array<Object>} equityData The equity curve data to find the date range.
 * @param {Object} latestResult The latest result row from the history file.
 */
function renderKpiTable(equityData, latestResult) {
    const benchmarkTicker = latestResult.benchmark || 'Benchmark';
    document.getElementById('kpiSectionTitle').textContent = `Key Performance Indicators (KPIs) vs. ${benchmarkTicker}`;
    const tableBody = document.querySelector("#kpiTable tbody");

    const startDate = equityData[0]?.Date;
    const endDate = equityData[equityData.length - 1]?.Date;

    const kpis = [
        { label: 'Total Return (%)', portfolioKey: 'portfolio_total_return_pct', benchmarkKey: 'benchmark_total_return_pct' },
        { label: 'CAGR (%)', portfolioKey: 'portfolio_cagr_pct', benchmarkKey: 'benchmark_cagr_pct' },
        { label: 'Annualized Volatility (%)', portfolioKey: 'portfolio_volatility_pct', benchmarkKey: 'benchmark_volatility_pct' },
        { label: 'Historical Sharpe Ratio', portfolioKey: 'portfolio_sharpe_ratio', benchmarkKey: 'benchmark_sharpe_ratio' },
        { label: 'Max Drawdown (%)', portfolioKey: 'portfolio_max_drawdown_pct', benchmarkKey: 'benchmark_max_drawdown_pct' }
    ];

    let tableHtml = '';
    kpis.forEach(kpi => {
        const portfolioValue = parseFloat(latestResult[kpi.portfolioKey]).toFixed(2);
        const benchmarkValue = parseFloat(latestResult[kpi.benchmarkKey]).toFixed(2);
        tableHtml += `
            <tr>
                <td>${kpi.label}</td>
                <td>${portfolioValue}</td>
                <td>${benchmarkValue}</td>
            </tr>
        `;
    });

    // Add the backtest period row
    if (startDate && endDate) {
        tableHtml += `
            <tr class="kpi-period-row">
                <td><strong>Backtest Period</strong></td>
                <td colspan="2">${formatDate(startDate)} to ${formatDate(endDate)}</td>
            </tr>
        `;
    }

    tableBody.innerHTML = tableHtml;
}

/**
 * Renders a scatter plot of historical backtesting runs.
 * @param {Array<Object>} resultsData The backtesting results data.
 */
function renderBacktestHistoryScatterChart(resultsData) {
    const chartDiv = document.getElementById('backtestHistoryScatterChart');
    chartDiv.innerHTML = ''; // FIX: Explicitly clear the placeholder text

    const timestamps = resultsData.map(row => new Date(row.timestamp));
    const cagr = resultsData.map(row => parseFloat(row.portfolio_cagr_pct));
    const sharpe = resultsData.map(row => parseFloat(row.portfolio_sharpe_ratio));
    const hoverText = resultsData.map(row => 
        `<b>Run:</b> ${row.run_id}<br>` +
        `<b>Date:</b> ${formatDate(row.timestamp)}<br>` +
        `<b>CAGR:</b> ${parseFloat(row.portfolio_cagr_pct).toFixed(2)}%<br>` +
        `<b>Sharpe:</b> ${parseFloat(row.portfolio_sharpe_ratio).toFixed(3)}`
    );

    const trace = {
        x: timestamps,
        y: cagr,
        mode: 'markers',
        type: 'scatter',
        text: hoverText,
        hoverinfo: 'text',
        marker: {
            size: 10,
            color: sharpe,
            colorscale: 'Viridis',
            showscale: true,
            colorbar: {
                title: 'Sharpe Ratio'
            }
        }
    };

    const layout = {
        height: 500,
        title: 'Historical Backtest Performance',
        xaxis: { title: 'Run Date', type: 'date', gridcolor: '#e1e1e1' },
        yaxis: { title: 'Portfolio CAGR (%)', ticksuffix: '%', gridcolor: '#e1e1e1' },
        margin: { l: 70, r: 40, t: 50, b: 60 },
        paper_bgcolor: '#ffffff',
        plot_bgcolor: '#ffffff'
    };

    Plotly.newPlot(chartDiv, [trace], layout, { responsive: true });
}
