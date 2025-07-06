// /Users/gabrielcampos/Documents/Prog/PortfolioESG_public/html/js/scoring.js

document.addEventListener('DOMContentLoaded', function() {
    // Use D3.js for robust CSV parsing
    fetchScoringData(); 
});

async function fetchScoringData() { // The paths below should be from the web root /html
    try {
        // Fetch summary data
        console.log("Fetching summary data from data/latest_run_summary.json...");  // Debug log

        const summaryResponse = await fetch('/html/data/latest_run_summary.json?t=' + new Date().getTime());
        if (!summaryResponse.ok) {
            throw new Error(`HTTP error! status: ${summaryResponse.status} - latest_run_summary.json`);
        }
        const summaryData = await summaryResponse.json();
        updateSummary(summaryData);

        // Fetch top stocks data
        console.log("Fetching top stocks data from data/top_stocks.json...");  // Debug log
        const topStocksResponse = await fetch('/html/data/top_stocks.json?t=' + new Date().getTime());
        if (!topStocksResponse.ok) {
            throw new Error(`HTTP error! status: ${topStocksResponse.status} - top_stocks.json`);
        }
        const topStocksData = await topStocksResponse.json();
        populateTopStocksTable(topStocksData);
    } catch (error) {
        console.error('Could not fetch scoring data:', error);
        displayError(`Could not load scoring data: ${error.message}. Please check the pipeline and data files.`); // Include error message
    }
}

 function updateSummary(data) {
    const datetimeSpan = document.getElementById('summary-datetime');
    const versionSpan = document.getElementById('summary-version');

    if (datetimeSpan && versionSpan) {
        datetimeSpan.textContent = data.run_timestamp || '-';  // Use a placeholder if missing
        versionSpan.textContent = data.scoring_version || '-';
    }
}

function populateTopStocksTable(data) {
    const tbody = document.getElementById('top-stocks-tbody');
    if (!tbody) return; // If tbody not found, exit
    tbody.innerHTML = ''; // Clear "Loading..."

    if (!data || data.length === 0) {
        tbody.innerHTML = '<tr><td colspan="11">No results found.</td></tr>';
        return;
    }
    data.forEach(stock => {
        const row = tbody.insertRow();
        row.insertCell().textContent = stock.Stock || '-';
        row.insertCell().textContent = stock.Sector || '-';
        row.insertCell().textContent = stock.Industry || '-';
        row.insertCell().textContent = stock.CompositeScore ? stock.CompositeScore.toFixed(4) : '-'; // Format numbers
        row.insertCell().textContent = stock.SharpeRatio ? stock.SharpeRatio.toFixed(4) : '-';
        row.insertCell().textContent = stock.PotentialUpside_pct ? (stock.PotentialUpside_pct * 100).toFixed(2) + '%' : '-'; // Format percentage
        row.insertCell().textContent = stock.Momentum ? stock.Momentum.toFixed(4) : '-';
        row.insertCell().textContent = stock.CurrentPrice ? stock.CurrentPrice.toFixed(2) : '-';
        row.insertCell().textContent = stock.TargetPrice ? stock.TargetPrice.toFixed(2) : '-';
        row.insertCell().textContent = stock.forwardPE ? stock.forwardPE.toFixed(2) : '-';
        row.insertCell().textContent = stock.SectorMedianPE ? stock.SectorMedianPE.toFixed(2) : '-';
    });
}

function displayError(message) {
    const mainContent = document.querySelector('.main-content');
    if (mainContent) {
        mainContent.innerHTML = `<p style="color: red;">${message}</p>`;
    }
}