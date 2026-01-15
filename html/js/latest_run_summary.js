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
    treemapContainer: document.getElementById('treemap'),
    gaChartCanvas: document.getElementById('gaChart'),
    volChartCanvas: document.getElementById('volChart'),
    rangeButtons: document.querySelectorAll('.range-btn'),
    // Diagnostics KPIs (side panels)
    kpiSharpeDiag: document.querySelector('#kpi-sharpe-diag .kpi-val'),
    kpiVolDiag: document.querySelector('#kpi-vol-diag .kpi-val'),
    kpiHhiDiag: document.querySelector('#kpi-hhi-diag .kpi-val'),
    kpiPeDiag: document.querySelector('#kpi-pe-diag .kpi-val')
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
  // Diagnostics KPI fallbacks
  if(!els.kpiSharpeDiag) els.kpiSharpeDiag = { textContent: '' };
  if(!els.kpiVolDiag) els.kpiVolDiag = { textContent: '' };
  if(!els.kpiHhiDiag) els.kpiHhiDiag = { textContent: '' };
  if(!els.kpiPeDiag) els.kpiPeDiag = { textContent: '' };
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
  let lastFullData = null; // keep fetched JSON for range slicing

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

    // Main KPIs (top section)
    els.kpiSharpe.textContent = p.sharpe_ratio != null ? Number(p.sharpe_ratio).toFixed(3) : '—';
    els.kpiReturn.textContent = p.expected_return_annual_pct != null ? Number(p.expected_return_annual_pct).toFixed(1)+'%' : '—';
    els.kpiTop5.textContent = cr.top_5_holdings_pct != null ? (Number(cr.top_5_holdings_pct)*100).toFixed(1)+'%' : '—';

    // Diagnostics KPIs (side panels)
    els.kpiSharpeDiag.textContent = p.sharpe_ratio != null ? Number(p.sharpe_ratio).toFixed(3) : '—';
    els.kpiVolDiag.textContent = p.expected_volatility_annual_pct != null ? Number(p.expected_volatility_annual_pct).toFixed(1)+'%' : '—';
    els.kpiHhiDiag.textContent = cr.hhi != null ? Number(cr.hhi).toFixed(4) : '—';
    els.kpiPeDiag.textContent = p.portfolio_weighted_pe != null ? Number(p.portfolio_weighted_pe).toFixed(1) : '—';

    // mini-summary values (below table) — use JSON fields or compute reasonable fallbacks
    let computed_pwpe = null;
    if(p.portfolio_weighted_pe != null) computed_pwpe = Number(p.portfolio_weighted_pe);
    else if(Array.isArray(p.stocks) && Array.isArray(p.weights) && p.holdings_meta){
      let sum = 0, tw = 0;
      for(let i=0;i<p.stocks.length;i++){ const s=p.stocks[i]; const w=p.weights[i]||0; const meta = p.holdings_meta && p.holdings_meta[s]; const f = meta && meta.forwardPE; if(f!=null && !isNaN(Number(f)) && Number(f)>0){ sum += Number(f)*w; tw += w; } }
      if(tw>0) computed_pwpe = sum / tw;
    }
    els.pe.textContent = (computed_pwpe != null && !isNaN(Number(computed_pwpe))) ? Number(computed_pwpe).toFixed(1) : '—';

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

    let computed_bpe = null;
    if(p.momentum_valuation && p.momentum_valuation.benchmark_forward_pe != null) computed_bpe = Number(p.momentum_valuation.benchmark_forward_pe);
    else if(p.holdings_meta){
      const vals = Object.keys(p.holdings_meta).map(k=>p.holdings_meta[k] && p.holdings_meta[k].forwardPE).filter(v=>v!=null && !isNaN(Number(v)) && Number(v)>0).map(Number);
      if(vals.length) computed_bpe = vals.reduce((a,b)=>a+b,0)/vals.length;
    }
    els.bpe.textContent = (computed_bpe != null && !isNaN(Number(computed_bpe))) ? Number(computed_bpe).toFixed(1) : '—';
  }

  // render treemap using simple flex tiles
  function renderTreemap(data){
    const list = data.best_portfolio_details && data.best_portfolio_details.sector_exposure_list ? data.best_portfolio_details.sector_exposure_list : [];
    const container = els.treemapContainer; container.innerHTML='';
    if(!list || !list.length){ container.textContent='No sector data'; return; }
    // create tiles with flex-basis proportional to pct
    list.forEach((s, idx)=>{
      const pct = Number(s.pct) || 0; const wperc = Math.max(pct*100, 3); // min size
      const tile = document.createElement('div');
      tile.className = 'treemap-tile';
      tile.style.flex = `0 0 ${wperc}%`;
      tile.style.minWidth = '80px';
      tile.style.height = '80px';
      tile.style.margin = '4px';
      tile.style.borderRadius = '6px';
      tile.style.display = 'flex'; tile.style.flexDirection = 'column'; tile.style.justifyContent='center'; tile.style.alignItems='center';
      tile.style.color = '#012';
      const palette = generatePalette(8);
      tile.style.background = palette[idx % palette.length];
      tile.innerHTML = `<strong>${s.sector}</strong><small style="opacity:0.85">${(pct*100).toFixed(1)}%</small>`;
      tile.title = `${s.sector}: ${(pct*100).toFixed(2)}%`;
      container.appendChild(tile);
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
          legend:{display:true, position:'top', labels:{color:'#cbd5e1'}},
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

          let runIdIdx = 0, timestampIdx = 1, volIdx = 9;
          let startLine = 0;

          if(hasHeader){
            const header = firstLine.split(',');
            runIdIdx = header.findIndex(h => h.trim().toLowerCase() === 'run_id');
            timestampIdx = header.findIndex(h => h.trim().toLowerCase() === 'timestamp');
            volIdx = header.findIndex(h => h.trim().toLowerCase() === 'expected_volatility_annual_pct');
            if(runIdIdx === -1) runIdIdx = 0;
            if(timestampIdx === -1) timestampIdx = 1;
            if(volIdx === -1) volIdx = 9; // fallback to index 9 for CSV without proper header
            startLine = 1;
          }

          for(let i=startLine; i<lines.length; i++){
            const row = parseCSVLine(lines[i]);
            if(row.length > Math.max(runIdIdx, timestampIdx, volIdx)){
              const runId = row[runIdIdx] || '';
              const timestamp = row[timestampIdx] || '';
              const vol = parseFloat(row[volIdx]);
              if(!isNaN(vol) && timestamp){
                historicalData.push({
                  run_id: runId,
                  timestamp: timestamp,
                  volatility: vol
                });
              }
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
          legend:{display:true, position:'top', labels:{color:'#cbd5e1'}},
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

  // Cache for run_id by date - loaded from CSV
  let runIdByDateCache = null;

  // Load run_id mapping from CSV (date -> run_id)
  async function loadRunIdCache(){
    if(runIdByDateCache) return runIdByDateCache;
    runIdByDateCache = {};
    try {
      const csvResp = await fetch('data/portfolio_results_db.csv?_=' + Date.now(), {cache:'no-store'});
      if(csvResp.ok){
        const csvText = await csvResp.text();
        const lines = csvText.trim().split('\n');
        if(lines.length > 0){
          const firstLine = lines[0];
          const hasHeader = firstLine.toLowerCase().includes('run_id') && firstLine.toLowerCase().includes('timestamp');

          let runIdIdx = 0, timestampIdx = 1;
          let startLine = 0;

          if(hasHeader){
            const header = firstLine.split(',');
            runIdIdx = header.findIndex(h => h.trim().toLowerCase() === 'run_id');
            timestampIdx = header.findIndex(h => h.trim().toLowerCase() === 'timestamp');
            if(runIdIdx === -1) runIdIdx = 0;
            if(timestampIdx === -1) timestampIdx = 1;
            startLine = 1;
          }

          for(let i=startLine; i<lines.length; i++){
            const row = parseCSVLine(lines[i]);
            if(row.length > Math.max(runIdIdx, timestampIdx)){
              const runId = row[runIdIdx] || '';
              const timestamp = row[timestampIdx] || '';
              if(runId && timestamp){
                // Extract date part (YYYY-MM-DD) from timestamp
                const datePart = timestamp.split(' ')[0];
                runIdByDateCache[datePart] = runId;
              }
            }
          }
        }
      }
    } catch(e) {
      console.warn('Failed to load run_id cache from CSV', e);
    }
    return runIdByDateCache;
  }

  // Update portfolio chart with selected range
  async function updatePortfolioChart(rangeKey){
    if(!lastFullData) return;

    // Ensure run_id cache is loaded
    await loadRunIdCache();

    const p = lastFullData.best_portfolio_details || {};
    const fullRaw = p.portfolio_timeseries || [];
    const full = sanitizePortfolioTimeseries(fullRaw);
    const sliced = sliceByRange(full, rangeKey);
    const labels = sliced.map(d=>d.ts);
    // final_value actually represents annual return in % (not portfolio monetary value)
    const values = sliced.map(d=>d.final_value);
    // Get run_id from cache by date, fallback to the entry's run_id or last run_id
    const runIds = sliced.map(d => {
      // First try from cached CSV data
      if(runIdByDateCache && runIdByDateCache[d.ts]) return runIdByDateCache[d.ts];
      // Then from the entry itself
      if(d.run_id) return d.run_id;
      // Fallback to current run_id
      return lastFullData.last_updated_run_id || 'N/A';
    });
    console.debug('updatePortfolioChart (pre-filter):', {rangeKey, rawPoints: fullRaw.length, groupedPoints: full.length, slicedPoints: labels.length});
    // filter out invalid points (ensure numeric final_value)
    const filteredLabels = [];
    const filteredValues = [];
    const filteredRunIds = [];
    for(let i=0;i<labels.length;i++){
      const v = values[i];
      const n = (v == null || v === '') ? NaN : Number(v);
      if(!isNaN(n) && isFinite(n)){
        filteredLabels.push(labels[i]);
        filteredValues.push(n);
        filteredRunIds.push(runIds[i] || 'N/A');
      }
    }
    if(filteredValues.length === 0){
      // clear chart and show message
      try{ if(portfolioChart && portfolioChart.destroy) portfolioChart.destroy(); }catch(e){}
      const c = document.getElementById('portfolioChart'); try{ const ctx = c.getContext('2d'); ctx.clearRect(0,0,c.width,c.height); }catch(e){}
      showChartError('portfolioChart','No portfolio timeseries data available');
      return;
    } else {
      // remove any previous chart error message
      const pc = document.getElementById('portfolioChart'); if(pc && pc.parentElement) pc.parentElement.querySelectorAll('.chart-error').forEach(n=>n.remove());
    }

    // Format labels for better display (dd/MM format)
    const formattedLabels = filteredLabels.map(ts => {
      try {
        const d = new Date(ts + 'T00:00:00');
        return d.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' });
      } catch(e) { return ts; }
    });

    try{
      const canvasEl = document.getElementById('portfolioChart');
      // ensure canvas pixel size matches layout
      try{ canvasEl.width = canvasEl.clientWidth; canvasEl.height = canvasEl.clientHeight; }catch(e){}
      const ctx = canvasEl.getContext('2d');
      // diagnostics
      try{
        const sample = filteredValues.slice(0,5);
        const last = filteredValues[filteredValues.length-1];
        const min = Math.min(...filteredValues); const max = Math.max(...filteredValues);
        console.info('Portfolio chart data:', { points: filteredValues.length, sample, last, min, max });
      }catch(e){ console.warn('Portfolio chart diagnostics failed', e); }
      if(typeof window.Chart === 'undefined'){
        drawLineFallback(canvasEl, filteredValues, '#2b8a3e'); return;
      }
      try{
        if(typeof Chart !== 'undefined' && Chart.getChart){
          const existing = Chart.getChart(canvasEl);
          if(existing){
            // Update data in-place to avoid re-creating charts bound to the same canvas
            try{
              existing.data.labels = formattedLabels;
              if(existing.data.datasets && existing.data.datasets[0]){
                existing.data.datasets[0].data = filteredValues;
                existing.data.datasets[0].runIds = filteredRunIds;
                existing.data.datasets[0].originalDates = filteredLabels;
              } else {
                existing.data.datasets = [{
                  label:'Retorno Anual (%)',
                  data: filteredValues,
                  borderColor:'#2b8a3e',
                  backgroundColor:'rgba(43,138,62,0.08)',
                  pointRadius: 3,
                  pointHoverRadius: 6,
                  fill:true,
                  runIds: filteredRunIds,
                  originalDates: filteredLabels
                }];
              }
              existing.update();
              portfolioChart = existing;
              return;
            }catch(e){ console.warn('Failed to update existing portfolio chart, will recreate', e); try{ existing.destroy(); }catch(e){} }
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
            pointRadius: 3,
            pointHoverRadius: 6,
            fill:true,
            runIds: filteredRunIds,
            originalDates: filteredLabels
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          interaction: {
            intersect: false,
            mode: 'index'
          },
          plugins: {
            legend: { display: true, position: 'top', labels: { color: '#cbd5e1' } },
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
                    const d = new Date(originalDate + 'T00:00:00');
                    return 'Data: ' + d.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit', year: 'numeric' });
                  } catch(e) { return 'Data: ' + originalDate; }
                },
                label: function(context) {
                  const value = context.parsed.y;
                  return 'Retorno Anual: ' + value.toFixed(2) + '%';
                },
                afterLabel: function(context) {
                  const idx = context.dataIndex;
                  const runId = context.dataset.runIds?.[idx] || 'N/A';
                  return 'Run ID: ' + runId;
                }
              }
            }
          },
          scales: {
            x: {
              display: true,
              grid: { color: 'rgba(71,85,105,0.3)' },
              ticks: {
                color: '#94a3b8',
                maxRotation: 0,
                autoSkip: true,
                maxTicksLimit: 8,
                font: { size: 11 }
              },
              title: {
                display: true,
                text: 'Data',
                color: '#cbd5e1'
              }
            },
            y: {
              display: true,
              grid: { color: 'rgba(71,85,105,0.3)' },
              title: { display: true, text: 'Retorno Anual (%)', color: '#cbd5e1' },
              ticks: {
                color: '#94a3b8',
                callback: function(val){
                  try{ const n = Number(val); if(isNaN(n)) return val; return n.toFixed(1) + '%'; }catch(e){ return val; }
                }
              }
            }
          }
        }
      });
    }catch(err){
      console.error('Portfolio chart rendering error', err);
      showChartError('portfolioChart','Chart render error');
    }
  }

  // Render holdings table with badges and sparklines
  function renderHoldingsTable(data){
    const p = data.best_portfolio_details || {};
    const stocks = p.stocks || []; const weights = p.weights || [];
    const holdings_meta = p.holdings_meta || {};
    const benchmark_pe = (p.momentum_valuation && p.momentum_valuation.benchmark_forward_pe) || null;

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
      tdFpe.textContent = (fpe==null || isNaN(Number(fpe))) ? 'n/a' : Number(fpe).toFixed(1);
      // latest price cell
      const tdLatestPrice = document.createElement('td');
      const latestPrice = meta.currentPrice;
      tdLatestPrice.textContent = (latestPrice==null || isNaN(Number(latestPrice))) ? 'n/a' : 'R$ ' + Number(latestPrice).toFixed(2);
      // target price cell
      const tdTargetPrice = document.createElement('td');
      const targetPrice = meta.targetPrice;
      tdTargetPrice.textContent = (targetPrice==null || isNaN(Number(targetPrice))) ? 'n/a' : 'R$ ' + Number(targetPrice).toFixed(2);
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

  // render everything
  async function renderAll(data){
    // populate top meta block: only Run ID and Last updated (now styled as footnote)
    lastFullData = data;
    if(els.runId) els.runId.textContent = data.last_updated_run_id || '—';
    if(els.lastUpdated) els.lastUpdated.textContent = data.last_updated_timestamp || '—';
    // populate table footnote with last run date
    if(els.tableRunDate) els.tableRunDate.textContent = data.last_updated_timestamp || '—';
    const p = data.best_portfolio_details || {};

    // KPIs and other sections
    renderKPIs(data);
    renderHoldingsTable(data);
    renderTreemap(data);
    await renderGA(data);
    await renderVolatilityChart(data);

    // default portfolio range: all
    await updatePortfolioChart('all');
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
      // Update the chart with new range
      await updatePortfolioChart(range);
    });
  });

  // initial load
  fetchIfChanged(); loop();
})();
