// /Users/gabrielcampos/Documents/Prog/PortfolioESG_public/html/js/scoring.js

document.addEventListener('DOMContentLoaded', function() {
    // Use D3.js for robust CSV parsing
    d3.csv("data/scored_runs.csv?t=" + new Date().getTime())
        .then(function(data) {
            if (!data || data.length === 0) {
                console.warn("scored_runs.csv is empty or could not be loaded.");
                document.getElementById('latest-run-summary').innerHTML = '<p>No scoring data found.</p>';
                return;
            }

            // --- Find the latest run_id ---
            // This makes the page resilient to old, malformed data in the CSV.
            const latestRunId = data.reduce((max, row) => (row.run_id > max ? row.run_id : max), data[0].run_id);
            const latestRunData = data.filter(d => d.run_id === latestRunId);

            if (latestRunData.length === 0) {
                console.error("Could not find data for the latest run ID:", latestRunId);
                return;
            }

            // --- Populate Summary ---
            const firstRow = latestRunData[0];
            document.getElementById('summary-datetime').textContent = formatDate(firstRow.run_timestamp) || 'N/A';
            document.getElementById('summary-version').textContent = firstRow.scoring_version || 'N/A';

            // --- Populate Top 20 Stocks Table ---
            const tableBody = document.getElementById('top-stocks-tbody');
            tableBody.innerHTML = ''; // Clear existing rows
            const top20Data = latestRunData.slice(0, 20);

            top20Data.forEach(d => {
                let row = tableBody.insertRow();
                row.insertCell().textContent = d.Stock || 'N/A';
                row.insertCell().textContent = d.Sector || 'N/A';
                row.insertCell().textContent = d.Industry || 'N/A';
                row.insertCell().textContent = parseFloat(d.CompositeScore || 0).toFixed(4);
                row.insertCell().textContent = parseFloat(d.SharpeRatio || 0).toFixed(4);
                row.insertCell().textContent = parseFloat(d.PotentialUpside_pct || 0).toFixed(4);
                row.insertCell().textContent = parseFloat(d.Momentum || 0).toFixed(4);
                row.insertCell().textContent = parseFloat(d.CurrentPrice || 0).toFixed(2);
                row.insertCell().textContent = parseFloat(d.TargetPrice || 0).toFixed(2);
                row.insertCell().textContent = parseFloat(d.forwardPE || 0).toFixed(2);
                row.insertCell().textContent = parseFloat(d.SectorMedianPE || 0).toFixed(2);
            });

            // --- Render Charts ---
            renderSectorBreakdown(latestRunData);
            renderHistoricalTrends(data); // Pass all data for historical view
            renderCorrelationMatrix(latestRunData);

        }).catch(function(error) {
            console.error("Error loading or parsing scored_runs.csv:", error);
            document.getElementById('latest-run-summary').innerHTML = `<p style="color:red;">Error loading scoring data. Check console.</p>`;
        });
});

function renderSectorBreakdown(latestRunData) {
    const container = document.getElementById('sector-breakdown-chart');
    container.innerHTML = ''; // Clear loading text

    const sectorCounts = d3.rollup(latestRunData, v => v.length, d => d.Sector);
    const chartData = Array.from(sectorCounts, ([key, value]) => ({ sector: key, count: value }));

    const width = container.clientWidth;
    const height = 300;
    const radius = Math.min(width, height) / 2;

    const svg = d3.select(container).append("svg")
        .attr("width", width)
        .attr("height", height)
        .append("g")
        .attr("transform", `translate(${width / 2}, ${height / 2})`);

    const color = d3.scaleOrdinal(d3.schemeCategory10);
    const pie = d3.pie().value(d => d.count).sort(null);
    const arc = d3.arc().innerRadius(0).outerRadius(radius * 0.8);

    const g = svg.selectAll(".arc")
        .data(pie(chartData))
        .enter().append("g")
        .attr("class", "arc");

    g.append("path")
        .attr("d", arc)
        .style("fill", d => color(d.data.sector));

    g.append("text")
        .attr("transform", d => `translate(${arc.centroid(d)})`)
        .attr("dy", ".35em")
        .style("text-anchor", "middle")
        .style("fill", "#fff")
        .text(d => `${d.data.sector} (${d.data.count})`);
}

function renderHistoricalTrends(allData) {
    const container = document.getElementById('historical-trends-chart');
    container.innerHTML = '';

    // Group by run_id and calculate average composite score for each run
    const trends = d3.rollup(allData, 
        v => d3.mean(v, d => +d.CompositeScore), 
        d => d.run_id
    );
    const chartData = Array.from(trends, ([key, value]) => ({
        run_id: key,
        date: d3.timeParse("%Y%m%d_%H%M%S")(key),
        avgScore: value
    })).sort((a, b) => a.date - b.date);

    const margin = { top: 20, right: 30, bottom: 40, left: 50 };
    const width = container.clientWidth - margin.left - margin.right;
    const height = 300 - margin.top - margin.bottom;

    const svg = d3.select(container).append("svg")
        .attr("width", width + margin.left + margin.right)
        .attr("height", height + margin.top + margin.bottom)
        .append("g")
        .attr("transform", `translate(${margin.left},${margin.top})`);

    const x = d3.scaleTime().domain(d3.extent(chartData, d => d.date)).range([0, width]);
    const y = d3.scaleLinear().domain([0, d3.max(chartData, d => d.avgScore)]).range([height, 0]);

    svg.append("g").attr("transform", `translate(0,${height})`).call(d3.axisBottom(x));
    svg.append("g").call(d3.axisLeft(y));

    svg.append("path")
        .datum(chartData)
        .attr("fill", "none")
        .attr("stroke", "steelblue")
        .attr("stroke-width", 1.5)
        .attr("d", d3.line().x(d => x(d.date)).y(d => y(d.avgScore)));
}

function renderCorrelationMatrix(latestRunData) {
    const container = document.getElementById('correlation-matrix');
    container.innerHTML = '';

    const metrics = ['SharpeRatio', 'PotentialUpside_pct', 'Momentum'];
    const numericData = latestRunData.map(d => ({
        SharpeRatio: +d.SharpeRatio,
        PotentialUpside_pct: +d.PotentialUpside_pct,
        Momentum: +d.Momentum
    }));

    // Simple correlation calculation
    function correlation(arr1, arr2) {
        let n = arr1.length;
        let mean1 = d3.mean(arr1);
        let mean2 = d3.mean(arr2);
        let std1 = d3.deviation(arr1);
        let std2 = d3.deviation(arr2);
        if (std1 === 0 || std2 === 0) return 0;
        let cov = d3.mean(arr1.map((x, i) => (x - mean1) * (arr2[i] - mean2)));
        return cov / (std1 * std2);
    }

    const matrix = [];
    for (let i = 0; i < metrics.length; i++) {
        for (let j = 0; j < metrics.length; j++) {
            const arr1 = numericData.map(d => d[metrics[i]]);
            const arr2 = numericData.map(d => d[metrics[j]]);
            matrix.push({
                x: metrics[i],
                y: metrics[j],
                value: correlation(arr1, arr2)
            });
        }
    }

    const margin = { top: 50, right: 20, bottom: 20, left: 120 };
    const width = 400 - margin.left - margin.right;
    const height = 300 - margin.top - margin.bottom;

    const svg = d3.select(container).append("svg")
        .attr("width", width + margin.left + margin.right)
        .attr("height", height + margin.top + margin.bottom)
        .append("g")
        .attr("transform", `translate(${margin.left},${margin.top})`);

    const x = d3.scaleBand().range([0, width]).domain(metrics).padding(0.05);
    svg.append("g")
        .attr("transform", `translate(0, -5)`)
        .call(d3.axisTop(x).tickSize(0))
        .select(".domain").remove();

    const y = d3.scaleBand().range([height, 0]).domain(metrics).padding(0.05);
    svg.append("g")
        .call(d3.axisLeft(y).tickSize(0))
        .select(".domain").remove();

    const color = d3.scaleSequential(d3.interpolateRdBu).domain([-1, 1]);

    svg.selectAll()
        .data(matrix, d => d.x + ':' + d.y)
        .enter()
        .append("rect")
        .attr("x", d => x(d.x))
        .attr("y", d => y(d.y))
        .attr("width", x.bandwidth())
        .attr("height", y.bandwidth())
        .style("fill", d => color(d.value));

    svg.selectAll()
        .data(matrix, d => d.x + ':' + d.y)
        .enter()
        .append("text")
        .attr("x", d => x(d.x) + x.bandwidth() / 2)
        .attr("y", d => y(d.y) + y.bandwidth() / 2)
        .attr("dy", ".35em")
        .style("text-anchor", "middle")
        .style("fill", d => Math.abs(d.value) > 0.5 ? "white" : "black")
        .text(d => d.value.toFixed(2));
}