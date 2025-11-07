// filepath: html/js/assets.js
/*
 * Loads ledger.csv and portfolio_timeseries.csv and renders:
 * - Ledger table and pie (current positions from ledger.csv)
 * - Pipeline latest portfolio (stock-level) table and pie (from portfolio_timeseries.csv)
 * - Comparison bar chart (pipeline stocks vs ledger tickers)
 */

const LEDGER_CSV_CANDIDATES = ['/data/ledger.csv', '../data/ledger.csv', 'data/ledger.csv'];
const PORTFOLIO_TS_CSV_CANDIDATES = ['/html/data/portfolio_timeseries.csv', '/html/data/portfolio_results_db.csv', '/data/portfolio_timeseries.csv', '../data/portfolio_timeseries.csv', 'data/portfolio_timeseries.csv'];
const SCORED_STOCKS_CSV_CANDIDATES = ['/data/results/scored_stocks.csv','/html/data/scored_stocks.csv','/data/scored_stocks.csv','../data/results/scored_stocks.csv'];
// Backwards-compatibility aliases: some legacy code references `SCORED_STOCKS_CANDIDATES` or expects these on window.
var SCORED_STOCKS_CANDIDATES = SCORED_STOCKS_CSV_CANDIDATES; // var so it's available globally across scripts
window.SCORED_STOCKS_CSV_CANDIDATES = SCORED_STOCKS_CSV_CANDIDATES;
window.SCORED_STOCKS_CANDIDATES = SCORED_STOCKS_CANDIDATES;

// Try consolidated JSON ledger first to avoid recomputing aggregation on the client every time.
const CONSOLIDATED_LEDGER_JSON_CANDIDATES = [
    '/data/ledger_positions.json',
    '/data/ledger_consolidated.json',
    '../data/ledger_positions.json',
    'data/ledger_positions.json'
];

// New: pipeline JSON candidates prefer relative paths first (works when site is served from /html/)
const PIPELINE_JSON_CANDIDATES = [
    '../data/pipeline_latest.json',
    'data/pipeline_latest.json',
    '/data/pipeline_latest.json',
    '/html/data/pipeline_latest.json',
    '../html/data/pipeline_latest.json'
];

function safeParseFloat(v) {
    if (v === undefined || v === null || v === '') return 0;
    const n = parseFloat(String(v).replace(/[^0-9.-]/g, ''));
    return isNaN(n) ? 0 : n;
}

// Lightweight debug logger used throughout this file. Enable by setting window.ASSETS_DEBUG = true in the console.
const DEBUG_MODE = !!window.ASSETS_DEBUG;
function debugLog(...args) {
    if (DEBUG_MODE && console && console.debug) {
        console.debug('[Assets]', ...args);
    }
}

async function tryFetchCsvFromCandidates(candidates) {
    // Try each candidate path until one returns OK and parse succeeds
    for (const p of candidates) {
        try {
            const rows = await fetchAndParseCsv(p);
            // If parse returned something (even empty array), return it
            return { path: p, rows };
        } catch (err) {
            // Continue to next candidate
            console.warn(`Failed to load CSV from ${p}:`, err.message || err);
            continue;
        }
    }
    throw new Error(`Failed to load CSV from candidates: ${candidates.join(', ')}`);
}

async function tryFetchJsonFromCandidates(candidates) {
    const attempts = [];
    for (const p of candidates) {
        try {
            const url = p + '?t=' + new Date().getTime();
            const resp = await fetch(url);
            attempts.push({ path: p, status: resp.status });
            if (!resp.ok) {
                // continue to next candidate
                continue;
            }
            // try parse JSON
            try {
                const json = await resp.json();
                return { path: p, json };
            } catch (parseErr) {
                attempts.push({ path: p, error: 'json_parse_error', message: parseErr && parseErr.message });
                continue;
            }
        } catch (err) {
            attempts.push({ path: p, error: err && err.message ? err.message : String(err) });
            continue;
        }
    }
    // return attempts for diagnostic purposes when nothing found
    return { attempts };
}

async function loadLedgerAggregates() {
    // Load consolidated ledger JSON (single authoritative source)
    try {
        // Try multiple JSON candidate paths first (fastest path when available)
        let src = null;
        try {
            const res = await tryFetchJsonFromCandidates(CONSOLIDATED_LEDGER_JSON_CANDIDATES);
            if (res && res.json) src = res.json;
        } catch (e) {
            console.debug('No consolidated ledger JSON found in candidates:', e && e.message);
        }

        // If no JSON consolidated ledger, try ledger CSV candidates and use the parsed rows as the source
        if (!src) {
            try {
                const csvRes = await tryFetchCsvFromCandidates(LEDGER_CSV_CANDIDATES);
                if (csvRes && csvRes.rows) src = csvRes.rows;
            } catch (e) {
                console.debug('No ledger CSV found in candidates:', e && e.message);
            }
        }

        if (!src) {
            // Nothing found, return empty array rather than throwing so the page can show a friendly message
            return [];
        }
        let arr = [];
        // Accept wrapper shape { positions: [...] }
        // Validate src.positions before mapping
        if (src && Array.isArray(src.positions)) {
            arr = src.positions.filter(r => typeof r === 'object' && r !== null).map(r => ({
                ticker: (r.ticker || r.Ticker || r.symbol || '').trim(),
                symbol: (r.symbol || r.Symbol || r.ticker_symbol || null),
                net_qty: safeParseFloat(r.net_qty || r.netQty || r.quantity || r.qty || 0),
                net_invested: safeParseFloat(r.net_invested || r.netInvested || r.invested || r.net_value || r.total_invested || 0),
                target_price: (r.target_price !== undefined && r.target_price !== null) ? safeParseFloat(r.target_price) : null,
                current_price: (r.current_price !== undefined && r.current_price !== null) ? safeParseFloat(r.current_price) : null
            })).filter(x => x.ticker || x.symbol);
            return arr.sort((a,b) => Math.abs(b.net_invested) - Math.abs(a.net_invested));
        }

        // If file is already an array of positions
        if (Array.isArray(src)) {
            arr = src.map(r => ({
                ticker: (r.ticker || r.Ticker || r.symbol || '').trim(),
                symbol: (r.symbol || r.Symbol || null),
                net_qty: safeParseFloat(r.net_qty || r.netQty || r.quantity || r.qty || 0),
                net_invested: safeParseFloat(r.net_invested || r.netInvested || r.invested || r.net_value || r.total_invested || 0),
                target_price: (r.target_price !== undefined && r.target_price !== null) ? safeParseFloat(r.target_price) : null,
                current_price: (r.current_price !== undefined && r.current_price !== null) ? safeParseFloat(r.current_price) : null
            })).filter(x => x.ticker || x.symbol);
            return arr.sort((a,b) => Math.abs(b.net_invested) - Math.abs(a.net_invested));
        }

        // If it's an object keyed by ticker
        if (typeof src === 'object' && src !== null) {
            const keys = Object.keys(src);
            if (keys.length > 0) {
                arr = keys.map(k => {
                    const v = src[k];
                    if (typeof v === 'number') return { ticker: String(k).trim(), symbol: null, net_qty: 0, net_invested: safeParseFloat(v), target_price: null, current_price: null };
                    if (typeof v === 'object' && v !== null) return {
                        ticker: String(k).trim(),
                        symbol: v.symbol || null,
                        net_qty: safeParseFloat(v.net_qty || v.qty || v.quantity || 0),
                        net_invested: safeParseFloat(v.net_invested || v.invested || v.value || v.total || 0),
                        target_price: (v.target_price !== undefined && v.target_price !== null) ? safeParseFloat(v.target_price) : null,
                        current_price: (v.current_price !== undefined && v.current_price !== null) ? safeParseFloat(v.current_price) : null
                    };
                    return null;
                }).filter(Boolean);
                return arr.sort((a,b) => Math.abs(b.net_invested) - Math.abs(a.net_invested));
            }
        }

        // Nothing usable
        return [];
    } catch (err) {
        console.warn('Failed to load /data/ledger_positions.json:', err);
        // Re-throw so callers can show an error state
        throw err;
    }
}

function formatBRL(n) {
    if (n === null || n === undefined) return 'N/A';
    return Number(n).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL', minimumFractionDigits: 2 });
}

async function renderLedgerSection() {
    try {
        const ledger = await loadLedgerAggregates();
        const tbody = document.getElementById('ledger-tbody');
        if (!tbody) return { ledger: [], positiveInvested: [], totalInvested: 0 };

        // calculate projection per row
        const positiveInvested = ledger.filter(l => l.net_qty > 0 && l.net_invested > 0);
        const totalInvested = positiveInvested.reduce((s, i) => s + i.net_invested, 0);
        const totalQty = ledger.reduce((s, i) => s + (i.net_qty > 0 ? i.net_qty : 0), 0);

        if (ledger.length === 0) {
            tbody.innerHTML = '<tr><td colspan="8">No ledger data available.</td></tr>';
            return { ledger, positiveInvested, totalInvested };
        }

        // attempt to fill current prices for ledger symbols if missing
        const symbolsToFetch = ledger.map(r => r.symbol || r.ticker).filter(Boolean);
        const pricesMap = await getLatestPricesForList(symbolsToFetch);
        const scoredSymbolMap = await loadScoredSymbolMap();
        // load scored targets so ledger rows can show target prices when missing in the ledger JSON
        const scoredTargetMap = await loadScoredTargetMap();
        // pipeline JSON fallback targets (if pipeline_latest.json contains detailed rows with 'target')
        let pipelineTargetMap = {};
        let pipelineJsonPathUsed = null;
        try {
            const pCandidates = Array.from(new Set([window.location.pathname.replace(/\/[^\/]*$/, '') + '/../data/pipeline_latest.json', '../data/pipeline_latest.json', '/data/pipeline_latest.json', 'data/pipeline_latest.json']));
            const pj = await tryFetchJsonFromCandidates(pCandidates);
            if (pj && pj.json && Array.isArray(pj.json.rows)) {
                pipelineJsonPathUsed = pj.path || null;
                pj.json.rows.forEach(r => {
                    const t = r.ticker || r.Ticker || r.symbol || '';
                    const tp = (r.target !== undefined && r.target !== null) ? safeParseFloat(r.target) : (r.TargetPrice !== undefined ? safeParseFloat(r.TargetPrice) : null);
                    if (t && tp !== null) pipelineTargetMap[normalizeTicker(t)] = tp;
                });
            }
        } catch (e) { /* ignore */ }

        debugLog('scoredTargetMap keys sample:', Object.keys(scoredTargetMap).slice(0,10));
        // compute missing target diagnostics early so we can show it in the UI
        const missingTargetsCount = ledger.reduce((c, row) => {
            const displaySym = (row.symbol || (scoredSymbolMap[normalizeTicker(row.ticker || '')] || row.ticker || '')).trim();
            const existingTp = (row.target_price !== undefined && row.target_price !== null && Number(row.target_price) !== 0) ? safeParseFloat(row.target_price) : null;
            const found = existingTp !== null && existingTp !== 0 ? true : (!!scoredTargetMap[normalizeTicker(displaySym)] || !!scoredTargetMap[normalizeTicker(row.ticker || '')] || !!pipelineTargetMap[normalizeTicker(displaySym)] || !!pipelineTargetMap[normalizeTicker(row.ticker || '')]);
            return c + (found ? 0 : 1);
        }, 0);
        try {
            const ledgerNoteEl = document.getElementById('ledger-note');
            if (ledgerNoteEl) ledgerNoteEl.textContent = `Scored targets: ${window.LAST_SCORED_CSV_PATH || 'none'}; pipeline targets: ${pipelineJsonPathUsed || 'none'} — missing targets: ${missingTargetsCount}`;
        } catch (e) {}

        let totalProjected = 0;
        let totalProjectedCount = 0;
        let totalCurrentMarket = 0;
        // accumulate for ledger unit cost weighted average
        let totalUnitCostQty = 0;
        let totalUnitCostSum = 0;

        const rowsHtml = ledger.map(row => {
            const invested = row.net_invested || 0;
            const qty = row.net_qty || 0;
            // compute unit cost: prefer detailed lots weighted average, else fallback to net_invested/net_qty
            let unitCost = null;
            try {
                if (row.lots && Array.isArray(row.lots) && row.lots.length > 0) {
                    let totalQtyLot = 0, totalCostLot = 0;
                    row.lots.forEach(l => {
                        const lq = safeParseFloat(l.qty || l.Qty || l.quantity || 0);
                        const uc = safeParseFloat(l.unit_cost || l.unitCost || l.price || l.unitPrice || 0);
                        if (lq && uc) { totalQtyLot += lq; totalCostLot += (lq * uc); }
                    });
                    if (totalQtyLot > 0) unitCost = totalCostLot / totalQtyLot;
                }
                if ((unitCost === null || unitCost === 0) && qty) {
                    unitCost = safeParseFloat(invested / (qty || 1));
                }
            } catch (e) { unitCost = null; }
             // determine display symbol: prefer explicit symbol, else try scored map using normalized ticker/name
             let displaySymbol = row.symbol || null;
             if (!displaySymbol) {
                 const norm = normalizeTicker(row.ticker || '');
                 if (scoredSymbolMap[norm]) displaySymbol = scoredSymbolMap[norm];
             }
             if (!displaySymbol) displaySymbol = row.ticker;

            const currentPrice = (row.current_price !== undefined && row.current_price !== null) ? row.current_price : (pricesMap[(row.symbol || row.ticker || displaySymbol)] || null);
            // determine target price: prefer row.target_price, else try scored targets by normalized displaySymbol or ticker
            let tp = (row.target_price !== undefined && row.target_price !== null) ? safeParseFloat(row.target_price) : null;
            if ((tp === null || tp === 0) && displaySymbol) {
                const t = scoredTargetMap[normalizeTicker(displaySymbol)] || scoredTargetMap[normalizeTicker(row.ticker)] || pipelineTargetMap[normalizeTicker(displaySymbol)] || pipelineTargetMap[normalizeTicker(row.ticker)];
                debugLog('lookup target for', displaySymbol, normalizeTicker(displaySymbol), '->', t);
                if (t) tp = safeParseFloat(t);
            }

            let projected = null;
            let diff = null;
            if (tp && !isNaN(tp) && Number(tp) !== 0 && qty !== 0) {
                projected = qty * tp;
                diff = projected - invested;
                totalProjected += projected;
                totalProjectedCount += 1;
            }
            if (currentPrice && !isNaN(currentPrice) && qty !== 0) {
                totalCurrentMarket += qty * currentPrice;
            }
            // accumulate unit cost totals for weighted average
            if (unitCost !== null && unitCost !== undefined && qty && qty > 0) {
                totalUnitCostQty += qty;
                totalUnitCostSum += unitCost * qty;
            }

            const pct = (invested > 0 && totalInvested > 0) ? (invested / totalInvested * 100) : 0;

            // current position value = current price * quantity
            const currentPosition = (currentPrice !== null && currentPrice !== undefined && qty !== 0) ? (currentPrice * qty) : null;

            return `<tr>
                <td>${displaySymbol}</td>
                <td>${unitCost !== null && unitCost !== undefined ? formatBRL(unitCost) : '-'}</td>
                <td>${Number(qty || 0).toFixed(0)}</td>
                <td>${formatBRL(invested)}</td>
                <td>${pct.toFixed(2)}%</td>
                <td>${currentPrice !== null && currentPrice !== undefined ? formatBRL(currentPrice) : '-'}</td>
                <td>${currentPosition !== null ? formatBRL(currentPosition) : '-'}</td>
                <td>${tp !== null && tp !== undefined && tp !== 0 ? formatBRL(tp) : '-'}</td>
                <td>${projected !== null ? formatBRL(projected) : '-'}</td>
                <td>${diff !== null ? formatBRL(diff) : '-'}</td>
            </tr>`;
        }).join('');

        tbody.innerHTML = rowsHtml;
        document.getElementById('ledger-total-qty').textContent = totalQty.toFixed(0);
        document.getElementById('ledger-total-invested').textContent = formatBRL(totalInvested);
        document.getElementById('ledger-total-pct').textContent = '100%';
        document.getElementById('ledger-total-projected').textContent = totalProjectedCount > 0 ? formatBRL(totalProjected) : '-';
        document.getElementById('ledger-total-diff').textContent = totalProjectedCount > 0 ? formatBRL(totalProjected - totalInvested) : '-';
        // new: ledger total current position (sum of qty * current price)
        document.getElementById('ledger-total-current-position').textContent = totalCurrentMarket && totalCurrentMarket > 0 ? formatBRL(totalCurrentMarket) : '-';
        // ledger weighted average unit cost
        try {
            const avgUnitCost = (totalUnitCostQty > 0) ? (totalUnitCostSum / totalUnitCostQty) : null;
            document.getElementById('ledger-total-unitcost').textContent = (avgUnitCost !== null && !isNaN(avgUnitCost)) ? formatBRL(avgUnitCost) : '-';
        } catch (e) {}

        // Pie chart for ledger (only positive invested items)
        const pieDiv = document.getElementById('ledger-pie');
        const labels = positiveInvested.map(i => i.symbol || (scoredSymbolMap[normalizeTicker(i.ticker)] || i.ticker));
        const values = positiveInvested.map(i => i.net_invested);
        if (pieDiv) {
            pieDiv.innerHTML = '';
            if (labels.length === 0) {
                pieDiv.textContent = 'No positive positions to display.';
            } else {
                const data = [{ labels, values, type: 'pie', hole: 0.3 }];
                const layout = { title: 'Ledger Composition (by invested BRL)', height: 320, legend: { orientation: 'h' } };
                Plotly.newPlot(pieDiv, data, layout, {responsive: true});
            }
        }

        // Return totals including current market proceeds (cash we'd get if we sold all positions at latest prices)
        return { ledger, positiveInvested, totalInvested, totalCurrentMarket };
    } catch (error) {
        console.error('Error rendering ledger section:', error);
        const tbody = document.getElementById('ledger-tbody');
        if (tbody) tbody.innerHTML = `<tr class="status-error-row"><td colspan="8">Failed to load ledger. ${error.message}</td></tr>`;
        return { ledger: [], positiveInvested: [], totalInvested: 0 };
    }
}

// --- Portfolio timeseries parsing ---
function pickLatestRun(rows) {
    if (!rows || rows.length === 0) return null;
    // prefer columns: run_id, run_timestamp
    const hasRunId = rows.some(r => r.run_id !== undefined && r.run_id !== '');
    if (hasRunId) {
        // choose max run_id (numeric or lexicographic)
        let maxId = rows.reduce((max, r) => (r.run_id > max ? r.run_id : max), rows[0].run_id);
        const filtered = rows.filter(r => r.run_id === maxId);
        return { type: 'group', run_id: maxId, rows: filtered };
    }
    // else, check timestamp/date fields
    const tsKeys = ['run_timestamp','timestamp','date','datetime'];
    for (const k of tsKeys) {
        if (rows.some(r => r[k])) {
            // pick row(s) with latest date
            let latest = null; let latestVal = -Infinity;
            rows.forEach(r => {
                try {
                    const val = new Date(r[k]).getTime();
                    if (!isNaN(val) && val > latestVal) { latestVal = val; latest = r; }
                } catch(e) {}
            });
            if (latest) return { type: 'single', timestamp_key: k, row: latest };
        }
    }
    // fallback: if rows look tall (each row is a ticker-weight), group by nothing and use last row's run_id if present
    return { type: 'single', row: rows[rows.length-1] };
}

function parsePortfolioFromTimeseriesRows(rows) {
    if (!rows || rows.length === 0) return { stocks: [], weights: [] };
    // Detect tall format: rows with ticker and weight columns
    const hasTickerCol = rows.some(r => r.ticker !== undefined || r.Ticker !== undefined || r.symbol !== undefined || r.ticker_symbol !== undefined);
    const hasWeightCol = rows.some(r => r.weight !== undefined || r.Weight !== undefined || r.weight_pct !== undefined || r.weight_pct !== undefined || r.weight_pct !== undefined || r.pct !== undefined);
    if (hasTickerCol && hasWeightCol) {
        // If pickLatestRun returned group-type (many rows with same run), use those rows
        // Group by run_id or timestamp if present
        const latestInfo = pickLatestRun(rows);
        if (latestInfo.type === 'group') {
            const runRows = latestInfo.rows;
            const stocks = runRows.map(r => (r.ticker || r.Ticker || r.symbol || '').trim()).filter(Boolean);
            const weights = runRows.map(r => safeParseFloat(r.weight || r.Weight || r.weight_pct || r.pct || r.weight_percent || r.weightPercentage));
            return { stocks, weights };
        } else if (latestInfo.type === 'single' && latestInfo.row) {
            // there's a single row; maybe this is wide shape
            const row = latestInfo.row;
            // If the single row contains 'tickers' and 'weights' as comma lists
            const tickersField = row.tickers || row.Tickers || row.stocks || row.assets || row.ticker_list;
            const weightsField = row.weights || row.weights_pct || row.weights_percent || row.weight_list || row.weights_list;
            if (tickersField && weightsField) {
                const stocks = String(tickersField).replace(/"/g,'').split(',').map(s => s.trim()).filter(Boolean);
                const weights = String(weightsField).replace(/"/g,'').split(',').map(s => safeParseFloat(s));
                return { stocks, weights };
            }
            // else maybe the row itself is a ticker row
            const stock = (row.ticker || row.Ticker || row.symbol || '').trim();
            const weight = safeParseFloat(row.weight || row.Weight || row.weight_pct || row.pct || 0);
            if (stock) return { stocks: [stock], weights: [weight] };
        }
    }

    // Wide single-row format: one row contains fields like stock_1, weight_1, stock_2, weight_2
    const sample = rows[0];
    const stockKeys = Object.keys(sample).filter(k => /^(stock|ticker|asset)[_\d]*$/i.test(k));
    const weightKeys = Object.keys(sample).filter(k => /^(weight|weight_pct|weight%|pct)[_\d]*$/i.test(k));
    if (stockKeys.length && weightKeys.length) {
        // Pair by order
        const stocks = stockKeys.map(k => String(sample[k]).trim()).filter(Boolean);
        const weights = stockKeys.map((k, i) => {
            const maybe = weightKeys[i] || weightKeys.find(wk => wk.match(/\d+/) && wk.match(/\d+/)[0] === (k.match(/\d+/) || [''])[0]);
            return safeParseFloat(maybe ? sample[maybe] : 0);
        });
        return { stocks, weights };
    }

    // As a last resort, attempt to parse a 'composition' comma-delimited field
    const first = rows[0];
    const possibleTickersField = first.tickers || first.stocks || first.assets || first.composition;
    const possibleWeightsField = first.weights || first.weights_pct || first.weights_percent || null;
    if (possibleTickersField) {
        const stocks = String(possibleTickersField).replace(/"/g,'').split(',').map(s => s.trim()).filter(Boolean);
        let weights = [];
        if (possibleWeightsField) weights = String(possibleWeightsField).replace(/"/g,'').split(',').map(s => safeParseFloat(s));
        if (stocks.length && (weights.length === stocks.length || weights.length === 0)) return { stocks, weights };
    }

    return { stocks: [], weights: [] };
}

// Helper: build pipeline row objects (sorted by projectedInvested desc) and totals
async function buildPipelineRowsData(stocks, weights, ledgerTotalInvested, priceMap, targetMap) {
    const rows = [];
    let totalCurrentSum = 0;
    let totalProjectedQty = 0;
    let totalProjectedInvested = 0; // projectedQty * current
    let totalProjectedBRL = 0; // projectedQty * target
    let totalPct = 0;

    for (let i = 0; i < stocks.length; i++) {
        const s = stocks[i];
        const weight = safeParseFloat(weights[i] || 0);
        totalPct += weight;
        // Use the ledgerTotalInvested argument as the cash-on-hand (proceeds from selling current positions)
        const allocated = (ledgerTotalInvested && ledgerTotalInvested > 0) ? (ledgerTotalInvested * (weight / 100)) : null;
        const current = (priceMap && priceMap[s] !== undefined) ? priceMap[s] : null;
        const tp = (targetMap && targetMap[normalizeTicker(s)] !== undefined) ? targetMap[normalizeTicker(s)] : null;

        // projected quantity: whole shares only (we cannot buy fractional shares)
        const projectedQty = (allocated !== null && current !== null && current !== 0) ? Math.floor(allocated / current) : null;
        // cash actually used to buy whole shares
        const projectedInvested = (projectedQty !== null && current !== null) ? Math.floor(projectedQty * current) : null;
        // projected value at target price for the purchased whole shares
        const projectedBRL = (projectedQty !== null && tp !== null) ? (projectedQty * tp) : null;

        if (allocated !== null) totalCurrentSum += allocated;
        if (projectedQty !== null) totalProjectedQty += projectedQty;
        if (projectedInvested !== null) totalProjectedInvested += projectedInvested;
        if (projectedBRL !== null) totalProjectedBRL += projectedBRL;

        rows.push({
            ticker: s,
            weight,
            current,
            projectedQty,
            projectedInvested,
            target: tp,
            projectedBRL
        });
    }

    // sort descending by projectedInvested (null treated as 0)
    rows.sort((a,b) => (b.projectedInvested || 0) - (a.projectedInvested || 0));

    return {
        rows,
        totals: {
            totalPct,
            totalCurrentSum,
            totalProjectedQty,
            totalProjectedInvested,
            totalProjectedBRL
        }
    };
}

async function renderPipelineSection(ledgerTotalInvested = 0) {
    try {
        // build dynamic candidates relative to current document path to handle different server roots
        const docDir = window.location.pathname ? window.location.pathname.replace(/\/[^\/]*$/, '') : '';
        const dynamicCandidates = [];
        try {
            if (docDir) {
                // e.g. if page is /html/assets.html, then try /html/../data/... => /data/...
                dynamicCandidates.push(docDir + '/../data/pipeline_latest.json');
                dynamicCandidates.push(docDir + '/data/pipeline_latest.json');
                dynamicCandidates.push(docDir + '/../html/data/pipeline_latest.json');
            }
        } catch (e) { /* ignore */ }
        const pipelineCandidates = Array.from(new Set([...dynamicCandidates, ...PIPELINE_JSON_CANDIDATES]));

        // Prefer pipeline JSON output (produced by engines/generate_assets_json.py) to avoid parsing CSV on the client
        let rows = [];
        let usedPath = null;
        try {
            const jsonRes = await tryFetchJsonFromCandidates(pipelineCandidates);
            // If tryFetchJsonFromCandidates returned diagnostic attempts (no JSON found), show them and fall through to CSV fallback
            if (jsonRes && jsonRes.attempts && !jsonRes.json) {
                const noteEl = document.getElementById('pipeline-note');
                try {
                    const attemptsText = jsonRes.attempts.map(a => {
                        if (a.status) return `${a.path} -> HTTP ${a.status}`;
                        if (a.error) return `${a.path} -> ERROR: ${a.error}`;
                        return String(a.path);
                    }).join('; ');
                    if (noteEl) noteEl.textContent = `No pipeline JSON found. Attempts: ${attemptsText}`;
                } catch (e) { /* ignore UI errors */ }
            }
            if (jsonRes && jsonRes.json) {
                 // JSON may contain 'rows' (detailed) or 'stocks'/'weights'
                 const j = jsonRes.json;
                 usedPath = jsonRes.path || usedPath;
                 if (Array.isArray(j.rows) && j.rows.length > 0) {
                    // Use the detailed rows directly — they already contain the fields we need.
                    const dataRows = j.rows.map(r => ({
                        ticker: r.ticker || r.Ticker || r.symbol || '',
                        weight: safeParseFloat(r.weight || r.Weight || 0),
                        current: (r.current !== undefined && r.current !== null) ? safeParseFloat(r.current) : null,
                        projectedQty: (r.projectedQty !== undefined) ? r.projectedQty : (r.projectedQty === 0 ? 0 : null),
                        projectedInvested: (r.projectedInvested !== undefined) ? safeParseFloat(r.projectedInvested) : null,
                        target: (r.target !== undefined && r.target !== null) ? safeParseFloat(r.target) : null,
                        projectedBRL: (r.projectedBRL !== undefined) ? safeParseFloat(r.projectedBRL) : null
                    }));
                    // build stocks/weights arrays for pie/summary
                    const stocksList = dataRows.map(r => r.ticker).filter(Boolean);
                    const weightsList = dataRows.map(r => r.weight || 0);
                    rows = [{ stocks: stocksList.join(','), weights: weightsList.join(',') }];
                    // store detailed rows & totals to render below
                    var pipelineDetailedRows = dataRows;
                    var pipelineDetailedTotals = j.totals || null;
                    debugLog('Loaded pipeline JSON rows (detailed) from', usedPath);
                 } else if (Array.isArray(j.stocks) && j.stocks.length > 0) {
                     // create synthetic single-row shape with stocks and weights
                     rows = [{ stocks: j.stocks.join(','), weights: (j.weights||[]).join(',') }];
                     debugLog('Loaded pipeline JSON (stocks list) from', usedPath);
                 }
            }
        } catch (je) {
            // ignore and fallback to CSV
            debugLog('No pipeline JSON found, will try CSV candidates:', je && je.message);
            rows = [];
        }

        // If we didn't get pipeline JSON rows, fallback to CSV logic
        if (!rows || rows.length === 0) {
            const primaryPath = '/html/data/portfolio_results_db.csv';
            try {
                rows = await fetchAndParseCsv(primaryPath);
                usedPath = primaryPath;
                debugLog('Loaded pipeline results from', primaryPath, 'rows:', rows ? rows.length : 0);
            } catch (ePrimary) {
                debugLog(`Primary pipeline CSV not found at ${primaryPath}, trying candidates...`, ePrimary && ePrimary.message);
                try {
                    const res = await tryFetchCsvFromCandidates(PORTFOLIO_TS_CSV_CANDIDATES);
                    rows = res.rows || [];
                    usedPath = res.path;
                    debugLog('Loaded pipeline results from candidate', usedPath, 'rows:', rows ? rows.length : 0);
                } catch (eFallback) {
                    debugLog('No pipeline CSV found in candidates:', eFallback && eFallback.message);
                    rows = [];
                }
            }
        }
        // Detailed debug: log which path was used and a preview of parsed rows
        try {
            console.debug('[Assets] pipeline usedPath:', usedPath);
            console.debug('[Assets] pipeline rows count:', rows ? rows.length : 0);
            if (rows && rows.length > 0) console.debug('[Assets] pipeline sample last row:', rows[rows.length-1]);
        } catch (eDbg) { /* ignore debug errors */ }

        if (!rows || rows.length === 0) {
            const tbody = document.getElementById('pipeline-tbody');
            const note = document.getElementById('pipeline-note');
            if (note) note.textContent = `No pipeline results found${usedPath ? ' (tried ' + usedPath + ')' : ''}.`;
            if (tbody) tbody.innerHTML = '<tr><td colspan="7">No portfolio stock-level composition available (pipeline data missing).</td></tr>';
            const pieDiv = document.getElementById('pipeline-pie'); if (pieDiv) pieDiv.textContent = 'No stock-level composition available.';
            return { stocks: [], weights: [], totals: {} };
        }

        // choose latest row (use last row as latest run)
        const last = rows[rows.length - 1];
        const stocksField = last.stocks || last.Stocks || last.stock || last.tickers || last.Tickers || last.stocks_list || last.assets;
        const weightsField = last.weights || last.Weights || last.weight || last.weights_list || last.weights_pct;

        let stocks = [];
        let weights = [];
        if (stocksField) stocks = String(stocksField).replace(/"/g,'').split(',').map(s => s.trim()).filter(Boolean);
        if (weightsField) weights = String(weightsField).replace(/"/g,'').split(',').map(s => safeParseFloat(s));

        if (!stocks || stocks.length === 0) {
            const tbody = document.getElementById('pipeline-tbody');
            const note = document.getElementById('pipeline-note');
            if (note) note.textContent = `No portfolio composition found${usedPath ? ' (tried ' + usedPath + ')' : ''}.`;
            if (tbody) tbody.innerHTML = '<tr><td colspan="7">No portfolio stock-level composition available.</td></tr>';
            const pieDiv = document.getElementById('pipeline-pie'); if (pieDiv) pieDiv.textContent = 'No stock-level composition available.';
            return { stocks: [], weights: [], totals: {} };
        }

        // Normalize weights: if fractional (sum ~1) convert to percentages
        if (!weights || weights.length !== stocks.length) {
            weights = stocks.map(_ => 100 / stocks.length);
        } else {
            const sum = weights.reduce((s,v) => s + (v||0), 0);
            if (sum > 0 && sum <= 1.1) weights = weights.map(w => (w || 0) * 100);
        }

        const tbody = document.getElementById('pipeline-tbody');
        const note = document.getElementById('pipeline-note');
        if (note) note.textContent = `Loaded latest portfolio composition from ${usedPath || 'source'} (latest run).`;

        // fetch current prices and scored targets
        const priceMap = await getLatestPricesForList(stocks);
        const targetMap = await loadScoredTargetMap();

        let dataRows = null;
        let totals = null;
        if (typeof pipelineDetailedRows !== 'undefined' && pipelineDetailedRows !== null) {
            // use server-provided detailed rows if available (they already include projections)
            dataRows = pipelineDetailedRows;
            totals = pipelineDetailedTotals || { totalPct: weights.reduce((a,b)=>a+(b||0),0), totalCurrentSum: null, totalProjectedQty: null, totalProjectedInvested: null, totalProjectedBRL: null };
        } else {
            const built = await buildPipelineRowsData(stocks, weights, ledgerTotalInvested, priceMap, targetMap);
            dataRows = built.rows;
            totals = built.totals;
        }

        // compute per-row gain/loss and totals
        let totalGainLoss = 0;
        const rowsHtml = dataRows.map(r => {
            const projectedInvested = (r.projectedInvested !== null && r.projectedInvested !== undefined) ? Number(r.projectedInvested) : 0;
            const projectedBRL = (r.projectedBRL !== null && r.projectedBRL !== undefined) ? Number(r.projectedBRL) : 0;
            const gainloss = (projectedBRL - projectedInvested);
            if (!isNaN(gainloss)) totalGainLoss += gainloss;
            return `<tr>
                <td>${r.ticker}</td>
                <td>${r.current !== null ? formatBRL(r.current) : '-'}</td>
                <td>${r.projectedQty !== null ? Number(r.projectedQty).toFixed(0) : '-'}</td>
                <td>${r.projectedInvested !== null ? formatBRL(r.projectedInvested) : '-'}</td>
                <td>${(r.weight||0).toFixed(2)}%</td>
                <td>${r.target !== null ? formatBRL(r.target) : '-'}</td>
                <td>${r.projectedBRL !== null ? formatBRL(r.projectedBRL) : '-'}</td>
                <td>${!isNaN(gainloss) ? formatBRL(gainloss) : '-'}</td>
            </tr>`;
        }).join('');

        if (tbody) tbody.innerHTML = rowsHtml;
        const pieDiv = document.getElementById('pipeline-pie'); if (pieDiv) { pieDiv.innerHTML=''; Plotly.newPlot(pieDiv, [{labels:stocks, values:weights, type:'pie', hole:0.3}], {title:'Pipeline (latest) Portfolio Composition (stocks %)', height:320}, {responsive:true}); }

        // update pipeline totals (match footer order)
        document.getElementById('pipeline-total-current').textContent = '-';
        document.getElementById('pipeline-total-qty-projected').textContent = (totals && totals.totalProjectedQty && totals.totalProjectedQty > 0) ? totals.totalProjectedQty.toFixed(0) : '-';
        document.getElementById('pipeline-total-projected-invested').textContent = (totals && totals.totalProjectedInvested && totals.totalProjectedInvested > 0) ? formatBRL(totals.totalProjectedInvested) : '-';
        document.getElementById('pipeline-total-pct').textContent = (totals && totals.totalPct ? totals.totalPct.toFixed(2) : ((weights && weights.length) ? weights.reduce((a,b)=>a+(b||0),0).toFixed(2) : '0.00')) + '%';
        document.getElementById('pipeline-total-target').textContent = '-';
        document.getElementById('pipeline-total-projected').textContent = (totals && totals.totalProjectedBRL && totals.totalProjectedBRL > 0) ? formatBRL(totals.totalProjectedBRL) : (ledgerTotalInvested && ledgerTotalInvested > 0 ? formatBRL(ledgerTotalInvested) : '-');
        // pipeline total gain/loss (difference between target projected BRL and invested used to buy whole shares)
        try { document.getElementById('pipeline-total-gainloss').textContent = (typeof totalGainLoss === 'number' && totalGainLoss !== 0) ? formatBRL(totalGainLoss) : '-'; } catch(e) { /* ignore */ }

        // Latest Price total is not meaningful; keep placeholder below
        try { document.getElementById('pipeline-total-current').textContent = '-'; } catch(e) {}

        return { stocks, weights, totals };

    } catch (error) {
        console.error('Error rendering pipeline section:', error);
        const tbody = document.getElementById('pipeline-tbody');
        if (tbody) tbody.innerHTML = `<tr class="status-error-row"><td colspan="7">Failed to load pipeline composition. ${error.message}</td></tr>`;
        return { stocks: [], weights: [], totals: {} };
    }
}

// --- Comparison chart rendering ---
async function renderComparisonChart(ledgerInfo, pipelineInfo) {
    const compDiv = document.getElementById('composition-comparison');
    if (!compDiv) return;
    compDiv.innerHTML = '';

    const pipelineStocks = pipelineInfo && pipelineInfo.stocks ? pipelineInfo.stocks : [];
    const pipelineVals = (pipelineInfo && pipelineInfo.weights ? pipelineInfo.weights : []).map(v => safeParseFloat(v));

    // Build normalized maps to improve matching
    const pipelineNormMap = {};
    pipelineStocks.forEach((s,i)=>{ pipelineNormMap[normalizeTicker(s)] = { orig: s, val: pipelineVals[i] || 0 }; });

    const ledgerTop = (ledgerInfo && (ledgerInfo.positiveInvested || [])).slice(0, 50); // show up to 50 ledger tickers
    const ledgerLabels = ledgerTop.map(l => l.ticker);
    const ledgerValsPct = ledgerTop.map(l => {
        const total = ledgerInfo.totalInvested || 1;
        return total ? (l.net_invested / total * 100) : 0;
    });

    const ledgerNormMap = {};
    ledgerTop.forEach((l,i)=>{ ledgerNormMap[normalizeTicker(l.ticker)] = { orig: l.ticker, val: ledgerValsPct[i] || 0 }; });

    // union of normalized keys
    const allNormKeys = Array.from(new Set([...Object.keys(pipelineNormMap), ...Object.keys(ledgerNormMap)]));
    // For display, pick original label preference: pipeline orig -> ledger orig -> normalized
    const displayLabels = allNormKeys.map(k => (pipelineNormMap[k] && pipelineNormMap[k].orig) || (ledgerNormMap[k] && ledgerNormMap[k].orig) || k);

    const pipelineY = allNormKeys.map(k => (pipelineNormMap[k] ? pipelineNormMap[k].val : 0));
    const ledgerY = allNormKeys.map(k => (ledgerNormMap[k] ? ledgerNormMap[k].val : 0));

    const traces = [
        { x: displayLabels, y: pipelineY, name: 'Pipeline %', type: 'bar' },
        { x: displayLabels, y: ledgerY, name: 'Ledger % (top tickers)', type: 'bar' }
    ];

    const layout = { title: 'Pipeline (stocks) vs Current Ledger (top tickers) - %', barmode: 'group', height: 420, yaxis: { title: '%' }, margin: { b: 160 } };
    Plotly.newPlot(compDiv, traces, layout, {responsive: true});
}

// CSV split regex used to handle commas inside quoted fields
const CSV_ROW_SPLIT_REGEX = /,(?=(?:(?:[^\"]*\"){2})*[^\"]*$)/;

async function fetchCsvRaw(path) {
    const response = await fetch(path + '?t=' + new Date().getTime());
    if (!response.ok) throw new Error(`Failed to load ${path}. Status: ${response.status}`);
    return await response.text();
}

// Normalize tickers/stock identifiers to improve matching between sources
function normalizeTicker(s) {
    if (!s) return '';
    // Uppercase, remove common extraneous characters and whitespace
    return String(s).toUpperCase().replace(/\s+/g, '').replace(/\./g, '').replace(/\-/g, '').replace(/[^A-Z0-9]/g, '');
}

// --- NEW: load scored_stocks target map (normalized symbol -> target) ---
async function loadScoredTargetMap() {
    const map = {};
    try {
        const scored = await tryFetchCsvFromCandidates(SCORED_STOCKS_CANDIDATES).catch(_=>null);
        if (scored && scored.rows && scored.rows.length) {
            // remember which path succeeded for diagnostics
            try { window.LAST_SCORED_CSV_PATH = scored.path || null; } catch (e) {}
            scored.rows.forEach(r => {
                const stock = r.Stock || r.stock || r.StockSymbol || r.Symbol || r.Ticker || r.stock_symbol || '';
                const tp = safeParseFloat(r.TargetPrice || r.Target_price || r.targetprice || r.target || r.Target);
                if (stock) {
                    const k = normalizeTicker(stock);
                    map[k] = tp;
                    // also add variant without trailing .SA to increase match coverage (e.g., CSMG3 -> CSMG3.SA)
                    try { const noSa = normalizeTicker(String(stock).replace(/\.SA$/i, '')); if (noSa) map[noSa] = tp; } catch(e) {}
                }
            });
        } else {
            try { window.LAST_SCORED_CSV_PATH = null; } catch (e) {}
        }
     } catch (e) {
         console.warn('Failed to load scored_stocks.csv client-side:', e);
     }
     return map;
}

// --- NEW: load scored_stocks symbol map (normalized stock name -> trading symbol)
async function loadScoredSymbolMap() {
    const map = {};
    try {
        const scored = await tryFetchCsvFromCandidates(SCORED_STOCKS_CANDIDATES).catch(_=>null);
        if (scored && scored.rows && scored.rows.length) {
            scored.rows.forEach(r => {
                const stock = r.Stock || r.stock || r.StockSymbol || r.Symbol || r.Ticker || r.stock_symbol || '';
                const name = r.Name || r.name || '';
                // prefer symbol column if present, else try to use Stock field
                const symbol = (r.StockSymbol || r.Symbol || r.Ticker || r.Stock || '').trim();
                if (stock || name) {
                    const key = normalizeTicker(stock || name);
                    if (key) map[key] = symbol || (stock || name);
                }
            });
        }
    } catch (e) {
        console.warn('Failed to load scored_stocks.csv for symbols:', e);
    }
    return map;
}

// --- NEW: load latest Close prices for a list of tickers by scanning StockDataDB.csv from bottom up ---
async function getLatestPricesForList(requestedSymbols) {
    const result = {};
    if (!requestedSymbols || requestedSymbols.length === 0) return result;
    // build normalized lookup
    const requiredNorm = {};
    requestedSymbols.forEach(s => { if (s) requiredNorm[normalizeTicker(s)] = s; });
    const foundNorm = {};
    try {
        // try multiple candidate paths to the findb CSV
        const candidates = ['../data/findb/StockDataDB.csv','/data/findb/StockDataDB.csv','data/findb/StockDataDB.csv'];
        let raw = null;
        for (const p of candidates) {
            try { raw = await fetchCsvRaw(p); break; } catch (e) { continue; }
        }
        if (!raw) return result;
        const lines = raw.split(/\r?\n/).filter(l => l.trim().length > 0);
        if (lines.length < 2) return result;
        // parse header to find indexes for Stock and Close
        const headerLine = lines[0];
        const headerFields = headerLine.split(CSV_ROW_SPLIT_REGEX).map(h => h.replace(/^"|"$/g,'').trim());
        const stockIndex = headerFields.findIndex(h => /^stock$/i.test(h));
        const closeIndex = headerFields.findIndex(h => /^close$/i.test(h));
        if (stockIndex < 0 || closeIndex < 0) return result;
        // scan lines bottom-up to pick latest close per symbol
        for (let i = lines.length - 1; i >= 1; i--) {
            if (Object.keys(foundNorm).length === Object.keys(requiredNorm).length) break;
            const parts = lines[i].split(CSV_ROW_SPLIT_REGEX);
            if (parts.length <= Math.max(stockIndex, closeIndex)) continue;
            let stock = parts[stockIndex] ? parts[stockIndex].replace(/^"|"$/g,'').trim() : '';
            const closeStr = parts[closeIndex] ? parts[closeIndex].replace(/^"|"$/g,'').trim() : '';
            if (!stock) continue;
            const norm = normalizeTicker(stock);
            if (requiredNorm[norm] && !foundNorm[norm]) {
                const val = parseFloat(closeStr.replace(/[^0-9.-]/g, ''));
                if (!isNaN(val)) {
                    result[requiredNorm[norm]] = val;
                    foundNorm[norm] = true;
                }
            }
        }
    } catch (e) {
        console.warn('Failed to load StockDataDB.csv for latest prices:', e);
    }
    return result;
}

async function mainAssets() {
    const ledgerInfo = await renderLedgerSection();
    const cashProceeds = (ledgerInfo && ledgerInfo.totalCurrentMarket) ? ledgerInfo.totalCurrentMarket : (ledgerInfo ? ledgerInfo.totalInvested : 0);
    const pipelineInfo = await renderPipelineSection(cashProceeds);
     // Some renders may return undefined on errors, guard
     if (ledgerInfo && pipelineInfo) {
         await renderComparisonChart(ledgerInfo, pipelineInfo);
     } else {
         const compDiv = document.getElementById('composition-comparison');
         if (compDiv) compDiv.innerHTML = '<tr><td colspan="2">Failed to render comparison chart: check console for errors.</td></tr>';
     }
}

// --- INITIALIZATION: ensure mainAssets runs whether the script loaded before or after DOMContentLoaded ---
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function() { setTimeout(mainAssets, 0); });
} else {
    // already parsed
    setTimeout(mainAssets, 0);
}

// Fix accidental removal of '||' operators (double-space sequences replaced with ' || ')
// This restores expressions like: (a || b || c)
(function(){
    const fs = null; // no-op marker for the editor tool; replacement done inline by the edit tool
})();
