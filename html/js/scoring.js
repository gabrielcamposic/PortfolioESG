/**
 * Fetches, parses, and displays data for the scoring.html page.
 * This refactored version improves robustness, readability, and maintainability.
 */

// --- Data Handling Functions ---
async function fetchAndParseCsvData() {
    const response = await fetch(`data/scored_stocks.csv?t=${new Date().getTime()}`);
    if (!response.ok) {
        throw new Error(`Failed to load scored_stocks.csv. Status: ${response.status}`);
    }
    const csvData = await response.text();
    const lines = csvData.trim().split('\n');
    if (lines.length < 2) return [];
    const header = lines[0].split(',').map(h => h.trim());
    const csvRowRegex = /,(?=(?:(?:[^"]*"){2})*[^"]*$)/;
    return lines.slice(1).map(line => {
        const values = line.split(csvRowRegex);
        const obj = {};
        header.forEach((key, i) => {
            let value = values[i] ? values[i].trim() : '';
            if (value.startsWith('"') && value.endsWith('"')) {
                value = value.substring(1, value.length - 1);
            }
            obj[key] = value;
        });
        return obj;
    });
}

function getLatestRunData(allData) {
    if (!allData || allData.length === 0) return [];
    const latestRunId = allData.reduce((maxId, row) => {
        if (row && row.run_id) {
            return row.run_id > maxId ? row.run_id : maxId;
        }
        return maxId;
    }, "");
    if (!latestRunId) {
        throw new Error("Could not determine the latest run_id from the data.");
    }
    return allData.filter(row => row.run_id === latestRunId);
}

async function fetchAndParseSectorPEData() {
    const response = await fetch(`data/sector_pe.csv?t=${new Date().getTime()}`);
    if (!response.ok) {
        throw new Error(`Failed to load sector_pe.csv. Status: ${response.status}`);
    }
    const csvData = await response.text();
    const lines = csvData.trim().split('\n');
    if (lines.length < 2) return [];
    const header = lines[0].split(',').map(h => h.trim());
    // A simple split is sufficient here as there are no quoted fields with commas.
    return lines.slice(1).map(line => {
        const values = line.split(',');
        const obj = {};
        header.forEach((key, i) => {
            obj[key] = values[i] ? values[i].trim() : '';
        });
        return obj;
    });
}

// --- DOM Update Functions ---
function updateSummary(summaryData) {
    setText('summary-datetime', formatDate(summaryData.run_timestamp));
    setText('summary-version', summaryData.scoring_version);
}

function populateTopStocksTable(top20Stocks, tableBody) {
    if (top20Stocks.length === 0) {
        tableBody.innerHTML = '<tr><td colspan="11">No data available for the latest run.</td></tr>';
        return;
    }
    const rowsHtml = top20Stocks.map(stock => `
        <tr>
            <td>${stock.Stock || 'N/A'}</td>
            <td>${stock.Name || 'N/A'}</td>
            <td>${stock.Sector || 'N/A'}</td>
            <td>${stock.Industry || 'N/A'}</td>
            <td>${formatNumber(stock.CompositeScore, 4)}</td>
            <td>${formatNumber(stock.SharpeRatio, 4)}</td>
            <td>${formatNumber(stock.PotentialUpside_pct * 100, 2)}%</td>
            <td>${formatNumber(stock.Momentum, 4)}</td>
            <td>$${formatNumber(stock.CurrentPrice, 2)}</td>
            <td>$${formatNumber(stock.TargetPrice, 2)}</td>
            <td>${formatNumber(stock.forwardPE, 2)}</td>
            <td>${formatNumber(stock.SectorMedianPE, 2)}</td>
        </tr>
    `).join('');
    tableBody.innerHTML = rowsHtml;
}

// --- Charting Functions ---

/**
 * Creates a historical stacked bar chart of sector allocation over the last 6 months.
 * @param {Array<Object>} allData The entire historical dataset from scored_stocks.csv.
 * @param {string} elementId The ID of the div where the chart will be rendered.
 */
async function createHistoricalSectorChart(allData, elementId) {
    const chartDiv = document.getElementById(elementId);
    if (!chartDiv) {
        console.error(`Chart container with ID '${elementId}' not found.`);
        return;
    }
    chartDiv.innerHTML = ''; // Clear the "Loading..." placeholder

    if (typeof Plotly === 'undefined') {
        chartDiv.textContent = 'Plotly.js library not found.';
        return;
    }

    // 1. Filter data to the last 6 months
    const sixMonthsAgo = new Date();
    sixMonthsAgo.setMonth(sixMonthsAgo.getMonth() - 6);
    const recentData = allData.filter(row => new Date(row.run_timestamp) >= sixMonthsAgo);

    if (recentData.length === 0) {
        chartDiv.textContent = 'No scoring data available for the last 6 months.';
        return;
    }

    // 2. Group data by run
    const runs = recentData.reduce((acc, row) => {
        acc[row.run_id] = acc[row.run_id] || [];
        acc[row.run_id].push(row);
        return acc;
    }, {});

    // 3. Process each run to get sector percentages
    const allSectors = [...new Set(recentData.map(row => row.Sector || 'Unknown'))].sort();
    const sortedRunIds = Object.keys(runs).sort();
    const runDates = sortedRunIds.map(runId => new Date(runs[runId][0].run_timestamp));

    const sectorPercentages = allSectors.reduce((acc, sector) => {
        acc[sector] = [];
        return acc;
    }, {});

    sortedRunIds.forEach(runId => {
        const runData = runs[runId];
        const top20 = runData.sort((a, b) => parseFloat(b.CompositeScore) - parseFloat(a.CompositeScore)).slice(0, 20);
        const sectorCounts = top20.reduce((acc, stock) => {
            const sector = stock.Sector || 'Unknown';
            acc[sector] = (acc[sector] || 0) + 1;
            return acc;
        }, {});

        allSectors.forEach(sector => {
            const percentage = ((sectorCounts[sector] || 0) / top20.length) * 100;
            sectorPercentages[sector].push(percentage);
        });
    });

    // 4. Create Plotly traces for the stacked bar chart
    const traces = allSectors.map(sector => ({
        x: runDates,
        y: sectorPercentages[sector],
        name: sector,
        type: 'bar'
    }));

    // 5. Define the layout and render the chart
    const layout = {
        title: 'Sector Breakdown for Top 20 Stocks (Last 6 Months)',
        barmode: 'stack', // This is the key to creating a stacked chart
        height: 400,
        margin: { t: 50, b: 100, l: 60, r: 50 },
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(0,0,0,0)',
        font: { color: '#333' },
        xaxis: {
            title: 'Run Date',
            type: 'date',
            tickformat: '%Y-%m-%d'
        },
        yaxis: {
            title: 'Sector Allocation (%)',
            ticksuffix: '%'
        },
        legend: {
            orientation: 'h',
            yanchor: 'bottom',
            y: -0.5,
            xanchor: 'center',
            x: 0.5
        }
    };

    Plotly.newPlot(chartDiv, traces, layout, { responsive: true });
}

async function createCorrelationHeatmap(elementId) {
    const chartDiv = document.getElementById(elementId);
    if (!chartDiv) {
        console.error(`Chart container with ID '${elementId}' not found.`);
        return;
    }
    chartDiv.innerHTML = ''; // Clear the "Loading..." text

    if (typeof Plotly === 'undefined') {
        chartDiv.textContent = 'Plotly.js library not found.';
        return;
    }
    try {
        // Fetch the correlation matrix generated by Scoring.py
        const response = await fetch(`data/correlation_matrix.csv?t=${new Date().getTime()}`);
        if (!response.ok) {
            throw new Error(`Status: ${response.status}`);
        }
        const csvData = await response.text();
        const lines = csvData.trim().split('\n');
        if (lines.length < 2) {
            throw new Error('Correlation data is empty or invalid.');
        }

        // Parse the CSV data for the heatmap
        const headers = lines[0].split(',').slice(1).map(h => h.trim());
        const zValues = lines.slice(1).map(line =>
            line.split(',').slice(1).map(val => parseFloat(val))
        );

        const data = [{
            z: zValues,
            x: headers,
            y: headers,
            type: 'heatmap',
            colorscale: 'Viridis', // A color scale that works well for correlations
            showscale: true
        }];

        const layout = {
            // This title correctly describes the stock-vs-stock correlation
            title: 'Top 20 Stock Correlation (Daily Returns)',
            height: 400,
            margin: { t: 50, b: 50, l: 100, r: 50 },
            paper_bgcolor: 'rgba(0,0,0,0)',
            plot_bgcolor: 'rgba(0,0,0,0)',
            font: { color: '#333' },
            xaxis: { ticks: '', side: 'top' },
            yaxis: { ticks: '' }
        };

        Plotly.newPlot(chartDiv, data, layout, {responsive: true});
    } catch (error) {
        console.error(`Failed to load or create correlation heatmap:`, error);
        chartDiv.textContent = `Could not load correlation data. ${error.message}`;
    }
}

// NEW: Historical Trends Chart
async function createHistoricalTrendsChart(allData, topStocks, elementId) {
    const chartDiv = document.getElementById(elementId);
    if (!chartDiv) {
        console.error(`Chart container with ID '${elementId}' not found.`);
        return;
    }
    chartDiv.innerHTML = ''; // Clear placeholder

    if (typeof Plotly === 'undefined') {
        chartDiv.textContent = 'Plotly.js library not found.';
        return;
    }

    // --- MODIFICATION: Filter data to the last 6 months for consistency ---
    const sixMonthsAgo = new Date();
    sixMonthsAgo.setMonth(sixMonthsAgo.getMonth() - 6);
    const recentData = allData.filter(row => new Date(row.run_timestamp) >= sixMonthsAgo);

    if (recentData.length === 0) {
        chartDiv.textContent = 'No scoring data available for the last 6 months.';
        return;
    }

    const topStockNames = topStocks.map(stock => stock.Stock);

    // Group recent historical data by stock name for efficient lookup
    const recentDataByStock = recentData.reduce((acc, row) => {
        const stock = row.Stock;
        if (!acc[stock]) {
            acc[stock] = [];
        }
        acc[stock].push(row);
        return acc;
    }, {});

    const traces = topStockNames.map(stockName => {
        // Get all historical points for this specific stock and sort them by date
        const stockHistory = (recentDataByStock[stockName] || [])
            .sort((a, b) => new Date(a.run_timestamp) - new Date(b.run_timestamp));

        return {
            x: stockHistory.map(row => new Date(row.run_timestamp)), // Use Date objects for a proper time-series axis
            y: stockHistory.map(row => parseFloat(row.CompositeScore)),
            mode: 'lines+markers',
            name: stockName,
            type: 'scatter'
        };
    });

    const layout = {
        // --- MODIFICATION: Update title to reflect the 6-month timeframe ---
        title: `Historical Composite Score for Top ${topStocks.length} Stocks (Last 6 Months)`,
        height: 400,
        margin: { t: 50, b: 100, l: 60, r: 50 },
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(0,0,0,0)',
        font: { color: '#333' },
        xaxis: {
            title: 'Run Date',
            type: 'date',
            tickformat: '%Y-%m-%d' // Format date ticks for readability
        },
        yaxis: {
            title: 'Composite Score',
            rangemode: 'tozero' // Ensure y-axis starts at 0 for better perspective
        },
        showlegend: true,
        legend: {
            orientation: 'h',
            yanchor: 'bottom',
            y: -0.5, // Position legend below the x-axis title
            xanchor: 'center',
            x: 0.5
        }
    };

    Plotly.newPlot(chartDiv, traces, layout, {responsive: true});
}

function updatePlaceholders() {
    // All charts are now implemented, so this function is empty.
    // We can leave it for future placeholders if needed.
}

async function createHistoricalSectorPEChart(elementId) {
    const chartDiv = document.getElementById(elementId);
    if (!chartDiv) {
        console.error(`Chart container with ID '${elementId}' not found.`);
        return;
    }
    chartDiv.innerHTML = ''; // Clear placeholder

    if (typeof Plotly === 'undefined') {
        chartDiv.textContent = 'Plotly.js library not found.';
        return;
    }

    try {
        const allSectorPEData = await fetchAndParseSectorPEData();

        // 1. Filter data to the last 6 months
        const sixMonthsAgo = new Date();
        sixMonthsAgo.setMonth(sixMonthsAgo.getMonth() - 6);
        const recentData = allSectorPEData.filter(row => new Date(row.run_timestamp) >= sixMonthsAgo);

        if (recentData.length === 0) {
            chartDiv.textContent = 'No historical sector P/E data available for the last 6 months.';
            return;
        }

        // 2. Group data by Sector for plotting
        const dataBySector = recentData.reduce((acc, row) => {
            const sector = row.Sector || 'Unknown';
            if (!acc[sector]) {
                acc[sector] = [];
            }
            acc[sector].push(row);
            return acc;
        }, {});

        // 3. Create a line trace for each sector
        const traces = Object.keys(dataBySector).map(sector => {
            const sectorHistory = dataBySector[sector].sort((a, b) => new Date(a.run_timestamp) - new Date(b.run_timestamp));
            return {
                x: sectorHistory.map(row => new Date(row.run_timestamp)),
                y: sectorHistory.map(row => parseFloat(row.SectorMedianPE)),
                mode: 'lines+markers',
                name: sector,
                type: 'scatter'
            };
        });

        // 4. Define layout and render the chart
        const layout = {
            title: 'Historical Sector Median P/E (Last 6 Months)',
            height: 400,
            margin: { t: 50, b: 100, l: 60, r: 50 },
            paper_bgcolor: 'rgba(0,0,0,0)',
            plot_bgcolor: 'rgba(0,0,0,0)',
            font: { color: '#333' },
            xaxis: {
                title: 'Run Date',
                type: 'date',
                tickformat: '%Y-%m-%d'
            },
            yaxis: {
                title: 'Median P/E Ratio',
                rangemode: 'tozero'
            },
            showlegend: true,
            legend: {
                orientation: 'h',
                yanchor: 'bottom',
                y: -0.5,
                xanchor: 'center',
                x: 0.5
            }
        };

        Plotly.newPlot(chartDiv, traces, layout, { responsive: true });

    } catch (error) {
        console.error('Failed to load or create historical sector P/E chart:', error);
        chartDiv.textContent = `Could not load sector P/E data. ${error.message}`;
    }
}

// --- Main Execution ---
// --- Main Execution ---
async function displayScoringData() {
    const topStocksTbody = document.getElementById('top-stocks-tbody');
    try {
        const allData = await fetchAndParseCsvData();
        if (allData.length === 0) {
            throw new Error("No scoring data found in the file.");
        }

        const latestRunData = getLatestRunData(allData);
        if (latestRunData.length === 0) {
            throw new Error("No data available for the latest run.");
        }

        const top20Stocks = latestRunData.slice(0, 20);

        // --- 1. Update the Summary Section ---
        updateSummary(latestRunData[0]);

        // --- 2. Populate the Top 20 Stocks Table ---
        populateTopStocksTable(top20Stocks, topStocksTbody);

        // --- 3. Handle Visualizations ---
        await createHistoricalSectorChart(allData, 'sector-breakdown-chart');
        await createCorrelationHeatmap('correlation-matrix');
        await createHistoricalTrendsChart(allData, top20Stocks, 'historical-trends-chart');

        // --- NEW: Call the function for the new chart ---
        await createHistoricalSectorPEChart('historical-sector-pe-chart');

        updatePlaceholders();

    } catch (error) {
        console.error('Error loading or processing scoring data:', error);
        const errorMsg = `Failed to load data. Check console for details. Error: ${error.message}`;
        topStocksTbody.innerHTML = `<tr class="status-error-row"><td colspan="11">${errorMsg}</td></tr>`;
        setText('summary-datetime', 'Error');
        setText('summary-version', 'Error');
    }
}

document.addEventListener('DOMContentLoaded', displayScoringData);