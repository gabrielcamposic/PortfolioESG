(function(){
  const JSON_PATH = 'data/latest_run_summary.json';
  const POLL_INTERVAL = 10000; // ms

  const els = {
    runId: document.getElementById('runId'),
    lastUpdated: document.getElementById('lastUpdated'),
    stocksTableBody: document.querySelector('#stocksTable tbody'),
    pe: document.getElementById('pe'),
    momentum: document.getElementById('momentum'),
    bpe: document.getElementById('bpe'),
    sectorList: document.getElementById('sectorList'),
    lastFetch: document.getElementById('lastFetch'),
    interval: document.getElementById('interval'),
    refreshBtn: document.getElementById('refreshBtn'),
    downloadJson: document.getElementById('downloadJson'),
    tableRunDate: document.getElementById('tableRunDate'),
    // new elements
    kpiSharpe: document.querySelector('#kpi-sharpe .kpi-val'),
    kpiReturn: document.querySelector('#kpi-return .kpi-val'),
    kpiTop5: document.querySelector('#kpi-top5 .kpi-val'),
    kpiVol: document.getElementById('kpi-vol-val'),
    kpiHhi: document.getElementById('kpi-hhi-val'),
    kpiTurnover: document.getElementById('kpi-turnover-val'),
    treemapContainer: document.getElementById('treemap'),
    gaChartCanvas: document.getElementById('gaChart'),
    volChartCanvas: document.getElementById('volChart'),
    correlationMatrix: document.getElementById('correlationMatrix'),
    rangeButtons: document.querySelectorAll('.range-btn'),
    // Diagnostics KPIs (inline with charts)
    kpiSharpeDiag: document.querySelector('#kpi-sharpe-diag .kpi-val'),
    kpiVolDiag: document.querySelector('#kpi-vol-diag .kpi-val'),
    // Valuation section
    diagPortfolioPe: document.getElementById('diag_portfolio_pe')
  };

  // Debug area
  let debugArea = document.getElementById('lrs-debug');
  if(!debugArea){
    const header = document.querySelector('.header');
    debugArea = document.createElement('div');
    debugArea.id='lrs-debug';
    debugArea.style.fontSize='12px';
    debugArea.style.marginTop='8px';
    debugArea.style.color='#ffdede';
    if(header && header.appendChild) header.appendChild(debugArea);
  }
  function setDebug(msg){ debugArea.textContent = msg || ''; }

  // Defensive fallbacks for environments without full DOM (avoid crashing runner)
  if(!els.runId) els.runId = { textContent: '' };
  if(!els.lastUpdated) els.lastUpdated = { textContent: '' };
  if(!els.stocksTableBody) els.stocksTableBody = { innerHTML: '', querySelectorAll: ()=>[], appendChild: ()=>{} };
  // KPI fallbacks
  if(!els.kpiSharpe) els.kpiSharpe = { textContent: '' };
  if(!els.kpiReturn) els.kpiReturn = { textContent: '' };
  if(!els.kpiTop5) els.kpiTop5 = { textContent: '' };
  if(!els.kpiVol) els.kpiVol = { textContent: '' };
  if(!els.kpiHhi) els.kpiHhi = { textContent: '' };
  if(!els.kpiTurnover) els.kpiTurnover = { textContent: '' };
  // Diagnostics KPI fallbacks
  if(!els.kpiSharpeDiag) els.kpiSharpeDiag = { textContent: '' };
  if(!els.kpiVolDiag) els.kpiVolDiag = { textContent: '' };
  if(!els.diagPortfolioPe) els.diagPortfolioPe = { textContent: '' };
  // mini-summary fallbacks (below table)
  if(!els.pe) els.pe = { textContent: '' };
  if(!els.momentum) els.momentum = { textContent: '' };
  if(!els.bpe) els.bpe = { textContent: '' };
  if(!els.tableRunDate) els.tableRunDate = { textContent: '' };

  let lastETag = null; let lastModified = null; let polling = true;
  els.interval.textContent = Math.round(POLL_INTERVAL/1000);

  function formatPct(v){ if(v===null||v===undefined) return '—'; return (Number(v).toFixed(1)) + '%'; }

  function clearTable(){ els.stocksTableBody.innerHTML = ''; }

  // Chart instances
  let portfolioChart = null; let concentrationBarChart = null; let gaChart = null; let volChart = null;
  let compositionChart = null; // for modal
  let compositionHistoryChart = null; // for stacked area chart
  let lastFullData = null; // keep fetched JSON for range slicing
  let portfolioResultsCache = []; // cache of all portfolio results from CSV

  function destroyCharts(){
    [portfolioChart, concentrationBarChart, gaChart, volChart].forEach(c=>{ if(c && c.destroy) try{ c.destroy(); }catch(e){} });
    portfolioChart = concentrationBarChart = gaChart = volChart = null;
  }

  function clearChartCard(id){ const c=document.getElementById(id); if(!c) return; const parent=c.parentElement; if(parent) parent.querySelectorAll('.chart-error').forEach(n=>n.remove()); }
  function showChartError(id,msg){ const c=document.getElementById(id); if(!c) return; const parent=c.parentElement; if(parent){ parent.querySelectorAll('.chart-error').forEach(n=>n.remove()); const d=document.createElement('div'); d.className='chart-error'; d.style.color='#ffbbbb'; d.style.padding='10px'; d.textContent=msg||'Chart unavailable'; parent.appendChild(d);} }

  // Helpers for date range slicing
  function parseDateYMD(s){ return s ? new Date(s + 'T00:00:00') : null; }
  function sliceByRange(timeseries, rangeKey){
    if(!timeseries || !timeseries.length) return timeseries;
    if(rangeKey === 'all') return timeseries;
    const lastDate = parseDateYMD(timeseries[timeseries.length-1].ts);
    const months = { '1m':1, '3m':3, '6m':6, '12m':12 }[rangeKey] || 12;
    const cutoff = new Date(lastDate);
    cutoff.setMonth(cutoff.getMonth() - months);
    return timeseries.filter(d => parseDateYMD(d.ts) >= cutoff);
  }

  // Sanitizes portfolio timeseries:
  // - groups by date (keeps last entry per date),
  // - sorts by date asc,
  // - removes numeric outliers using IQR; fallbacks to relative bounds if needed.
  function sanitizePortfolioTimeseries(raw){
    if(!raw || !raw.length) return raw || [];
    // group by date preserving last occurrence
    const map = new Map();
    for(let i=0;i<raw.length;i++){ const r = raw[i]; if(!r || !r.ts) continue; map.set(r.ts, r); }
    // build array and sort by date
    const arr = Array.from(map.values()).map(r=>({ ts: r.ts, final_value: (r.final_value==null||r.final_value==='')?null: Number(r.final_value) }));
    arr.sort((a,b)=>{ const da = parseDateYMD(a.ts); const db = parseDateYMD(b.ts); return (da && db) ? da - db : 0; });
    // extract numeric values
    const nums = arr.map(x=> (x.final_value==null||isNaN(Number(x.final_value))) ? NaN : Number(x.final_value)).filter(n=>!isNaN(n) && isFinite(n));
    if(!nums.length) return arr;
    // helper quantile
    function quantile(sorted, q){ if(!sorted.length) return NaN; const pos = (sorted.length-1) * q; const base = Math.floor(pos); const rest = pos - base; if(sorted[base+1] !== undefined) return sorted[base] + rest * (sorted[base+1] - sorted[base]); return sorted[base]; }
    const sortedNums = nums.slice().sort((a,b)=>a-b);
    const q1 = quantile(sortedNums, 0.25); const q3 = quantile(sortedNums, 0.75); const iqr = q3 - q1;
    let lower = (isFinite(q1) ? q1 - 1.5*iqr : -Infinity);
    let upper = (isFinite(q3) ? q3 + 1.5*iqr : Infinity);
    // If IQR is zero or too tight, fallback to relative bounds around median
    const median = quantile(sortedNums, 0.5);
    if(!isFinite(lower) || !isFinite(upper) || (upper - lower) < (Math.abs(median)*0.001)){
      lower = median * 0.1; // 10% of median
      upper = median * 10;  // 10x median
    }
    // filter arr by bounds
    const filtered = arr.filter(x=>{ const v = x.final_value; return (v!=null && !isNaN(v) && isFinite(v) && v >= lower && v <= upper); });
    // If filtering removed too many points, relax bounds to original median-based range
    if(filtered.length < Math.max(3, Math.round(arr.length*0.3))){
      const relaxed = arr.filter(x=>{ const v = x.final_value; return (v!=null && !isNaN(v) && isFinite(v) && v >= Math.max(0, median*0.01) && v <= median*100); });
      if(relaxed.length >= 3) return relaxed;
      return arr; // fallback to original grouped data
    }
    return filtered;
  }

  // --- Missing helpers (fallback draw + palette + sparklines) ---
  function generatePalette(n){
    const base = [ '#2b8a3e', '#68b36b', '#a6d4a0', '#f2c057', '#f28c28', '#d9534f', '#6c5ce7', '#00a3e0' ];
    const out = [];
    for(let i=0;i<n;i++) out.push(base[i%base.length]);
    return out;
  }

  function drawLineFallback(canvas, values, color){
    if(!canvas) return;
    const ctx = canvas.getContext('2d');
    const w = canvas.width || canvas.clientWidth; const h = canvas.height || canvas.clientHeight;
    ctx.clearRect(0,0,w,h);
    if(!values || values.length===0){ ctx.fillStyle='rgba(255,255,255,0.03)'; ctx.fillRect(0,0,w,h); return; }
    const nums = values.map(v=>Number(v)||0);
    const min = Math.min(...nums); const max = Math.max(...nums); const range = (max - min) || 1;
    ctx.beginPath();
    nums.forEach((v,i)=>{
      const x = (i/(nums.length-1||1)) * w;
      const y = h - ((v - min)/range) * h;
      if(i===0) ctx.moveTo(x,y); else ctx.lineTo(x,y);
    });
    ctx.strokeStyle = color || '#2b8a3e'; ctx.lineWidth = 1.4; ctx.stroke();
    ctx.lineTo(w,h); ctx.lineTo(0,h); ctx.closePath(); ctx.fillStyle = (color ? color.replace('#','rgba(') : 'rgba(43,138,62,0.06)');
    try{ ctx.fillStyle = 'rgba(43,138,62,0.06)'; ctx.fill(); }catch(e){}
  }

  function drawBarFallback(canvas, labels, values, color){
    if(!canvas) return;
    const ctx = canvas.getContext('2d');
    const w = canvas.width || canvas.clientWidth; const h = canvas.height || canvas.clientHeight; ctx.clearRect(0,0,w,h);
    if(!values || values.length===0) return;
    const nums = values.map(v=>Number(v)||0); const max = Math.max(...nums) || 1;
    const barW = (w / nums.length) * 0.6; const gap = (w - barW*nums.length) / (nums.length+1);
    nums.forEach((val,i)=>{
      const x = gap + i*(barW+gap);
      const barH = (val/max) * (h*0.85);
      ctx.fillStyle = color || '#6c9f58'; ctx.fillRect(x, h - barH, barW, barH);
    });
  }

  function drawDonutFallback(canvas, labels, values, colors){
    if(!canvas) return;
    const ctx = canvas.getContext('2d');
    const w = canvas.width || canvas.clientWidth; const h = canvas.height || canvas.clientHeight; ctx.clearRect(0,0,w,h);
    const nums = values.map(v=>Number(v)||0); const total = nums.reduce((s,n)=>s+n,0) || 1;
    let start = -Math.PI/2; const cx = w/2; const cy = h/2; const r = Math.min(w,h)/2 * 0.8;
    nums.forEach((v,i)=>{
      const angle = (v/total) * Math.PI*2;
      ctx.beginPath(); ctx.moveTo(cx,cy); ctx.fillStyle = (colors && colors[i]) || generatePalette(nums.length)[i%8]; ctx.arc(cx,cy,r,start,start+angle); ctx.closePath(); ctx.fill(); start += angle;
    });
    ctx.globalCompositeOperation = 'destination-out'; ctx.beginPath(); ctx.arc(cx,cy,r*0.55,0,Math.PI*2); ctx.fill(); ctx.globalCompositeOperation = 'source-over';
  }

  function renderSparklines(data){
    const p = data && data.best_portfolio_details ? data.best_portfolio_details : {};
    const sparklines = p.stock_sparklines || {};
    const rows = els.stocksTableBody.querySelectorAll('tr');
    rows.forEach(row=>{
      const ticker = row.getAttribute('data-ticker');
      const canvas = row.querySelector('canvas.spark-canvas');
      const pctEl = row.querySelector('.spark-pct');
      if(!canvas) return;
      const series = sparklines[ticker] || [];
      try{ canvas.getContext('2d').clearRect(0,0,canvas.width,canvas.height); }catch(e){}
      if(!series || series.length===0){ try{ const ctx=canvas.getContext('2d'); ctx.fillStyle='rgba(255,255,255,0.03)'; ctx.fillRect(0,0,canvas.width,canvas.height);}catch(e){}
        if(pctEl) pctEl.textContent = '—';
        return; }
      drawLineFallback(canvas, series, '#2b8a3e');
      // compute pct change from first to last point and display
      if(pctEl){
        const first = Number(series[0]) || 0;
        const last = Number(series[series.length-1]) || 0;
        let pct = null;
        if(first && !isNaN(first)) pct = ((last - first) / Math.abs(first)) * 100;
        pctEl.textContent = pct==null || isNaN(pct) ? '—' : (pct>=0?'+':'') + pct.toFixed(1) + '%';
        pctEl.style.color = (pct==null || isNaN(pct)) ? '' : (pct>=0 ? '#2b8a3e' : '#d9534f');
      }
    });
  }

  // Render KPI tiles
  function renderKPIs(data){
    const p = data.best_portfolio_details || {};
    const cr = p.concentration_risk || {};

    // Main KPIs (top section - 6 cards)
    els.kpiSharpe.textContent = p.sharpe_ratio != null ? Number(p.sharpe_ratio).toFixed(3) : '—';
    els.kpiReturn.textContent = p.expected_return_annual_pct != null ? Number(p.expected_return_annual_pct).toFixed(1)+'%' : '—';
    els.kpiTop5.textContent = cr.top_5_holdings_pct != null ? (Number(cr.top_5_holdings_pct)*100).toFixed(1)+'%' : '—';

    // Volatility
    if(els.kpiVol) {
      els.kpiVol.textContent = p.expected_volatility_annual_pct != null ? Number(p.expected_volatility_annual_pct).toFixed(1)+'%' : '—';
    }
    // HHI
    if(els.kpiHhi) {
      els.kpiHhi.textContent = cr.hhi != null ? Number(cr.hhi).toFixed(4) : '—';
    }

    // === QUALIFICAÇÃO VISUAL DOS KPIs ===

    // Sharpe qualification: <1 ruim, 1-2 bom, >2 excelente
    const sharpeBar = document.getElementById('sharpe-qual-bar');
    const sharpeLabel = document.getElementById('sharpe-qual-label');
    if (sharpeBar && sharpeLabel && p.sharpe_ratio != null) {
      const sharpe = Number(p.sharpe_ratio);
      let pct, color, label, labelClass;
      if (sharpe < 1) {
        pct = Math.min(100, (sharpe / 1) * 33);
        color = '#f44336'; label = 'Baixo'; labelClass = 'qual-bad';
      } else if (sharpe < 2) {
        pct = 33 + ((sharpe - 1) / 1) * 33;
        color = '#FFC107'; label = 'Bom'; labelClass = 'qual-moderate';
      } else {
        pct = 66 + Math.min(34, ((sharpe - 2) / 2) * 34);
        color = '#4CAF50'; label = 'Excelente'; labelClass = 'qual-good';
      }
      sharpeBar.style.width = pct + '%';
      sharpeBar.style.background = color;
      sharpeLabel.textContent = label;
      sharpeLabel.className = 'kpi-qual-label ' + labelClass;
    }

    // HHI qualification: <0.15 diversificado, 0.15-0.25 moderado, >0.25 concentrado
    const hhiBar = document.getElementById('hhi-qual-bar');
    const hhiLabel = document.getElementById('hhi-qual-label');
    if (hhiBar && hhiLabel && cr.hhi != null) {
      const hhi = Number(cr.hhi);
      let pct, color, label, labelClass;
      if (hhi < 0.15) {
        pct = (hhi / 0.15) * 33;
        color = '#4CAF50'; label = 'Diversificado'; labelClass = 'qual-good';
      } else if (hhi < 0.25) {
        pct = 33 + ((hhi - 0.15) / 0.10) * 33;
        color = '#FFC107'; label = 'Moderado'; labelClass = 'qual-moderate';
      } else {
        pct = 66 + Math.min(34, ((hhi - 0.25) / 0.25) * 34);
        color = '#f44336'; label = 'Concentrado'; labelClass = 'qual-bad';
      }
      hhiBar.style.width = pct + '%';
      hhiBar.style.background = color;
      hhiLabel.textContent = label;
      hhiLabel.className = 'kpi-qual-label ' + labelClass;
    }

    // Top 5% qualification: <50% diversificado, 50-80% moderado, >80% concentrado
    const top5Bar = document.getElementById('top5-qual-bar');
    const top5Label = document.getElementById('top5-qual-label');
    if (top5Bar && top5Label && cr.top_5_holdings_pct != null) {
      const top5 = Number(cr.top_5_holdings_pct) * 100;
      let pct, color, label, labelClass;
      if (top5 < 50) {
        pct = (top5 / 50) * 33;
        color = '#4CAF50'; label = 'Diversificado'; labelClass = 'qual-good';
      } else if (top5 < 80) {
        pct = 33 + ((top5 - 50) / 30) * 33;
        color = '#FFC107'; label = 'Moderado'; labelClass = 'qual-moderate';
      } else {
        pct = 66 + Math.min(34, ((top5 - 80) / 20) * 34);
        color = '#f44336'; label = 'Concentrado'; labelClass = 'qual-bad';
      }
      top5Bar.style.width = pct + '%';
      top5Bar.style.background = color;
      top5Label.textContent = label;
      top5Label.className = 'kpi-qual-label ' + labelClass;
    }

    // Diagnostics KPIs (inline with charts in history section)
    els.kpiSharpeDiag.textContent = p.sharpe_ratio != null ? Number(p.sharpe_ratio).toFixed(3) : '—';
    els.kpiVolDiag.textContent = p.expected_volatility_annual_pct != null ? Number(p.expected_volatility_annual_pct).toFixed(1)+'%' : '—';

    // Portfolio P/E in valuation section
    let computed_pwpe = null;
    if(p.portfolio_weighted_pe != null) computed_pwpe = Number(p.portfolio_weighted_pe);
    else if(Array.isArray(p.stocks) && Array.isArray(p.weights) && p.holdings_meta){
      let sum = 0, tw = 0;
      for(let i=0;i<p.stocks.length;i++){ const s=p.stocks[i]; const w=p.weights[i]||0; const meta = p.holdings_meta && p.holdings_meta[s]; const f = meta && meta.forwardPE; if(f!=null && !isNaN(Number(f)) && Number(f)>0){ sum += Number(f)*w; tw += w; } }
      if(tw>0) computed_pwpe = sum / tw;
    }
    if(els.diagPortfolioPe) {
      els.diagPortfolioPe.textContent = (computed_pwpe != null && !isNaN(Number(computed_pwpe))) ? Number(computed_pwpe).toFixed(1) : '—';
    }

    // Momentum in valuation section
    let computed_mom = null;
    if(p.momentum_valuation && p.momentum_valuation.portfolio_momentum != null) computed_mom = Number(p.momentum_valuation.portfolio_momentum);
    else if(Array.isArray(p.stocks) && Array.isArray(p.weights) && p.holdings_meta){
      let sum = 0, tw = 0;
      for(let i=0;i<p.stocks.length;i++){ const s=p.stocks[i]; const w=p.weights[i]||0; const meta = p.holdings_meta && p.holdings_meta[s]; const m = meta && meta.Momentum; if(m!=null && !isNaN(Number(m))){ sum += Number(m)*w; tw += w; } }
      if(tw>0) computed_mom = sum / tw;
    }
    // format momentum with 1 decimal and add arrow indicator
    if(computed_mom != null && !isNaN(Number(computed_mom))){
      const momPctVal = Number(computed_mom*100);
      const momText = (momPctVal>=0?'+':'') + momPctVal.toFixed(1) + '%';
      let arrow = '';
      if(momPctVal > 0) arrow = ' <span class="mom-up">↑</span>';
      else if(momPctVal < 0) arrow = ' <span class="mom-down">↓</span>';
      els.momentum.innerHTML = momText + arrow;
    } else {
      els.momentum.textContent = '—';
    }

    // Benchmark P/E in valuation section
    let computed_bpe = null;
    if(p.momentum_valuation && p.momentum_valuation.benchmark_forward_pe != null) computed_bpe = Number(p.momentum_valuation.benchmark_forward_pe);
    else if(p.holdings_meta){
      const vals = Object.keys(p.holdings_meta).map(k=>p.holdings_meta[k] && p.holdings_meta[k].forwardPE).filter(v=>v!=null && !isNaN(Number(v)) && Number(v)>0).map(Number);
      if(vals.length) computed_bpe = vals.reduce((a,b)=>a+b,0)/vals.length;
    }
    els.bpe.textContent = (computed_bpe != null && !isNaN(Number(computed_bpe))) ? Number(computed_bpe).toFixed(1) : '—';

    // === P/E COMPARISON VISUAL ===
    const peCompareLabel = document.getElementById('pe-compare-label');
    const pePortBar = document.getElementById('pe-compare-portfolio-bar');
    const peBenchBar = document.getElementById('pe-compare-benchmark-bar');
    if (peCompareLabel && pePortBar && peBenchBar && computed_pwpe != null && computed_bpe != null) {
      const total = computed_pwpe + computed_bpe;
      const portPct = (computed_pwpe / total) * 100;
      const benchPct = (computed_bpe / total) * 100;
      pePortBar.style.width = portPct + '%';
      peBenchBar.style.width = benchPct + '%';

      // Label: show if portfolio is cheaper or more expensive
      const diff = ((computed_pwpe - computed_bpe) / computed_bpe) * 100;
      if (diff < -5) {
        peCompareLabel.textContent = Math.abs(diff).toFixed(0) + '% mais barato';
        peCompareLabel.style.color = '#4CAF50';
      } else if (diff > 5) {
        peCompareLabel.textContent = diff.toFixed(0) + '% mais caro';
        peCompareLabel.style.color = '#f44336';
      } else {
        peCompareLabel.textContent = 'Similar';
        peCompareLabel.style.color = '#FFC107';
      }
    }
  }

  // render treemap using simple flex tiles
  let sectorExposureChartInstance = null;

  async function renderTreemap(data){
    const list = data.best_portfolio_details && data.best_portfolio_details.sector_exposure_list ? data.best_portfolio_details.sector_exposure_list : [];
    const container = els.treemapContainer;
    if(container) container.innerHTML='';

    // Load sector P/E data
    let sectorPEData = new Map();
    try {
      const res = await fetch('./data/sector_pe.csv?_=' + Date.now());
      if (res.ok) {
        const text = await res.text();
        const lines = text.trim().split('\n');
        if (lines.length >= 2) {
          const headers = lines[0].split(',');
          const sectorIdx = headers.findIndex(h => h.toLowerCase().includes('sector'));
          const peIdx = headers.findIndex(h => h.toLowerCase().includes('sectormedianpe') || h.toLowerCase().includes('pe'));
          const runIdIdx = headers.findIndex(h => h.toLowerCase().includes('run_id'));
          const timestampIdx = headers.findIndex(h => h.toLowerCase().includes('timestamp'));

          if (sectorIdx !== -1 && peIdx !== -1) {
            // Group by run_id to get the latest run
            const runMap = new Map();
            for (let i = 1; i < lines.length; i++) {
              const cols = lines[i].split(',');
              if (cols.length > Math.max(sectorIdx, peIdx, runIdIdx)) {
                const runId = cols[runIdIdx]?.trim() || '';
                const timestamp = cols[timestampIdx]?.trim() || '';
                const sector = cols[sectorIdx]?.trim();
                const pe = parseFloat(cols[peIdx]);
                if (sector && !isNaN(pe) && runId) {
                  if (!runMap.has(runId)) {
                    runMap.set(runId, { timestamp, data: [] });
                  }
                  runMap.get(runId).data.push({ sector, pe });
                }
              }
            }

            // Find the latest run by timestamp
            let latestRunId = null;
            let latestTimestamp = '';
            for (const [runId, info] of runMap.entries()) {
              if (info.timestamp > latestTimestamp) {
                latestTimestamp = info.timestamp;
                latestRunId = runId;
              }
            }

            const latestData = runMap.get(latestRunId)?.data || [];
            latestData.forEach(d => sectorPEData.set(d.sector, d.pe));
          }
        }
      }
    } catch(e) {
      console.warn('Failed to load sector P/E data:', e);
    }

    if(!list || !list.length){
      const canvas = document.getElementById('sectorExposureChart');
      if(canvas) {
        const ctx = canvas.getContext('2d');
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.fillStyle = '#888';
        ctx.font = '14px sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText('No sector data', canvas.width/2, canvas.height/2);
      }
      return;
    }

    // Sort by exposure descending
    const sortedList = [...list].sort((a, b) => (Number(b.pct) || 0) - (Number(a.pct) || 0));

    // Prepare data for combined chart
    const labels = sortedList.map(s => s.sector);
    const exposures = sortedList.map(s => (Number(s.pct) || 0) * 100);
    const pes = sortedList.map(s => sectorPEData.get(s.sector) || null);

    renderSectorExposureChart(labels, exposures, pes);
  }

  function renderSectorExposureChart(labels, exposures, pes) {
    const canvas = document.getElementById('sectorExposureChart');
    if (!canvas) return;

    if (sectorExposureChartInstance) {
      try { sectorExposureChartInstance.destroy(); } catch(e) {}
    }

    const palette = generatePalette(labels.length);
    const avgPE = pes.filter(p => p != null).reduce((a, b) => a + b, 0) / pes.filter(p => p != null).length || 0;

    // Create datasets
    const datasets = [
      {
        label: 'Exposição (%)',
        data: exposures,
        backgroundColor: palette.map(c => c.replace(')', ', 0.8)').replace('rgb', 'rgba')),
        borderColor: palette,
        borderWidth: 1,
        borderRadius: 4,
        yAxisID: 'y',
        order: 2
      }
    ];

    // Add P/E line if data exists
    if (pes.some(p => p != null)) {
      datasets.push({
        label: 'Forward P/E',
        data: pes,
        type: 'line',
        borderColor: '#f28c28',
        backgroundColor: '#f28c28',
        pointBackgroundColor: pes.map(p => p != null ? (p > avgPE ? '#e76f51' : '#5bd2a3') : 'transparent'),
        pointBorderColor: pes.map(p => p != null ? (p > avgPE ? '#e76f51' : '#5bd2a3') : 'transparent'),
        pointRadius: 6,
        pointHoverRadius: 8,
        borderWidth: 2,
        fill: false,
        tension: 0.1,
        yAxisID: 'y1',
        order: 1
      });
    }

    sectorExposureChartInstance = new Chart(canvas, {
      type: 'bar',
      data: {
        labels: labels,
        datasets: datasets
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
            position: 'top',
            labels: { color: '#ccc', usePointStyle: true, padding: 15 }
          },
          tooltip: {
            backgroundColor: 'rgba(30, 41, 59, 0.95)',
            titleColor: '#f1f5f9',
            bodyColor: '#cbd5e1',
            borderColor: '#475569',
            borderWidth: 1,
            padding: 12,
            callbacks: {
              label: function(ctx) {
                if (ctx.dataset.label === 'Exposição (%)') {
                  return `Exposição: ${ctx.raw.toFixed(1)}%`;
                } else if (ctx.dataset.label === 'Forward P/E') {
                  if (ctx.raw == null) return 'P/E: N/A';
                  const indicator = ctx.raw > avgPE ? '↑' : '↓';
                  return `P/E: ${ctx.raw.toFixed(1)} ${indicator}`;
                }
                return ctx.formattedValue;
              }
            }
          }
        },
        scales: {
          x: {
            grid: { display: false },
            ticks: {
              color: '#ccc',
              font: { size: 11 },
              maxRotation: 45,
              minRotation: 45
            }
          },
          y: {
            type: 'linear',
            position: 'left',
            beginAtZero: true,
            grid: { color: 'rgba(255,255,255,0.05)' },
            ticks: { color: '#aaa' },
            title: {
              display: true,
              text: 'Exposição (%)',
              color: '#aaa'
            }
          },
          y1: {
            type: 'linear',
            position: 'right',
            beginAtZero: false,
            grid: { display: false },
            ticks: { color: '#f28c28' },
            title: {
              display: true,
              text: 'Forward P/E',
              color: '#f28c28'
            }
          }
        }
      }
    });
  }

  // Render GA fitness history (diagnostics) - now shows best Sharpe from each run over time
  // Loads data from portfolio_results_db.csv which contains history of all runs
  async function renderGA(data){
    const canvas = els.gaChartCanvas || document.getElementById('gaChart');
    try{ if(gaChart && gaChart.destroy) gaChart.destroy(); }catch(e){}
    if(!canvas) return;
    // clear any previous error messages
    if(canvas.parentElement) canvas.parentElement.querySelectorAll('.chart-error').forEach(n=>n.remove());

    // Try to load historical data from CSV
    let historicalData = [];
    try {
      const csvResp = await fetch('data/portfolio_results_db.csv?_=' + Date.now(), {cache:'no-store'});
      if(csvResp.ok){
        const csvText = await csvResp.text();
        const lines = csvText.trim().split('\n');
        if(lines.length > 0){
          // Check if first line is a header (contains column names)
          const firstLine = lines[0];
          const hasHeader = firstLine.toLowerCase().includes('run_id') && firstLine.toLowerCase().includes('timestamp');

          let runIdIdx = 0, timestampIdx = 1, sharpeIdx = 7;
          let startLine = 0;

          if(hasHeader){
            const header = firstLine.split(',');
            runIdIdx = header.findIndex(h => h.trim().toLowerCase() === 'run_id');
            timestampIdx = header.findIndex(h => h.trim().toLowerCase() === 'timestamp');
            sharpeIdx = header.findIndex(h => h.trim().toLowerCase() === 'sharpe_ratio');
            if(runIdIdx === -1) runIdIdx = 0;
            if(timestampIdx === -1) timestampIdx = 1;
            if(sharpeIdx === -1) sharpeIdx = 7;
            startLine = 1;
          }

          for(let i=startLine; i<lines.length; i++){
            // Parse CSV line carefully (handle quoted fields with commas)
            const row = parseCSVLine(lines[i]);
            if(row.length > Math.max(runIdIdx, timestampIdx, sharpeIdx)){
              const runId = row[runIdIdx] || '';
              const timestamp = row[timestampIdx] || '';
              const sharpe = parseFloat(row[sharpeIdx]);
              if(!isNaN(sharpe) && timestamp){
                historicalData.push({
                  run_id: runId,
                  timestamp: timestamp,
                  sharpe: sharpe
                });
              }
            }
          }
        }
      }
    } catch(e) {
      console.warn('Failed to load GA history from CSV', e);
    }

    // Sort by timestamp
    historicalData.sort((a,b) => new Date(a.timestamp) - new Date(b.timestamp));

    if(!historicalData.length){
      try{ const ctx=canvas.getContext('2d'); ctx.clearRect(0,0,canvas.width,canvas.height); }catch(e){};
      showChartError('gaChart', 'No historical run data available');
      return;
    }

    // Prepare data for chart
    const labels = historicalData.map(d => {
      try {
        const date = new Date(d.timestamp);
        return date.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' });
      } catch(e) { return d.timestamp.substring(0,10); }
    });
    const values = historicalData.map(d => d.sharpe);
    const runIds = historicalData.map(d => d.run_id);
    const originalDates = historicalData.map(d => d.timestamp);

    // ensure canvas has correct pixel size
    try{ canvas.width = canvas.clientWidth; canvas.height = canvas.clientHeight; }catch(e){}

    if(typeof window.Chart === 'undefined'){
      drawLineFallback(canvas, values, '#f2c057');
      return;
    }

    const ctx = canvas.getContext('2d');
    try{
      if(typeof Chart !== 'undefined' && Chart.getChart){
        const existing = Chart.getChart(canvas);
        if(existing){
          try{
            existing.data.labels = labels;
            if(existing.data.datasets && existing.data.datasets[0]){
              existing.data.datasets[0].data = values;
              existing.data.datasets[0].runIds = runIds;
              existing.data.datasets[0].originalDates = originalDates;
            }
            existing.update();
            gaChart = existing;
            return;
          }catch(e){ console.warn('Failed to update existing GA chart, will recreate', e); try{ existing.destroy(); }catch(e){} }
        }
      }
    }catch(e){ console.warn('Safe GA chart check failed', e); }

    gaChart = new Chart(ctx, {
      type: 'line',
      data: {
        labels: labels,
        datasets: [{
          label: 'Sharpe Ratio',
          data: values,
          borderColor:'#f2c057',
          backgroundColor:'rgba(242,192,87,0.12)',
          pointRadius: 3,
          pointHoverRadius: 6,
          fill:true,
          runIds: runIds,
          originalDates: originalDates
        }]
      },
      options: {
        responsive:true,
        maintainAspectRatio:false,
        interaction: {
          intersect: false,
          mode: 'index'
        },
        plugins:{
          legend:{display:false},
          tooltip: {
            enabled: true,
            backgroundColor: 'rgba(30, 41, 59, 0.95)',
            titleColor: '#f1f5f9',
            bodyColor: '#cbd5e1',
            borderColor: '#475569',
            borderWidth: 1,
            padding: 12,
            callbacks: {
              title: function(context) {
                const idx = context[0].dataIndex;
                const originalDate = context[0].dataset.originalDates?.[idx] || context[0].label;
                try {
                  const d = new Date(originalDate);
                  return 'Data: ' + d.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
                } catch(e) { return 'Data: ' + originalDate; }
              },
              label: function(context) {
                const value = context.parsed.y;
                return 'Sharpe: ' + value.toFixed(4);
              },
              afterLabel: function(context) {
                const idx = context.dataIndex;
                const runId = context.dataset.runIds?.[idx] || 'N/A';
                return 'Run ID: ' + runId;
              }
            }
          }
        },
        scales:{
          x:{
            display:true,
            grid: { color: 'rgba(71,85,105,0.3)' },
            ticks: {
              color: '#94a3b8',
              maxRotation: 0,
              autoSkip: true,
              maxTicksLimit: 8,
              font: { size: 10 }
            },
            title:{display:true, text:'Data da Simulação', color:'#cbd5e1'}
          },
          y:{
            display:true,
            grid: { color: 'rgba(71,85,105,0.3)' },
            ticks: { color: '#94a3b8' },
            title:{display:true, text:'Best Sharpe Ratio', color:'#cbd5e1'}
          }
        }
      }
    });
  }

  // Helper function to parse CSV line handling quoted fields
  function parseCSVLine(line){
    const result = [];
    let current = '';
    let inQuotes = false;
    for(let i=0; i<line.length; i++){
      const ch = line[i];
      if(ch === '"'){
        inQuotes = !inQuotes;
      } else if(ch === ',' && !inQuotes){
        result.push(current.trim());
        current = '';
      } else {
        current += ch;
      }
    }
    result.push(current.trim());
    return result;
  }

  // Load all portfolio results from CSV and cache them
  async function loadPortfolioResultsCache(){
    if(portfolioResultsCache.length > 0) return portfolioResultsCache;
    try {
      const csvResp = await fetch('data/portfolio_results_db.csv?_=' + Date.now(), {cache:'no-store'});
      if(!csvResp.ok) return [];
      const csvText = await csvResp.text();
      const lines = csvText.trim().split('\n');
      if(lines.length < 2) return [];

      const header = parseCSVLine(lines[0]);
      const indices = {
        run_id: header.findIndex(h => h.toLowerCase() === 'run_id'),
        timestamp: header.findIndex(h => h.toLowerCase() === 'timestamp'),
        stocks: header.findIndex(h => h.toLowerCase() === 'stocks'),
        weights: header.findIndex(h => h.toLowerCase() === 'weights'),
        sharpe_ratio: header.findIndex(h => h.toLowerCase() === 'sharpe_ratio'),
        expected_return_annual_pct: header.findIndex(h => h.toLowerCase() === 'expected_return_annual_pct'),
        expected_volatility_annual_pct: header.findIndex(h => h.toLowerCase() === 'expected_volatility_annual_pct')
      };

      for(let i=1; i<lines.length; i++){
        const row = parseCSVLine(lines[i]);
        const entry = {
          run_id: row[indices.run_id] || '',
          timestamp: row[indices.timestamp] || '',
          stocks: (row[indices.stocks] || '').split(',').map(s => s.trim()).filter(s => s),
          weights: (row[indices.weights] || '').split(',').map(w => parseFloat(w.trim()) || 0),
          sharpe_ratio: parseFloat(row[indices.sharpe_ratio]) || 0,
          annual_return: parseFloat(row[indices.expected_return_annual_pct]) || 0,
          volatility: parseFloat(row[indices.expected_volatility_annual_pct]) || 0
        };
        if(entry.run_id && entry.stocks.length > 0){
          portfolioResultsCache.push(entry);
        }
      }
    } catch(e) {
      console.warn('Failed to load portfolio results cache', e);
    }
    return portfolioResultsCache;
  }

  // Show modal with portfolio composition for a specific run
  function showCompositionModal(runId){
    const entry = portfolioResultsCache.find(e => e.run_id === runId);
    if(!entry){
      console.warn('No portfolio data found for run_id:', runId);
      return;
    }

    const modal = document.getElementById('compositionModal');
    if(!modal) return;

    // Populate modal data
    document.getElementById('modalRunId').textContent = entry.run_id;
    document.getElementById('modalDate').textContent = entry.timestamp;
    document.getElementById('modalReturn').textContent = entry.annual_return.toFixed(2) + '%';
    document.getElementById('modalSharpe').textContent = entry.sharpe_ratio.toFixed(4);

    // Build composition list
    const listEl = document.getElementById('compositionList');
    listEl.innerHTML = '';
    const maxWeight = Math.max(...entry.weights, 0.01);

    for(let i=0; i<entry.stocks.length; i++){
      const stock = entry.stocks[i];
      const weight = entry.weights[i] || 0;
      const pct = (weight * 100).toFixed(1);
      const barWidth = (weight / maxWeight) * 100;

      const item = document.createElement('div');
      item.className = 'composition-item';
      item.innerHTML = `
        <span class="stock-name">${stock}</span>
        <div class="weight-bar-container">
          <div class="weight-bar-fill" style="width: ${barWidth}%"></div>
        </div>
        <span class="weight-value">${pct}%</span>
      `;
      listEl.appendChild(item);
    }

    // Render pie chart
    const chartCanvas = document.getElementById('compositionChart');
    if(chartCanvas && typeof Chart !== 'undefined'){
      try{ if(compositionChart && compositionChart.destroy) compositionChart.destroy(); }catch(e){}
      const ctx = chartCanvas.getContext('2d');
      compositionChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
          labels: entry.stocks,
          datasets: [{
            data: entry.weights.map(w => w * 100),
            backgroundColor: generatePalette(entry.stocks.length),
            borderWidth: 1,
            borderColor: 'rgba(0,0,0,0.2)'
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: {
              display: true,
              position: 'right',
              labels: { color: '#cbd5e1', font: { size: 11 } }
            },
            tooltip: {
              callbacks: {
                label: function(context) {
                  return context.label + ': ' + context.parsed.toFixed(1) + '%';
                }
              }
            }
          }
        }
      });
    }

    // Show modal
    modal.style.display = 'flex';
  }

  // Close modal
  function closeCompositionModal(){
    const modal = document.getElementById('compositionModal');
    if(modal) modal.style.display = 'none';
  }

  // Initialize modal event listeners
  (function initModalListeners(){
    const closeBtn = document.getElementById('closeModal');
    if(closeBtn) closeBtn.addEventListener('click', closeCompositionModal);

    const modal = document.getElementById('compositionModal');
    if(modal){
      modal.addEventListener('click', function(e){
        if(e.target === modal) closeCompositionModal();
      });
    }

    document.addEventListener('keydown', function(e){
      if(e.key === 'Escape') closeCompositionModal();
    });
  })();

  // Render composition history as stacked area chart
  async function renderCompositionHistoryChart(rangeKey){
    const canvas = document.getElementById('compositionHistoryChart');
    const legendContainer = document.getElementById('compositionLegend');
    if(!canvas) return;

    try{ if(compositionHistoryChart && compositionHistoryChart.destroy) compositionHistoryChart.destroy(); }catch(e){}

    // Ensure cache is loaded
    if(portfolioResultsCache.length === 0){
      await loadPortfolioResultsCache();
    }

    if(portfolioResultsCache.length === 0){
      if(legendContainer) legendContainer.innerHTML = '<span style="color:var(--muted);font-size:12px;">No historical data available</span>';
      return;
    }

    // Sort by timestamp
    let sortedData = [...portfolioResultsCache].sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));

    // Apply range filter if specified
    if(rangeKey && rangeKey !== 'all'){
      sortedData = sliceByRange(sortedData.map(d => ({...d, ts: d.timestamp.split(' ')[0]})), rangeKey);
    }

    // Collect all unique stocks across all runs
    const allStocks = new Set();
    sortedData.forEach(entry => {
      entry.stocks.forEach(s => allStocks.add(s));
    });
    const stockList = Array.from(allStocks).sort();

    // Build datasets - one per stock
    const datasets = [];
    const colors = generateExtendedPalette(stockList.length);

    stockList.forEach((stock, idx) => {
      const data = sortedData.map(entry => {
        const stockIdx = entry.stocks.indexOf(stock);
        if(stockIdx === -1) return 0;
        return (entry.weights[stockIdx] || 0) * 100; // convert to percentage
      });

      datasets.push({
        label: stock,
        data: data,
        backgroundColor: colors[idx],
        borderColor: colors[idx],
        borderWidth: 1,
        fill: true,
        pointRadius: 2,
        pointHoverRadius: 5,
        tension: 0.3
      });
    });

    // Labels (dates) - same format as portfolio chart for alignment
    const labels = sortedData.map(entry => {
      try {
        const d = new Date(entry.timestamp);
        return d.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit', year: '2-digit' });
      } catch(e) { return entry.timestamp.substring(0, 10); }
    });

    // Store run_ids for click handler
    const runIds = sortedData.map(entry => entry.run_id);

    // Ensure canvas has correct size
    try{ canvas.width = canvas.clientWidth; canvas.height = canvas.clientHeight; }catch(e){}

    if(typeof window.Chart === 'undefined'){
      if(legendContainer) legendContainer.innerHTML = '<span style="color:var(--muted);">Chart.js not loaded</span>';
      return;
    }

    const ctx = canvas.getContext('2d');

    compositionHistoryChart = new Chart(ctx, {
      type: 'line',
      data: {
        labels: labels,
        datasets: datasets
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: {
          mode: 'index',
          intersect: false
        },
        onClick: function(event, elements, chart) {
          if(elements.length > 0){
            const idx = elements[0].index;
            const runId = runIds[idx];
            if(runId){
              showCompositionModal(runId);
            }
          }
        },
        plugins: {
          legend: {
            display: false // We'll use custom legend
          },
          tooltip: {
            enabled: true,
            backgroundColor: 'rgba(30, 41, 59, 0.95)',
            titleColor: '#f1f5f9',
            bodyColor: '#cbd5e1',
            borderColor: '#475569',
            borderWidth: 1,
            padding: 12,
            callbacks: {
              title: function(context) {
                const idx = context[0].dataIndex;
                const entry = sortedData[idx];
                try {
                  const d = new Date(entry.timestamp);
                  return 'Data: ' + d.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit', year: 'numeric' });
                } catch(e) { return entry.timestamp; }
              },
              label: function(context) {
                const value = context.parsed.y;
                if(value === 0) return null; // Don't show stocks with 0%
                return context.dataset.label + ': ' + value.toFixed(1) + '%';
              },
              afterBody: function(context) {
                const idx = context[0].dataIndex;
                return '\nRun ID: ' + runIds[idx] + '\n(clique para detalhes)';
              }
            },
            filter: function(tooltipItem) {
              return tooltipItem.parsed.y > 0;
            }
          }
        },
        scales: {
          x: {
            display: false, // Hide x-axis since it's synchronized with the charts above
            grid: { display: false }
          },
          y: {
            display: true,
            stacked: true,
            min: 0,
            max: 100,
            grid: { color: 'rgba(71,85,105,0.3)' },
            ticks: {
              color: '#94a3b8',
              callback: function(val) { return val + '%'; }
            },
            title: { display: true, text: 'Peso no Portfolio (%)', color: '#cbd5e1' }
          }
        }
      }
    });

    // Render custom legend with toggle functionality
    if(legendContainer){
      legendContainer.innerHTML = '';
      stockList.forEach((stock, idx) => {
        const item = document.createElement('div');
        item.className = 'legend-item';
        item.innerHTML = `
          <span class="legend-color" style="background:${colors[idx]}"></span>
          <span class="legend-label">${stock}</span>
        `;
        item.addEventListener('click', function(){
          const datasetIndex = idx;
          const meta = compositionHistoryChart.getDatasetMeta(datasetIndex);
          meta.hidden = !meta.hidden;
          item.classList.toggle('hidden', meta.hidden);
          compositionHistoryChart.update();
        });
        legendContainer.appendChild(item);
      });
    }
  }

  // Extended color palette for many stocks
  function generateExtendedPalette(n){
    const base = [
      'rgba(43, 138, 62, 0.7)',   // green
      'rgba(79, 195, 247, 0.7)',  // light blue
      'rgba(242, 192, 87, 0.7)',  // yellow
      'rgba(217, 83, 79, 0.7)',   // red
      'rgba(108, 92, 231, 0.7)',  // purple
      'rgba(0, 163, 224, 0.7)',   // cyan
      'rgba(255, 152, 0, 0.7)',   // orange
      'rgba(156, 39, 176, 0.7)',  // deep purple
      'rgba(0, 150, 136, 0.7)',   // teal
      'rgba(233, 30, 99, 0.7)',   // pink
      'rgba(103, 58, 183, 0.7)',  // indigo
      'rgba(139, 195, 74, 0.7)',  // light green
      'rgba(255, 87, 34, 0.7)',   // deep orange
      'rgba(63, 81, 181, 0.7)',   // blue
      'rgba(205, 220, 57, 0.7)',  // lime
      'rgba(121, 85, 72, 0.7)',   // brown
      'rgba(96, 125, 139, 0.7)',  // blue grey
      'rgba(255, 193, 7, 0.7)',   // amber
      'rgba(76, 175, 80, 0.7)',   // green 2
      'rgba(33, 150, 243, 0.7)',  // blue 2
    ];
    const out = [];
    for(let i = 0; i < n; i++){
      out.push(base[i % base.length]);
    }
    return out;
  }

  // Render Volatility history chart (diagnostics)
  async function renderVolatilityChart(data){
    const canvas = els.volChartCanvas || document.getElementById('volChart');
    try{ if(volChart && volChart.destroy) volChart.destroy(); }catch(e){}
    if(!canvas) return;
    // clear any previous error messages
    if(canvas.parentElement) canvas.parentElement.querySelectorAll('.chart-error').forEach(n=>n.remove());

    // Try to load historical data from CSV
    let historicalData = [];
    try {
      const csvResp = await fetch('data/portfolio_results_db.csv?_=' + Date.now(), {cache:'no-store'});
      if(csvResp.ok){
        const csvText = await csvResp.text();
        const lines = csvText.trim().split('\n');
        if(lines.length > 0){
          // Check if first line is a header (contains column names)
          const firstLine = lines[0];
          const hasHeader = firstLine.toLowerCase().includes('run_id') && firstLine.toLowerCase().includes('timestamp');

          let runIdIdx = 0, timestampIdx = 1;
          // Header may have 12 columns (old format with final_value, roi_percent) or 10 columns (new format)
          // We need to detect per-row which format is being used
          let volIdxFromHeader = -1;
          let headerHasFinalValue = false;
          let startLine = 0;

          if(hasHeader){
            const header = firstLine.split(',');
            runIdIdx = header.findIndex(h => h.trim().toLowerCase() === 'run_id');
            timestampIdx = header.findIndex(h => h.trim().toLowerCase() === 'timestamp');
            volIdxFromHeader = header.findIndex(h => h.trim().toLowerCase() === 'expected_volatility_annual_pct');
            headerHasFinalValue = header.some(h => h.trim().toLowerCase() === 'final_value');
            if(runIdIdx === -1) runIdIdx = 0;
            if(timestampIdx === -1) timestampIdx = 1;
            startLine = 1;
          }

          for(let i=startLine; i<lines.length; i++){
            const row = parseCSVLine(lines[i]);
            if(row.length < 10) continue; // Need at least 10 columns

            const runId = row[runIdIdx] || '';
            const timestamp = row[timestampIdx] || '';

            // Determine volatility index based on row length
            // Old format (12+ cols with final_value, roi_percent): volatility at index 11
            // New format (10 cols without final_value, roi_percent): volatility at last column (index 9)
            let volIdx;
            if(headerHasFinalValue && row.length >= 12){
              // Old format: use header index
              volIdx = volIdxFromHeader !== -1 ? volIdxFromHeader : 11;
            } else {
              // New format: volatility is last column
              volIdx = row.length - 1;
            }

            const vol = parseFloat(row[volIdx]);
            if(!isNaN(vol) && timestamp && vol > 0 && vol < 100){
              historicalData.push({
                run_id: runId,
                timestamp: timestamp,
                volatility: vol
              });
            }
          }
        }
      }
    } catch(e) {
      console.warn('Failed to load volatility history from CSV', e);
    }

    // Sort by timestamp
    historicalData.sort((a,b) => new Date(a.timestamp) - new Date(b.timestamp));

    if(!historicalData.length){
      try{ const ctx=canvas.getContext('2d'); ctx.clearRect(0,0,canvas.width,canvas.height); }catch(e){};
      showChartError('volChart', 'No historical data available');
      return;
    }

    // Prepare data for chart
    const labels = historicalData.map(d => {
      try {
        const date = new Date(d.timestamp);
        return date.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' });
      } catch(e) { return d.timestamp.substring(0,10); }
    });
    const values = historicalData.map(d => d.volatility);
    const runIds = historicalData.map(d => d.run_id);
    const originalDates = historicalData.map(d => d.timestamp);

    // ensure canvas has correct pixel size
    try{ canvas.width = canvas.clientWidth; canvas.height = canvas.clientHeight; }catch(e){}

    if(typeof window.Chart === 'undefined'){
      drawLineFallback(canvas, values, '#d9534f');
      return;
    }

    const ctx = canvas.getContext('2d');
    try{
      if(typeof Chart !== 'undefined' && Chart.getChart){
        const existing = Chart.getChart(canvas);
        if(existing){
          try{
            existing.data.labels = labels;
            if(existing.data.datasets && existing.data.datasets[0]){
              existing.data.datasets[0].data = values;
              existing.data.datasets[0].runIds = runIds;
              existing.data.datasets[0].originalDates = originalDates;
            }
            existing.update();
            volChart = existing;
            return;
          }catch(e){ console.warn('Failed to update existing vol chart, will recreate', e); try{ existing.destroy(); }catch(e){} }
        }
      }
    }catch(e){ console.warn('Safe vol chart check failed', e); }

    volChart = new Chart(ctx, {
      type: 'line',
      data: {
        labels: labels,
        datasets: [{
          label: 'Volatilidade (%)',
          data: values,
          borderColor:'#d9534f',
          backgroundColor:'rgba(217,83,79,0.12)',
          pointRadius: 3,
          pointHoverRadius: 6,
          fill:true,
          runIds: runIds,
          originalDates: originalDates
        }]
      },
      options: {
        responsive:true,
        maintainAspectRatio:false,
        interaction: {
          intersect: false,
          mode: 'index'
        },
        plugins:{
          legend:{display:false},
          tooltip: {
            enabled: true,
            backgroundColor: 'rgba(30, 41, 59, 0.95)',
            titleColor: '#f1f5f9',
            bodyColor: '#cbd5e1',
            borderColor: '#475569',
            borderWidth: 1,
            padding: 12,
            callbacks: {
              title: function(context) {
                const idx = context[0].dataIndex;
                const originalDate = context[0].dataset.originalDates?.[idx] || context[0].label;
                try {
                  const d = new Date(originalDate);
                  return 'Data: ' + d.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
                } catch(e) { return 'Data: ' + originalDate; }
              },
              label: function(context) {
                const value = context.parsed.y;
                return 'Volatilidade: ' + value.toFixed(2) + '%';
              },
              afterLabel: function(context) {
                const idx = context.dataIndex;
                const runId = context.dataset.runIds?.[idx] || 'N/A';
                return 'Run ID: ' + runId;
              }
            }
          }
        },
        scales:{
          x:{
            display:true,
            grid: { color: 'rgba(71,85,105,0.3)' },
            ticks: {
              color: '#94a3b8',
              maxRotation: 0,
              autoSkip: true,
              maxTicksLimit: 8,
              font: { size: 10 }
            },
            title:{display:true, text:'Data da Simulação', color:'#cbd5e1'}
          },
          y:{
            display:true,
            grid: { color: 'rgba(71,85,105,0.3)' },
            ticks: {
              color: '#94a3b8',
              callback: function(value) { return value.toFixed(1) + '%'; }
            },
            title:{display:true, text:'Volatilidade Anual (%)', color:'#cbd5e1'}
          }
        }
      }
    });
  }

  // Render sector donut and concentration bar (used by renderAll)
  function renderSectorAndConcentration(data){
    const p = data.best_portfolio_details || {};
    // Concentration bar (top 5 holdings)
    const concCanvas = document.getElementById('concentrationBar');
    try{ if(concentrationBarChart && concentrationBarChart.destroy) concentrationBarChart.destroy(); }catch(e){}
    const top5 = (p.concentration_risk && p.concentration_risk.top_5_holdings) || [];
    if(!top5 || top5.length === 0){
      if(concCanvas && concCanvas.parentElement) concCanvas.parentElement.querySelectorAll('.chart-error').forEach(n=>n.remove());
      if(concCanvas && concCanvas.parentElement){ const d=document.createElement('div'); d.className='chart-error'; d.style.color='#ffbbbb'; d.style.padding='10px'; d.textContent='No concentration data'; concCanvas.parentElement.appendChild(d);}
    } else {
      // NOTE: we intentionally skip rendering the column/bar chart here because the table now
      // includes inline weight bars for each holding (formatting-conditional style). This avoids
      // duplicating the same information. If you want to re-enable the chart, uncomment the
      // block below.
      if(concCanvas && concCanvas.parentElement){
        // show a small hint that the column chart is intentionally hidden
        concCanvas.parentElement.querySelectorAll('.chart-error').forEach(n=>n.remove());
        const note = document.createElement('div'); note.className='chart-note'; note.style.color='#9fb0bb'; note.style.padding='8px'; note.textContent='Column chart hidden — weights shown in table as bars.'; concCanvas.parentElement.appendChild(note);
      }
      /*
      const labels = top5.map(h=>h.stock || h[0] || '');
      const values = top5.map(h=>{ const w = (h.weight!=null ? h.weight : (h[1]!=null ? h[1] : 0)); return Number(w*100); });
      if(typeof window.Chart === 'undefined'){
        drawBarFallback(concCanvas, labels, values, '#6c9f58');
      } else {
        const ctx = concCanvas.getContext('2d');
        concentrationBarChart = new Chart(ctx, {
          type: 'bar',
          data: {
            labels: labels,
            datasets: [{
              label: 'Weight %',
              data: values,
              backgroundColor: generatePalette(values.length)
            }]
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: { y: { ticks: { callback: function(v){ return v + '%'; } } } }
          }
        });
      }
      */
    }
  }

  // Cache for portfolio results from CSV
  let portfolioResultsCsvCache = null;

  // Load all portfolio results from CSV
  async function loadPortfolioResultsCsv(){
    if(portfolioResultsCsvCache) return portfolioResultsCsvCache;
    portfolioResultsCsvCache = [];
    try {
      const csvResp = await fetch('data/portfolio_results_db.csv?_=' + Date.now(), {cache:'no-store'});
      if(csvResp.ok){
        const csvText = await csvResp.text();
        const lines = csvText.trim().split('\n');
        if(lines.length > 1){
          // Parse header to find column indices
          const headerLine = lines[0];
          const headerParts = parseCSVLine(headerLine);

          const runIdIdx = headerParts.findIndex(h => h.trim().toLowerCase() === 'run_id');
          const timestampIdx = headerParts.findIndex(h => h.trim().toLowerCase() === 'timestamp');
          const minStocksIdx = headerParts.findIndex(h => h.trim().toLowerCase() === 'min_stocks');
          const maxStocksIdx = headerParts.findIndex(h => h.trim().toLowerCase() === 'max_stocks');
          const stocksIdx = headerParts.findIndex(h => h.trim().toLowerCase() === 'stocks');

          console.debug('CSV header columns:', headerParts.length, { runIdIdx, timestampIdx, minStocksIdx, maxStocksIdx, stocksIdx });

          if(runIdIdx === -1 || timestampIdx === -1){
            console.warn('CSV missing required columns:', { runIdIdx, timestampIdx });
            return portfolioResultsCsvCache;
          }

          for(let i=1; i<lines.length; i++){
            const row = parseCSVLine(lines[i]);

            const runId = row[runIdIdx] ? row[runIdIdx].trim() : '';
            const timestamp = row[timestampIdx] ? row[timestampIdx].trim() : '';

            // Handle different CSV formats:
            // Old format (12 cols): sharpe at 7, final_value at 8, roi at 9, expected_return at 10, volatility at 11
            // New format (10 cols): sharpe at 7, expected_return at 8, volatility at 9

            let expectedReturn = NaN;

            if(row.length >= 12){
              // Old format - expected_return is at index 10
              expectedReturn = parseFloat(row[10]);
            } else if(row.length >= 10){
              // New format - expected_return is at index 8 (right after sharpe at 7)
              expectedReturn = parseFloat(row[8]);
            }

            // Get min_stocks, max_stocks, and count actual stocks
            const minStocks = minStocksIdx !== -1 ? parseInt(row[minStocksIdx]) : NaN;
            const maxStocks = maxStocksIdx !== -1 ? parseInt(row[maxStocksIdx]) : NaN;
            let actualStocks = 0;
            if(stocksIdx !== -1 && row[stocksIdx]){
              // Count stocks by splitting on comma
              const stocksStr = row[stocksIdx].trim();
              if(stocksStr){
                actualStocks = stocksStr.split(',').filter(s => s.trim()).length;
              }
            }

            if(runId && timestamp && !isNaN(expectedReturn) && expectedReturn > 0){
              portfolioResultsCsvCache.push({
                run_id: runId,
                timestamp: timestamp,
                ts: timestamp.split(' ')[0],
                expected_return_annual_pct: expectedReturn,
                min_stocks: minStocks,
                max_stocks: maxStocks,
                actual_stocks: actualStocks
              });
            }
          }

          console.debug('Loaded portfolio results:', portfolioResultsCsvCache.length, 'records');
          if(portfolioResultsCsvCache.length > 0){
            console.debug('First record:', portfolioResultsCsvCache[0]);
            console.debug('Last record:', portfolioResultsCsvCache[portfolioResultsCsvCache.length-1]);
          }
        }
      }
    } catch(e) {
      console.warn('Failed to load portfolio results from CSV', e);
    }
    // Sort by timestamp ascending
    portfolioResultsCsvCache.sort((a,b) => new Date(a.timestamp) - new Date(b.timestamp));
    return portfolioResultsCsvCache;
  }

  // Update portfolio chart with selected range - now uses CSV data with each run_id as separate point
  async function updatePortfolioChart(rangeKey){
    // Load data from CSV
    const allResults = await loadPortfolioResultsCsv();

    if(!allResults || allResults.length === 0){
      // Fallback: clear chart and show message
      try{ if(portfolioChart && portfolioChart.destroy) portfolioChart.destroy(); }catch(e){}
      const c = document.getElementById('portfolioChart');
      try{ const ctx = c.getContext('2d'); ctx.clearRect(0,0,c.width,c.height); }catch(e){}
      showChartError('portfolioChart','No portfolio results data available');
      return;
    }

    // Apply date range filter
    const sliced = sliceByRange(allResults, rangeKey);

    if(sliced.length === 0){
      try{ if(portfolioChart && portfolioChart.destroy) portfolioChart.destroy(); }catch(e){}
      const c = document.getElementById('portfolioChart');
      try{ const ctx = c.getContext('2d'); ctx.clearRect(0,0,c.width,c.height); }catch(e){}
      showChartError('portfolioChart','No data for selected range');
      return;
    }

    // Remove any previous chart error message
    const pc = document.getElementById('portfolioChart');
    if(pc && pc.parentElement) pc.parentElement.querySelectorAll('.chart-error').forEach(n=>n.remove());

    // Prepare data - each run_id is a separate point
    const filteredLabels = sliced.map(d => d.ts);
    const filteredValues = sliced.map(d => d.expected_return_annual_pct);
    const filteredRunIds = sliced.map(d => d.run_id);
    const filteredTimestamps = sliced.map(d => d.timestamp);

    console.debug('updatePortfolioChart:', {rangeKey, points: filteredValues.length, lastValue: filteredValues[filteredValues.length-1]});

    // Format labels for display - use index for x-axis, show date in tooltip
    // This avoids mixing date formats and handles multiple runs on same day
    const formattedLabels = sliced.map((d, idx) => {
      try {
        const date = new Date(d.timestamp);
        return date.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit', year: '2-digit' });
      } catch(e) { return d.ts; }
    });

    try{
      const canvasEl = document.getElementById('portfolioChart');
      try{ canvasEl.width = canvasEl.clientWidth; canvasEl.height = canvasEl.clientHeight; }catch(e){}
      const ctx = canvasEl.getContext('2d');

      // Diagnostics
      const sample = filteredValues.slice(0,3);
      const last = filteredValues[filteredValues.length-1];
      const min = Math.min(...filteredValues);
      const max = Math.max(...filteredValues);
      console.info('Portfolio chart data:', { points: filteredValues.length, sample, last, min, max });

      if(typeof window.Chart === 'undefined'){
        drawLineFallback(canvasEl, filteredValues, '#2b8a3e');
        return;
      }

      // Check for existing chart and update in-place
      try{
        if(typeof Chart !== 'undefined' && Chart.getChart){
          const existing = Chart.getChart(canvasEl);
          if(existing){
            try{
              existing.data.labels = formattedLabels;
              if(existing.data.datasets && existing.data.datasets[0]){
                existing.data.datasets[0].data = filteredValues;
                existing.data.datasets[0].runIds = filteredRunIds;
                existing.data.datasets[0].originalDates = filteredLabels;
                existing.data.datasets[0].timestamps = filteredTimestamps;
              }
              existing.update();
              portfolioChart = existing;
              // Also update stock range chart
              await renderStockRangeChart(sliced, formattedLabels);
              return;
            }catch(e){
              console.warn('Failed to update existing portfolio chart, will recreate', e);
              try{ existing.destroy(); }catch(e){}
            }
          }
        }
      }catch(e){ console.warn('Safe chart check failed', e); }

      portfolioChart = new Chart(ctx, {
        type:'line',
        data: {
          labels: formattedLabels,
          datasets: [{
            label:'Retorno Anual (%)',
            data: filteredValues,
            borderColor:'#2b8a3e',
            backgroundColor:'rgba(43,138,62,0.08)',
            pointRadius: 4,
            pointHoverRadius: 7,
            fill:true,
            runIds: filteredRunIds,
            originalDates: filteredLabels,
            timestamps: filteredTimestamps
          }]
        },
        options: {
          responsive:true,
          maintainAspectRatio:false,
          interaction: { mode: 'nearest', intersect: false },
          plugins:{
            legend:{display:false},
            tooltip:{
              backgroundColor:'rgba(30,41,59,0.95)',
              titleColor:'#f1f5f9',
              bodyColor:'#cbd5e1',
              borderColor:'#475569',
              borderWidth:1,
              padding:12,
              callbacks:{
                title: function(items){
                  if(!items.length) return '';
                  const idx = items[0].dataIndex;
                  const ds = items[0].dataset;
                  const timestamp = ds.timestamps ? ds.timestamps[idx] : '';
                  return timestamp || items[0].label;
                },
                label: function(ctx){
                  const val = ctx.raw;
                  return 'Retorno Anual: ' + (val != null ? val.toFixed(2) + '%' : '—');
                },
                afterLabel: function(ctx){
                  const ds = ctx.dataset;
                  const idx = ctx.dataIndex;
                  const runId = ds.runIds ? ds.runIds[idx] : null;
                  return runId ? 'Run ID: ' + runId : '';
                }
              }
            }
          },
          scales:{
            x:{
              grid:{color:'rgba(255,255,255,0.03)'},
              ticks:{
                color:'#888',
                maxRotation: 45,
                minRotation: 45,
                autoSkip: true,
                maxTicksLimit: 15
              }
            },
            y:{
              grid:{color:'rgba(255,255,255,0.05)'},
              ticks:{
                color:'#aaa',
                callback: function(v){ return v.toFixed(0) + '%'; }
              },
              title:{
                display:true,
                text:'Retorno Anual (%)',
                color:'#aaa'
              }
            }
          }
        }
      });
    }catch(e){
      console.error('Failed to render portfolio chart', e);
      showChartError('portfolioChart','Failed to render chart');
    }

    // Render stock range chart synchronized with portfolio chart
    await renderStockRangeChart(sliced, formattedLabels);
  }

  // Stock range chart instance
  let stockRangeChart = null;

  // Render candlestick-style chart showing min_stocks, max_stocks range and actual stock count
  async function renderStockRangeChart(data, labels){
    const canvas = document.getElementById('stockRangeChart');
    if(!canvas) return;

    try {
      if(stockRangeChart && stockRangeChart.destroy) stockRangeChart.destroy();
    } catch(e) {}

    if(!data || !data.length){
      const ctx = canvas.getContext('2d');
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      return;
    }

    // Prepare data arrays
    const minStocks = data.map(d => d.min_stocks || 0);
    const maxStocks = data.map(d => d.max_stocks || 0);
    const actualStocks = data.map(d => d.actual_stocks || 0);
    const runIds = data.map(d => d.run_id);
    const timestamps = data.map(d => d.timestamp);

    // Create floating bar data for the range (min to max)
    const rangeData = data.map(d => [d.min_stocks || 0, d.max_stocks || 0]);

    try {
      const ctx = canvas.getContext('2d');

      stockRangeChart = new Chart(ctx, {
        type: 'bar',
        data: {
          labels: labels,
          datasets: [
            {
              label: 'Range (min-max)',
              data: rangeData,
              backgroundColor: 'rgba(107, 156, 232, 0.3)',
              borderColor: 'rgba(107, 156, 232, 0.8)',
              borderWidth: 1,
              borderSkipped: false,
              barPercentage: 0.6,
              categoryPercentage: 0.8
            },
            {
              label: 'Qtd. Ações Resultante',
              data: actualStocks,
              type: 'line',
              borderColor: '#f28c28',
              backgroundColor: '#f28c28',
              pointBackgroundColor: '#f28c28',
              pointBorderColor: '#fff',
              pointRadius: 4,
              pointHoverRadius: 6,
              borderWidth: 2,
              fill: false,
              tension: 0.1,
              order: 0 // Draw on top
            }
          ]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          interaction: { mode: 'index', intersect: false },
          plugins: {
            legend: { display: false },
            tooltip: {
              backgroundColor: 'rgba(30,41,59,0.95)',
              titleColor: '#f1f5f9',
              bodyColor: '#cbd5e1',
              borderColor: '#475569',
              borderWidth: 1,
              padding: 12,
              callbacks: {
                title: function(items) {
                  if(!items.length) return '';
                  const idx = items[0].dataIndex;
                  return timestamps[idx] || labels[idx];
                },
                label: function(ctx) {
                  if(ctx.dataset.label === 'Range (min-max)') {
                    const range = ctx.raw;
                    return `Range: ${range[0]} - ${range[1]} ações`;
                  } else {
                    return `Resultado: ${ctx.raw} ações`;
                  }
                },
                afterBody: function(items) {
                  if(!items.length) return '';
                  const idx = items[0].dataIndex;
                  return 'Run ID: ' + (runIds[idx] || 'N/A');
                }
              }
            }
          },
          scales: {
            x: {
              display: false, // Hide x-axis since it's synchronized with the chart above
              grid: { display: false }
            },
            y: {
              beginAtZero: true,
              grid: { color: 'rgba(255,255,255,0.05)' },
              ticks: {
                color: '#aaa',
                stepSize: 5,
                callback: function(v) { return v; }
              },
              title: {
                display: true,
                text: 'Nº Ações',
                color: '#aaa',
                font: { size: 11 }
              }
            }
          }
        }
      });
    } catch(e) {
      console.error('Failed to render stock range chart', e);
    }
  }

  // Render holdings table with badges and sparklines
  function renderHoldingsTable(data){
    const p = data.best_portfolio_details || {};
    const stocksRaw = p.stocks || []; const weightsRaw = p.weights || [];
    const holdings_meta = p.holdings_meta || {};
    const benchmark_pe = (p.momentum_valuation && p.momentum_valuation.benchmark_forward_pe) || null;

    // Ordenar por peso decrescente
    const indexed = stocksRaw.map((s, i) => ({ stock: s, weight: weightsRaw[i] || 0, index: i }));
    indexed.sort((a, b) => b.weight - a.weight);
    const stocks = indexed.map(x => x.stock);
    const weights = indexed.map(x => x.weight);

    const tbody = els.stocksTableBody;
    if(!tbody) return;

    // If the existing table rows match the incoming stocks length and order, update in-place to avoid
    // recreating DOM nodes (much faster on frequent refreshes). Otherwise rebuild the table.
    const existingRows = Array.from(tbody.rows || []);
    let canUpdateInPlace = (existingRows.length === stocks.length);
    if(canUpdateInPlace){
      for(let i=0;i<stocks.length;i++){
        const row = existingRows[i];
        if(!row) { canUpdateInPlace = false; break; }
        const ticker = (row.getAttribute('data-ticker')||'');
        if(ticker !== (stocks[i] || '')) { canUpdateInPlace = false; break; }
      }
    }

    if(canUpdateInPlace){
      // Update cells (weight value + dataset, badge colors) only
      for(let i=0;i<stocks.length;i++){
        const stock = stocks[i]; const w = weights[i] || 0;
        const row = existingRows[i];
        row.setAttribute('data-ticker', stock || '');
        // update # (th)
        const th = row.cells[0]; if(th) th.textContent = i+1;
        // stock name cell
        const tdStock = row.cells[1]; if(tdStock) tdStock.firstChild && (tdStock.firstChild.textContent = stock || '–');
        // forward PE cell (column index 2)
        const fwdCell = row.cells[2];
        const meta = holdings_meta[stock] || {};
        const fpe = meta.forwardPE;
        if(fwdCell){
          fwdCell.textContent = (fpe==null || isNaN(Number(fpe))) ? 'n/a' : Number(fpe).toFixed(1);
        }
        // latest price cell (column index 3)
        const latestPriceCell = row.cells[3];
        const latestPrice = meta.currentPrice;
        if(latestPriceCell){
          latestPriceCell.textContent = (latestPrice==null || isNaN(Number(latestPrice))) ? 'n/a' : 'R$ ' + Number(latestPrice).toFixed(2);
        }
        // target price cell (column index 4)
        const targetPriceCell = row.cells[4];
        const targetPrice = meta.targetPrice;
        if(targetPriceCell){
          targetPriceCell.textContent = (targetPrice==null || isNaN(Number(targetPrice))) ? 'n/a' : 'R$ ' + Number(targetPrice).toFixed(2);
        }
        // weight cell (column index 5)
        const weightCell = row.cells[5]; if(weightCell){
          weightCell.dataset.weight = String(Number(w));
          // keep visible percentage text in data-orig so decorate can recompute
          weightCell.dataset.orig = (Number(w)*100).toFixed(1) + '%';
        }
        // spark cell remains (column index 6); clear pct text placeholder
        const sparkCell = row.cells[6]; if(sparkCell){ const pctEl = sparkCell.querySelector('.spark-pct'); if(pctEl) pctEl.textContent = '—'; }
      }
      // draw sparklines for updated rows and decorate weights
      renderSparklines(lastFullData || {});
      decorateExistingWeightCells();
      return;
    }

    // Fallback: rebuild table as before
    clearTable();
    for(let i=0;i<stocks.length;i++){
      const stock = stocks[i]; const w = weights[i] || 0;
      const tr = document.createElement('tr'); tr.setAttribute('data-ticker', stock||'');
      const th = document.createElement('th'); th.textContent = i+1;
      const td1 = document.createElement('td'); td1.textContent = stock || '—';
      // forward PE cell
      const tdFpe = document.createElement('td');
      const meta = holdings_meta[stock] || {};
      const fpe = meta.forwardPE;
      tdFpe.textContent = (fpe==null || isNaN(Number(fpe)) || Number(fpe) === 0) ? 'n/a' : Number(fpe).toFixed(1);
      // latest price cell
      const tdLatestPrice = document.createElement('td');
      const latestPrice = meta.currentPrice;
      tdLatestPrice.textContent = (latestPrice==null || isNaN(Number(latestPrice)) || Number(latestPrice) <= 0) ? 'n/a' : 'R$ ' + Number(latestPrice).toFixed(2);
      // target price cell
      const tdTargetPrice = document.createElement('td');
      const targetPrice = meta.targetPrice;
      tdTargetPrice.textContent = (targetPrice==null || isNaN(Number(targetPrice)) || Number(targetPrice) <= 0) ? 'n/a' : 'R$ ' + Number(targetPrice).toFixed(2);
      // weight cell
      const td2 = document.createElement('td'); td2.textContent = (Number(w)*100).toFixed(1)+'%';
      td2.dataset.weight = String(Number(w));
      td2.classList.add('weight-cell-raw');
      // spark cell
      const td3 = document.createElement('td'); const c = document.createElement('canvas'); c.className='spark-canvas'; c.width=120; c.height=28; td3.appendChild(c);
      const pctSpan = document.createElement('span'); pctSpan.className='spark-pct'; pctSpan.style.marginLeft='8px'; pctSpan.style.fontSize='12px'; pctSpan.style.fontWeight='600'; pctSpan.textContent='—';
      td3.appendChild(pctSpan);
      // append in order: #, stock, fwdPE, latestPrice, targetPrice, weight, spark
      tr.appendChild(th); tr.appendChild(td1); tr.appendChild(tdFpe); tr.appendChild(tdLatestPrice); tr.appendChild(tdTargetPrice); tr.appendChild(td2); tr.appendChild(td3);
      // actually append the built row to the table body (previously missing)
      els.stocksTableBody.appendChild(tr);
    }
    renderSparklines(lastFullData || {});
    decorateExistingWeightCells();
  }

  // update spark header once the data is loaded
  function refreshSparkHeader(){ updateSparkHeader(lastFullData || {}); }

  // --- Helper: parse various weight formats (string with %, number fraction or percent) to fraction 0..1 ---
  function parseWeightToFraction(w){
    if(w==null) return 0;
    if(typeof w === 'number') return w > 1 ? w/100 : w; // treat >1 as percent
    if(typeof w === 'string'){
      const s = w.trim();
      if(s.endsWith('%')) return (parseFloat(s.slice(0,-1).replace(',','.'))||0)/100;
      const n = parseFloat(s.replace(',','.'))||0;
      return n>1 ? n/100 : n;
    }
    return 0;
  }

  // --- Helper: find column index by header text (case-insensitive) ---
  function findColumnIndexByHeaderText(table, headerText){
    const ths = table.querySelectorAll('thead th');
    for(let i=0;i<ths.length;i++){
      if((ths[i].textContent||'').trim().toLowerCase() === headerText.toLowerCase()) return i;
    }
    return -1;
  }

  // --- Decorate existing weight cells in the table, adding bar background + numeric text ---
  function decorateExistingWeightCells(){
    const table = document.getElementById('stocksTable'); if(!table) return;
    const weightColIndex = findColumnIndexByHeaderText(table, 'Weight'); if(weightColIndex===-1) return;
    const rows = Array.from(table.tBodies[0].rows || []);
    // read weights from data-weight when available to avoid reparsing text and costly queries
    const fracs = rows.map(r => {
      const cell = r.cells[weightColIndex];
      if(!cell) return 0;
      const ds = cell.dataset && cell.dataset.weight;
      if(ds != null && ds !== '') return parseFloat(ds) || 0;
      // fallback to parsing visible text
      const txt = (cell.textContent || '').trim();
      return parseWeightToFraction(txt);
    });
    const total = fracs.reduce((a,b)=>a+b,0) || 1;
    for(let i=0;i<rows.length;i++){
      const r = rows[i];
      const cell = r.cells[weightColIndex]; if(!cell) continue;
      const frac = fracs[i] || 0;
      const pct = (frac/total)*100;
      const pctClamped = Math.min(Math.max(pct,0),100);
      const displayText = isNaN(pct) ? '—' : (pct.toFixed(1) + '%');
      cell.classList.add('weight-cell');
      cell.setAttribute('title', displayText);
      if(!cell.dataset.orig) cell.dataset.orig = (cell.textContent || '').trim();
      // minimize DOM thrash by writing a short HTML fragment
      cell.innerHTML = '<div class="weight-bar-bg" aria-hidden="true"><div class="weight-bar" style="width:' + pctClamped + '%;"></div></div><div class="weight-val">' + displayText + '</div>';
    }
  }

  // compute spark column title based on data
  function computeSparkTitle(data){
    const p = data && data.best_portfolio_details ? data.best_portfolio_details : {};
    const sparklines = p.stock_sparklines || {};
    // prefer explicit dates if provided
    if(p.stock_sparklines_dates && Array.isArray(p.stock_sparklines_dates) && p.stock_sparklines_dates.length){
      try{
        const dates = p.stock_sparklines_dates.map(d => new Date(d)).filter(d=>!isNaN(d));
        if(dates.length>=2){
          const first = dates[0], last = dates[dates.length-1];
          const months = (last.getFullYear()-first.getFullYear())*12 + (last.getMonth()-first.getMonth());
          if(months >= 11 && months <= 14) return 'Spark TTM';
          const m = first.toLocaleString(undefined,{month:'short'});
          const y = String(first.getFullYear()).slice(-2);
          return `Spark (since ${m}${y})`;
        }
      }catch(e){}
    }
    // fallback: infer by number of points
    let maxLen = 0; for(const k in sparklines){ const arr = sparklines[k]||[]; if(arr.length>maxLen) maxLen = arr.length; }
    if(maxLen >= 240) return 'Spark TTM';
    if(maxLen >= 60) return 'Spark 12M';
    if(maxLen > 0) return `Spark (${maxLen} pts)`;
    return 'Spark';
  }

  function updateSparkHeader(data){
    const table = document.getElementById('stocksTable'); if(!table) return;
    const ths = table.querySelectorAll('thead th'); if(!ths || !ths.length) return;
    // find spark column index (header text starts with 'spark' or last column)
    let sparkIdx = -1;
    for(let i=0;i<ths.length;i++){
      const t = (ths[i].textContent||'').trim().toLowerCase(); if(t.startsWith('spark')){ sparkIdx = i; break; }
    }
    if(sparkIdx === -1) sparkIdx = ths.length - 1;
    const title = computeSparkTitle(data || lastFullData || {});
    ths[sparkIdx].textContent = title;
    ths[sparkIdx].setAttribute('title', 'Sparkline window inferred from sampled data');
  }

  // Flag to prevent concurrent correlation matrix renders
  let correlationRenderInProgress = false;

  // Render correlation matrix heatmap
  async function renderCorrelationMatrix(){
    const container = els.correlationMatrix || document.getElementById('correlationMatrix');
    if(!container) return;

    // Prevent concurrent renders
    if(correlationRenderInProgress) return;
    correlationRenderInProgress = true;

    container.innerHTML = '';

    // Get current portfolio stocks for highlighting
    const currentPortfolioStocks = new Set();
    if(lastFullData && lastFullData.best_portfolio_details && lastFullData.best_portfolio_details.stocks){
      lastFullData.best_portfolio_details.stocks.forEach(s => currentPortfolioStocks.add(s));
    }

    try {
      const resp = await fetch('data/correlation_matrix.csv?_=' + Date.now(), {cache:'no-store'});
      if(!resp.ok) throw new Error('HTTP ' + resp.status);
      const text = await resp.text();

      // Parse CSV
      const lines = text.split(/\r?\n/).filter(l=>l.length>0);
      if(lines.length === 0){
        container.innerHTML = '<div class="no-data">No correlation data available</div>';
        correlationRenderInProgress = false;
        return;
      }

      // Parse header and rows
      const cols = parseCSVLine(lines[0]);
      const rows = [];
      for(let i=1; i<lines.length; i++){
        const parts = parseCSVLine(lines[i]);
        while(parts.length < cols.length) parts.push('');
        rows.push(parts);
      }

      // Build heatmap table
      const headers = cols.slice(1); // first column is row labels
      const matrix = rows.map(r => r.slice(1).map(v => Number(v)));

      // Clear container again before appending (in case of race condition)
      container.innerHTML = '';

      const table = document.createElement('table');

      // Header row
      const thead = document.createElement('thead');
      const trh = document.createElement('tr');
      const thCorner = document.createElement('th');
      thCorner.textContent = '';
      trh.appendChild(thCorner);
      headers.forEach(h => {
        const th = document.createElement('th');
        th.textContent = h;
        th.title = h;
        // Highlight if in current portfolio
        if(currentPortfolioStocks.has(h)){
          th.classList.add('in-portfolio');
        }
        trh.appendChild(th);
      });
      thead.appendChild(trh);
      table.appendChild(thead);

      // Body rows
      const tbody = document.createElement('tbody');
      for(let i=0; i<matrix.length; i++){
        const tr = document.createElement('tr');
        const rowStock = rows[i][0];
        const rowInPortfolio = currentPortfolioStocks.has(rowStock);

        // Row header (ticker name)
        const th = document.createElement('th');
        th.textContent = rowStock;
        th.title = rowStock;
        // Highlight if in current portfolio
        if(rowInPortfolio){
          th.classList.add('in-portfolio');
        }
        tr.appendChild(th);

        // Data cells
        for(let j=0; j<matrix[i].length; j++){
          const td = document.createElement('td');
          const v = matrix[i][j];
          const colStock = headers[j];
          const colInPortfolio = currentPortfolioStocks.has(colStock);

          // Don't show text in cells (too crowded), show on hover via title
          td.textContent = '';
          // Color: map -1..1 to red..green
          const pct = Math.max(0, Math.min(1, (v + 1) / 2));
          // Use gradient: red (negative) -> yellow (neutral) -> green (positive)
          let r, g, b;
          if(pct < 0.5){
            // red to yellow
            r = 220;
            g = Math.round(180 * (pct * 2));
            b = 80;
          } else {
            // yellow to green
            r = Math.round(220 * (1 - (pct - 0.5) * 2));
            g = 180;
            b = 80;
          }
          td.style.background = `rgba(${r}, ${g}, ${b}, 0.85)`;
          td.title = `${rowStock} / ${colStock}: ${Number.isFinite(v) ? v.toFixed(3) : 'n/a'}`;

          // Highlight cell if both row and column are in portfolio
          if(rowInPortfolio && colInPortfolio){
            td.classList.add('portfolio-correlation');
          }
          tr.appendChild(td);
        }
        tbody.appendChild(tr);
      }
      table.appendChild(tbody);
      container.appendChild(table);
      correlationRenderInProgress = false;

    } catch(err) {
      console.error('Failed to load correlation matrix', err);
      container.innerHTML = '<div class="no-data">Failed to load correlation data</div>';
      correlationRenderInProgress = false;
    }
  }

  // ── Performance Attribution ─────────────────────────────────────────────────
  let attributionChartInstance = null;

  async function loadPerformanceAttribution() {
    try {
      const res = await fetch('./data/performance_attribution.json?_=' + Date.now());
      if (!res.ok) {
        console.warn('Failed to load performance_attribution.json:', res.status);
        return;
      }
      const data = await res.json();
      renderPerformanceAttribution(data);
    } catch (e) {
      console.warn('Failed to load performance attribution:', e);
    }
  }

  function renderPerformanceAttribution(data) {
    // Update total active return
    const totalEl = document.getElementById('attrTotalReturn');
    if (totalEl) {
      const total = data.total_active_return;
      if (total != null && !isNaN(total)) {
        totalEl.textContent = (total >= 0 ? '+' : '') + total.toFixed(2) + '%';
        totalEl.classList.toggle('negative', total < 0);
      } else {
        totalEl.textContent = '—';
      }
    }

    // Render breakdown details
    const detailsEl = document.getElementById('attributionDetails');
    if (detailsEl) {
      const items = [
        { key: 'allocation_effect', label: 'Allocation Effect', desc: 'Ganho por escolha de setores' },
        { key: 'selection_effect', label: 'Selection Effect', desc: 'Ganho por seleção de ações' },
        { key: 'interaction_effect', label: 'Interaction Effect', desc: 'Efeito combinado' }
      ];

      // Find max absolute value for bar scaling
      const maxAbs = Math.max(
        ...items.map(it => Math.abs(data[it.key] || 0)),
        0.0001
      );

      detailsEl.innerHTML = items.map(item => {
        const val = data[item.key] || 0;
        const isNegative = val < 0;
        const barWidth = (Math.abs(val) / maxAbs) * 100;
        return `
          <div class="attribution-item">
            <div class="attribution-item-header">
              <span class="attribution-item-label">${item.label}</span>
              <span class="attribution-item-value ${isNegative ? 'negative' : ''}">${(val >= 0 ? '+' : '') + val.toFixed(2)}%</span>
            </div>
            <div class="attribution-bar-bg">
              <div class="attribution-bar ${isNegative ? 'negative' : 'positive'}" style="width: ${barWidth}%"></div>
            </div>
          </div>
        `;
      }).join('');
    }

    // Render chart
    renderAttributionChart(data);
  }

  function renderAttributionChart(data) {
    const ctx = document.getElementById('attributionChart');
    if (!ctx) return;

    if (attributionChartInstance) {
      try { attributionChartInstance.destroy(); } catch(e) {}
    }

    const items = [
      { key: 'allocation_effect', label: 'Allocation' },
      { key: 'selection_effect', label: 'Selection' },
      { key: 'interaction_effect', label: 'Interaction' }
    ];

    const labels = items.map(it => it.label);
    const values = items.map(it => data[it.key] || 0);

    // Color based on positive/negative
    const colors = values.map(v => v >= 0 ? 'rgba(91, 210, 163, 0.85)' : 'rgba(231, 111, 81, 0.85)');
    const borderColors = values.map(v => v >= 0 ? 'rgba(91, 210, 163, 1)' : 'rgba(231, 111, 81, 1)');

    attributionChartInstance = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: labels,
        datasets: [{
          label: 'Attribution Effect',
          data: values,
          backgroundColor: colors,
          borderColor: borderColors,
          borderWidth: 1,
          borderRadius: 6
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: 'rgba(30, 41, 59, 0.95)',
            titleColor: '#f1f5f9',
            bodyColor: '#cbd5e1',
            borderColor: '#475569',
            borderWidth: 1,
            padding: 10,
            callbacks: {
              label: (ctx) => {
                const val = ctx.raw;
                return `${ctx.label}: ${(val >= 0 ? '+' : '') + val.toFixed(2)}%`;
              }
            }
          }
        },
        scales: {
          x: {
            grid: { display: false },
            ticks: { color: '#ccc', font: { size: 11 } }
          },
          y: {
            grid: { color: 'rgba(255,255,255,0.05)' },
            ticks: {
              color: '#aaa',
              callback: (val) => val.toFixed(1) + '%'
            },
            title: {
              display: true,
              text: 'Effect (%)',
              color: '#aaa'
            }
          }
        }
      }
    });
  }

  // ── Portfolio Diagnostics Metrics ───────────────────────────────────────────
  async function loadPortfolioDiagnostics() {
    try {
      const res = await fetch('./data/portfolio_diagnostics.json?_=' + Date.now());
      if (!res.ok) {
        console.warn('Failed to load portfolio_diagnostics.json:', res.status);
        return;
      }
      const data = await res.json();
      renderPortfolioDiagnostics(data);
    } catch (e) {
      console.warn('Failed to load portfolio diagnostics:', e);
    }
  }

  function renderPortfolioDiagnostics(data) {
    // Helper functions
    const formatPct = (v) => {
      if (v == null || isNaN(v)) return '—';
      const pct = Number(v) * 100;
      return (pct >= 0 ? '+' : '') + pct.toFixed(2) + '%';
    };
    const formatNum = (v, decimals = 2) => {
      if (v == null || isNaN(v)) return '—';
      return Number(v).toLocaleString('pt-BR', { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
    };
    const formatLarge = (v) => {
      if (v == null || isNaN(v)) return '—';
      const num = Number(v);
      if (num >= 1e9) return (num / 1e9).toFixed(1) + 'B';
      if (num >= 1e6) return (num / 1e6).toFixed(1) + 'M';
      if (num >= 1e3) return (num / 1e3).toFixed(1) + 'K';
      return num.toFixed(0);
    };

    // Momentum Signal Strength (range: -1 to +1)
    const momentumEl = document.getElementById('diag_momentum_signal');
    const momentumMarker = document.getElementById('diag_momentum_marker');
    if (momentumEl) {
      const ms = data.momentum_signal_strength;
      if (ms != null && !isNaN(ms)) {
        momentumEl.textContent = Number(ms).toFixed(4);
        momentumEl.classList.toggle('positive', ms > 0);
        momentumEl.classList.toggle('negative', ms < 0);
        // Position marker: -1 = 0%, 0 = 50%, +1 = 100%
        if (momentumMarker) {
          const pct = ((Number(ms) + 1) / 2) * 100;
          momentumMarker.style.left = Math.max(2, Math.min(98, pct)) + '%';
        }
      } else {
        momentumEl.textContent = '—';
      }
    }

    // Forward P/E Implied Upside
    const peUpsideEl = document.getElementById('diag_pe_upside');
    if (peUpsideEl) {
      const v = data.forward_pe_implied_upside;
      if (v != null && !isNaN(v)) {
        peUpsideEl.textContent = formatPct(v);
        peUpsideEl.classList.toggle('positive', v > 0);
        peUpsideEl.classList.toggle('negative', v < 0);
      } else {
        peUpsideEl.textContent = '—';
      }
    }

    // Weighted Dividend Yield
    const divYieldEl = document.getElementById('diag_div_yield');
    if (divYieldEl) {
      const v = data.weighted_dividend_yield;
      if (v != null && !isNaN(v)) {
        // If value > 1, assume it's raw and format accordingly
        if (Math.abs(v) > 1) {
          divYieldEl.textContent = formatNum(v, 2);
        } else {
          divYieldEl.textContent = formatPct(v);
        }
      } else {
        divYieldEl.textContent = '—';
      }
    }

    // Turnover
    const turnoverEl = document.getElementById('diag_turnover');
    const turnoverBar = document.getElementById('diag_turnover_bar');
    const kpiTurnoverEl = document.getElementById('kpi-turnover-val');
    if (turnoverEl || kpiTurnoverEl) {
      const v = data.turnover;
      if (v != null && !isNaN(v)) {
        const turnoverText = (Number(v) * 100).toFixed(1) + '%';
        if (turnoverEl) turnoverEl.textContent = turnoverText;
        if (kpiTurnoverEl) kpiTurnoverEl.textContent = turnoverText;
        if (turnoverBar) {
          turnoverBar.style.width = Math.min(100, Number(v) * 100) + '%';
        }
      } else {
        if (turnoverEl) turnoverEl.textContent = '—';
        if (kpiTurnoverEl) kpiTurnoverEl.textContent = '—';
      }
    }

    // Liquidity Score
    const liquidityEl = document.getElementById('diag_liquidity');
    if (liquidityEl) {
      const v = data.liquidity_score;
      liquidityEl.textContent = v != null ? formatLarge(v) : '—';
    }

    // Tracking Error
    const trackingEl = document.getElementById('diag_tracking_error');
    const trackingBar = document.getElementById('diag_tracking_bar');
    if (trackingEl) {
      const v = data.tracking_error;
      if (v != null && !isNaN(v)) {
        trackingEl.textContent = (Number(v) * 100).toFixed(2) + '%';
        if (trackingBar) {
          // Assume max tracking error ~50% for bar scaling
          trackingBar.style.width = Math.min(100, (Number(v) / 0.5) * 100) + '%';
        }
      } else {
        trackingEl.textContent = '—';
      }
    }

    // Information Ratio: <0 ruim, 0-0.5 ok, 0.5-1 bom, >1 excelente
    const infoRatioEl = document.getElementById('diag_info_ratio');
    const infoRatioBar = document.getElementById('diag_info_ratio_bar');
    const infoRatioQual = document.getElementById('diag_info_ratio_qual');
    if (infoRatioEl) {
      const v = data.information_ratio;
      if (v != null && !isNaN(v)) {
        infoRatioEl.textContent = Number(v).toFixed(2);
        infoRatioEl.classList.toggle('positive', v > 0);
        infoRatioEl.classList.toggle('negative', v < 0);

        // Bar and qualification
        if (infoRatioBar && infoRatioQual) {
          let pct, color, label;
          if (v < 0) {
            pct = Math.max(5, 25 + (v * 25)); // negative values get small bar
            color = '#f44336'; label = 'Ruim';
          } else if (v < 0.5) {
            pct = 25 + (v / 0.5) * 25;
            color = '#FFC107'; label = 'Regular';
          } else if (v < 1) {
            pct = 50 + ((v - 0.5) / 0.5) * 25;
            color = '#8BC34A'; label = 'Bom';
          } else {
            pct = 75 + Math.min(25, ((v - 1) / 1) * 25);
            color = '#4CAF50'; label = 'Excelente';
          }
          infoRatioBar.style.width = pct + '%';
          infoRatioBar.style.background = color;
          infoRatioQual.textContent = label;
          infoRatioQual.style.color = color;
          infoRatioQual.style.fontSize = '10px';
          infoRatioQual.style.fontWeight = '600';
          infoRatioQual.style.marginTop = '4px';
        }
      } else {
        infoRatioEl.textContent = '—';
      }
    }
  }

  // render everything
  async function renderAll(data){
    // populate top meta block: only Run ID and Last updated (now styled as footnote)
    lastFullData = data;
    if(els.runId) els.runId.textContent = data.last_updated_run_id || '—';
    if(els.lastUpdated) els.lastUpdated.textContent = data.last_updated_timestamp || '—';
    // populate table footnote with last run date
    if(els.tableRunDate) els.tableRunDate.textContent = data.last_updated_timestamp || '—';
    const p = data.best_portfolio_details || {};

    // Load portfolio results cache for composition modal
    await loadPortfolioResultsCache();

    // KPIs and other sections
    renderKPIs(data);
    renderHoldingsTable(data);
    renderTreemap(data);
    await loadPerformanceAttribution();
    await loadPortfolioDiagnostics();
    await renderCorrelationMatrix();
    await renderGA(data);
    await renderVolatilityChart(data);

    // default portfolio range: all
    await updatePortfolioChart('all');

    // render composition history stacked area chart (synchronized with portfolio chart)
    await renderCompositionHistoryChart('all');

    // render sector donut and concentration bar
    renderSectorAndConcentration(data);

    // update spark column header (in case dataset provides longer/shorter series)
    updateSparkHeader(data);
  }

  // early sanity checks for required DOM nodes
  try{
    if(!els.runId || !els.lastUpdated){
      setDebug('Warning: some top meta elements are missing from the DOM');
      console.warn('Missing meta elements', {runId: !!els.runId, lastUpdated: !!els.lastUpdated});
    }
  }catch(e){ console.warn('Sanity check failed', e); }

  function render(data){
    try{
      renderAll(data);
    }catch(err){
      console.error('renderAll failed', err);
      setDebug('Render error: ' + (err && err.message ? err.message : String(err)));
      // try to still populate minimal metadata so user sees something
      try{
        if(data){
          if(els.runId) els.runId.textContent = data.last_updated_run_id || '—';
          if(els.lastUpdated) els.lastUpdated.textContent = data.last_updated_timestamp || '—';
        }
      }catch(e){}
    }
  }

  async function fetchIfChanged(){
    // Clear CSV cache to force reload
    portfolioResultsCsvCache = null;

    try{
      const headResp = await fetch(JSON_PATH, {method:'HEAD', cache:'no-store'});
      if(!headResp.ok){ console.warn('HEAD fetch failed', headResp.status); }
      const etag = headResp.headers.get('ETag');
      const lm = headResp.headers.get('Last-Modified');
      if(etag && lastETag === etag){ els.lastFetch.textContent = new Date().toLocaleTimeString(); return; }
      if(!etag && lm && lastModified === lm){ els.lastFetch.textContent = new Date().toLocaleTimeString(); return; }
      const resp = await fetch(JSON_PATH + '?_=' + Date.now(), {cache:'no-store'});
      if(!resp.ok) throw new Error('Failed to fetch JSON: '+resp.status);
      const data = await resp.json();
      render(data);
      lastETag = resp.headers.get('ETag') || lastETag; lastModified = resp.headers.get('Last-Modified') || lastModified; els.lastFetch.textContent = new Date().toLocaleTimeString();
    }catch(err){ console.error('Fetch error', err); els.lastFetch.textContent = 'error'; setDebug('Failed to fetch latest_run_summary.json — see console'); }
  }

  async function loop(){ if(!polling) return; await fetchIfChanged(); setTimeout(loop, POLL_INTERVAL); }
  els.refreshBtn.addEventListener('click', ()=>{ fetchIfChanged(); });

  // Event listeners for range buttons (period selector)
  document.querySelectorAll('.range-btn').forEach(btn => {
    btn.addEventListener('click', async function() {
      // Remove active class from all buttons
      document.querySelectorAll('.range-btn').forEach(b => b.classList.remove('active'));
      // Add active class to clicked button
      this.classList.add('active');
      // Get the range from data-range attribute
      const range = this.getAttribute('data-range') || 'all';
      // Update all three charts with new range (they are synchronized)
      await updatePortfolioChart(range);
      // Composition chart is updated via updatePortfolioChart -> renderStockRangeChart
      // but we also need to update the composition history chart
      await renderCompositionHistoryChart(range);
    });
  });

  // initial load
  fetchIfChanged(); loop();
})();
