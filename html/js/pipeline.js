/**
 * Manages the Pipeline Status and Performance page.
 * - Fetches and displays live progress from multiple JSON files.
 * - Fetches and displays historical performance data from CSV files.
 * - Creates and updates charts and tables.
 */

// --- Configuration ---
const POLLING_INTERVAL_MS = 5000; // 5 seconds
const PROGRESS_FILES = {
    download: 'download_progress.json',
    scoring: 'scoring_progress.json',
    portfolio: 'portfolio_progress.json',
    backtesting: 'backtesting_progress.json'
};
const PERFORMANCE_FILES = {
    download: 'data/download_performance.csv',
    scoring: 'data/scoring_performance.csv',
    portfolio: 'data/portfolio_performance.csv',
    backtesting: 'data/backtesting_performance.csv',
    ga_fitness: 'data/ga_fitness_noise_db.csv'
};

// --- Main Execution Logic ---

document.addEventListener('DOMContentLoaded', () => {
    fetchAndUpdateAll();
    setInterval(fetchAndUpdateAll, POLLING_INTERVAL_MS);
    displayHistoricalPerformance();
    setupAccordion();
});

/**
 * Orchestrates fetching and updating all data sources.
 */
async function fetchAndUpdateAll() {
    try {
        const [downloadData, scoringData, portfolioData, backtestingData] = await Promise.all([
            fetchProgress(PROGRESS_FILES.download),
            fetchProgress(PROGRESS_FILES.scoring),
            fetchProgress(PROGRESS_FILES.portfolio),
            fetchProgress(PROGRESS_FILES.backtesting)
        ]);

        updateDownloadStatus(downloadData);
        updateScoringStatus(scoringData);
        updatePortfolioStatus(portfolioData);
        updateBacktestingStatus(backtestingData);

    } catch (error) {
        console.error("Error during periodic update:", error);
    }
}

/**
 * Fetches and parses a JSON progress file.
 * @param {string} fileName - The name of the JSON file to fetch.
 * @returns {Promise<Object>} A promise that resolves to the parsed JSON data.
 */
async function fetchProgress(fileName) {
    try {
        const response = await fetch(`${fileName}?t=${new Date().getTime()}`);
        if (!response.ok) {
            return {};
        }
        return await response.json();
    } catch (error) {
        console.warn(`Could not fetch or parse ${fileName}:`, error);
        return {}; // Return an empty object on network or parse error
    }
}

// --- UI Update Functions (Live Progress) ---

function updateDownloadStatus(data) {
    const status = data?.download_overall_status || 'Pending';
    const tickerInfo = data?.ticker_download || {};
    const startTime = data?.download_execution_start || 'N/A';
    const endTime = data?.download_execution_end || 'N/A';

    setStageStatus('download-stage-status-pill', status);
    setText('download-overall-status', status);
    setText('download-start-time', formatDate(startTime));
    setText('download-end-time', formatDate(endTime));
    setText('download-duration', calculateDuration(startTime, endTime));
    setText('download-date-range', tickerInfo.date_range || 'N/A');
    setText('download-current-ticker', tickerInfo.current_ticker || 'N/A');
    setText('download-progress-text', `${tickerInfo.completed_tickers || 0} / ${tickerInfo.total_tickers || 0}`);
    setText('download-rows-fetched', formatNumber(tickerInfo.rows, 0) || '0');
    updateProgressBar('download-progress-bar-inner', tickerInfo.progress || (status.toLowerCase() === 'completed' ? 100 : 0));
}

function updateScoringStatus(data) {
    const status = data?.scoring_status || 'Pending';
    const startTime = data?.scoring_start_time || 'N/A';
    const endTime = data?.scoring_end_time || 'N/A';

    setStageStatus('scoring-stage-status-pill', status);
    setText('scoring-overall-status', status);
    setText('scoring-start-time', formatDate(startTime));
    setText('scoring-end-time', formatDate(endTime));
    setText('scoring-duration', calculateDuration(startTime, endTime));
    setText('scoring-stocks-scored', formatNumber(data.stocks_scored_count, 0) || 'N/A');
    updateProgressBar('scoring-progress-bar-inner', status.toLowerCase() === 'completed' ? 100 : 0);
}

function updatePortfolioStatus(data) {
    const status = data?.portfolio_status || 'Pending';
    const progress = data?.progress || {};
    const startTime = data?.start_time || 'N/A';
    const endTime = data?.end_time || 'N/A';

    setStageStatus('portfolio-stage-status-pill', status);
    setText('portfolio-overall-status', status);
    setText('portfolio-start-time', formatDate(startTime));
    setText('portfolio-end-time', formatDate(endTime));
    setText('portfolio-duration', calculateDuration(startTime, endTime));
    setText('portfolio-current-phase', progress.current_phase || 'N/A');
    setText('portfolio-status-message', data.status_message || 'Awaiting previous stages...');
    updateProgressBar('portfolio-progress-bar-inner', progress.overall_progress || (status.toLowerCase() === 'completed' ? 100 : 0));
}

function updateBacktestingStatus(data) {
    const status = data?.backtesting_status || 'Pending';
    const startTime = data?.start_time || 'N/A';
    const endTime = data?.end_time || 'N/A';
    const message = data?.status_message || 'Awaiting previous stages...';
    const progress = data?.progress || 0;

    setStageStatus('backtesting-stage-status-pill', status);
    setText('backtesting-overall-status', status);
    setText('backtesting-start-time', formatDate(startTime));
    setText('backtesting-end-time', formatDate(endTime));
    setText('backtesting-duration', calculateDuration(startTime, endTime));
    setText('backtesting-status-message', message);
    updateProgressBar('backtesting-progress-bar-inner', progress || (status.toLowerCase() === 'completed' ? 100 : 0));
}


// --- Historical Performance and Logging ---

async function displayHistoricalPerformance() {
    try {
        const [downloadPerfData, scoringPerfData, portfolioPerfData, backtestingPerfData, gaFitnessData] = await Promise.all([
            fetchAndParseCsv(PERFORMANCE_FILES.download).catch(e => { console.error(e); return []; }),
            fetchAndParseCsv(PERFORMANCE_FILES.scoring).catch(e => { console.error(e); return []; }),
            fetchAndParseCsv(PERFORMANCE_FILES.portfolio).catch(e => { console.error(e); return []; }),
            fetchAndParseCsv(PERFORMANCE_FILES.backtesting).catch(e => { console.error(e); return []; }),
            fetchAndParseCsv(PERFORMANCE_FILES.ga_fitness).catch(e => { console.error(e); return []; })
        ]);

        createPerformanceChart(downloadPerfData, 'download-perf-chart', 'Download.py Duration', 'overall_script_duration_s', 'run_start_timestamp', 'minutes');
        createPerformanceChart(scoringPerfData, 'scoring-perf-chart', 'Scoring.py Duration', 'overall_script_duration_s', 'run_start_timestamp', 'seconds');
        createPerformanceChart(portfolioPerfData, 'portfolio-perf-chart', 'Portfolio.py Duration', 'overall_script_duration_s', 'run_start_timestamp', 'hours');
        createPerformanceChart(backtestingPerfData, 'backtesting-perf-chart', 'Backtesting.py Duration', 'overall_script_duration_s', 'run_start_timestamp', 'seconds');

        populatePerformanceTable(downloadPerfData, 'downloadPerformanceTable');
        populatePerformanceTable(scoringPerfData, 'scoringPerformanceTable');
        populatePerformanceTable(portfolioPerfData, 'portfolioPerformanceTable');
        populatePerformanceTable(backtestingPerfData, 'backtestingPerformanceTable');

        createGAFitnessChart(gaFitnessData, 'ga-fitness-chart');
        populateGATable(gaFitnessData, 'gaFitnessTable');

    } catch (error) {
        console.error("Error displaying historical performance:", error);
        document.getElementById('download-perf-chart').textContent = 'Error loading data.';
        document.getElementById('scoring-perf-chart').textContent = 'Error loading data.';
        document.getElementById('portfolio-perf-chart').textContent = 'Error loading data.';
        document.getElementById('backtesting-perf-chart').textContent = 'Error loading data.';
        document.getElementById('ga-fitness-chart').textContent = 'Error loading data.';
    }
}

function createPerformanceChart(data, elementId, title, valueKey, timeKey, unit = 'seconds') {
    const chartDiv = document.getElementById(elementId);
    chartDiv.innerHTML = ''; // Clear placeholder text

    if (!data || data.length === 0) {
        chartDiv.textContent = 'No performance data available.';
        return;
    }
    if (typeof Plotly === 'undefined') {
        chartDiv.textContent = 'Plotly.js library not found.';
        return;
    }

    const xValues = data.map(row => new Date(row[timeKey]));
    const rawYValues = data.map(row => parseFloat(row[valueKey]));

    let yAxisTitle;
    let yValues;

    switch (unit) {
        case 'minutes':
            yAxisTitle = 'Duration (minutes)';
            yValues = rawYValues.map(sec => sec / 60);
            break;
        case 'hours':
            yAxisTitle = 'Duration (hours)';
            yValues = rawYValues.map(sec => sec / 3600);
            break;
        case 'seconds':
        default:
            yAxisTitle = 'Duration (seconds)';
            yValues = rawYValues;
            break;
    }

    const trace = {
        x: xValues,
        y: yValues,
        type: 'scatter',
        mode: 'lines+markers',
        marker: { color: '#007bff' }
    };

    const layout = {
        title: { text: title, font: { size: 16 } }, // Use the title parameter
        height: 300,
        margin: { t: 40, b: 50, l: 60, r: 20 }, // Increased left margin for new labels
        xaxis: { title: 'Run Date' },
        yaxis: { title: yAxisTitle }, // Use the dynamic axis title
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(0,0,0,0)',
    };

    Plotly.newPlot(chartDiv, [trace], layout, { responsive: true });
}

function populatePerformanceTable(data, tableId) {
    const table = document.getElementById(tableId);
    if (!data || data.length === 0) {
        table.innerHTML = '<thead><tr><th>No Data</th></tr></thead><tbody><tr><td>No performance data available.</td></tr></tbody>';
        return;
    }
    const headers = Object.keys(data[0]);
    const headerHtml = `<thead><tr>${headers.map(h => `<th>${h}</th>`).join('')}</tr></thead>`;
    const bodyHtml = `<tbody>${data.map(row => `<tr>${headers.map(h => `<td>${row[h]}</td>`).join('')}</tr>`).reverse().join('')}</tbody>`;
    table.innerHTML = headerHtml + bodyHtml;
}

// --- NEW: Functions for GA analysis, adapted for Plotly ---
function createGAFitnessChart(data, elementId) {
    const chartDiv = document.getElementById(elementId);
    if (!chartDiv) return;
    chartDiv.innerHTML = '';

    if (!data || data.length === 0) {
        chartDiv.textContent = 'No GA fitness data available.';
        return;
    }
    if (typeof Plotly === 'undefined') {
        chartDiv.textContent = 'Plotly.js library not found.';
        return;
    }

    const dataByK = data.reduce((acc, row) => {
        const k = row.k_size;
        if (!acc[k]) acc[k] = [];
        acc[k].push(row);
        return acc;
    }, {});

    const traces = Object.keys(dataByK).sort((a, b) => parseInt(a) - parseInt(b)).map(k => {
        const kData = dataByK[k];
        return {
            x: kData.map(row => parseInt(row.sim_runs_used_for_ga)),
            y: kData.map(row => parseFloat(row.best_sharpe_found_for_k)),
            mode: 'markers',
            type: 'scatter',
            name: `k=${k}`
        };
    });

    const layout = {
        title: 'GA Fitness History by Portfolio Size (k)',
        height: 400, margin: { t: 50, b: 80, l: 60, r: 30 },
        xaxis: { title: 'Simulations per Individual' },
        yaxis: { title: 'Best Sharpe Ratio Found' },
        paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)',
    };

    Plotly.newPlot(chartDiv, traces, layout, { responsive: true });
}

function populateGATable(data, tableId) {
    const table = document.getElementById(tableId);
    if (!table) return;
    if (!data || data.length === 0) {
        table.innerHTML = '<thead><tr><th>No Data</th></tr></thead><tbody><tr><td>No GA fitness data available.</td></tr></tbody>';
        return;
    }
    const headers = Object.keys(data[0]);
    const headerHtml = `<thead><tr>${headers.map(h => `<th>${h}</th>`).join('')}</tr></thead>`;
    const bodyHtml = `<tbody>${data.map(row => `<tr>${headers.map(h => `<td>${row[h]}</td>`).join('')}</tr>`).reverse().join('')}</tbody>`;
    table.innerHTML = headerHtml + bodyHtml;
}

// --- Accordion and other helpers ---
function setupAccordion() {
    const button = document.querySelector('.accordion-button');
    if (button) {
        button.addEventListener('click', () => {
            const content = button.nextElementSibling;
            button.classList.toggle('active');
            if (content.style.maxHeight) {
                content.style.maxHeight = null;
            } else {
                content.style.maxHeight = content.scrollHeight + "px";
            }
        });
    }
}

function calculateDuration(startTime, endTime) {
    if (!startTime || !endTime || startTime === 'N/A' || endTime === 'N/A') return 'N/A';
    try {
        const start = new Date(startTime.replace(' ', 'T'));
        const end = new Date(endTime.replace(' ', 'T'));
        if (isNaN(start) || isNaN(end) || end < start) return 'Calculating...';
        let diff = Math.abs(end - start) / 1000;
        const h = String(Math.floor(diff / 3600)).padStart(2, '0');
        diff %= 3600;
        const m = String(Math.floor(diff / 60)).padStart(2, '0');
        const s = String(Math.floor(diff % 60)).padStart(2, '0');
        return `${h}:${m}:${s}`;
    } catch (e) {
        console.warn("Could not calculate duration for", startTime, endTime, e);
        return 'N/A';
    }
}