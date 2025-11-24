(function(){
  // Data Explorer: support CSV and plain text. Renders table, bar chart (sector PE) and correlation heatmap.
  const fileButtons = Array.from(document.querySelectorAll('.file-btn'));
  const refreshBtn = document.getElementById('refresh');
  const downloadLink = document.getElementById('download');
  const textArea = document.getElementById('textArea');
  const textPreview = document.getElementById('textPreview');
  const tableArea = document.getElementById('tableArea');
  const dataTable = document.getElementById('dataTable');
  const tableHead = dataTable.querySelector('thead');
  const tableBody = dataTable.querySelector('tbody');
  const searchInput = document.getElementById('searchInput');
  const clearSearch = document.getElementById('clearSearch');
  const columnSelect = document.getElementById('columnSelect');
  const chartArea = document.getElementById('chartArea');
  const chartContainer = document.getElementById('chartContainer');

  let currentFile = './data/scored_stocks.csv';
  let currentData = null; // {type:'csv'|'txt', raw:..., rows:[..], cols:[..]}

  fileButtons.forEach(btn=> btn.addEventListener('click', ()=>{
    fileButtons.forEach(b=>b.classList.remove('active'));
    btn.classList.add('active');
    currentFile = btn.dataset.file;
    downloadLink.href = currentFile;
    loadCurrent();
  }));

  refreshBtn.addEventListener('click', ()=> loadCurrent());
  clearSearch.addEventListener('click', ()=> { searchInput.value=''; renderTable(currentData); });
  searchInput.addEventListener('input', ()=> renderTable(currentData));
  columnSelect.addEventListener('change', ()=> renderTable(currentData));

  async function loadCurrent(){
    // normalize path: if starts with ../parameters, it should be accessible relative to html/ page
    const url = currentFile.replace('../','');
    try{
      const resp = await fetch(url, {cache:'no-store'});
      if(!resp.ok) throw new Error('HTTP '+resp.status);
      const text = await resp.text();
      if(currentFile.endsWith('.csv')){
        const parsed = parseCSV(text);
        currentData = {type:'csv', raw:text, rows:parsed.rows, cols:parsed.cols};
      } else {
        currentData = {type:'txt', raw:text};
      }
      renderCurrent();
    }catch(err){
      console.error('load err', err);
      textArea.style.display='block'; textPreview.textContent = 'Error loading file: '+err.message; textArea.scrollIntoView();
    }
  }

  function parseCSV(text){
    // simple CSV parser that handles quoted commas but not all edge cases. Good for our files.
    const lines = text.split(/\r?\n/).filter(l=>l.length>0);
    if(lines.length===0) return {cols:[], rows:[]};
    const cols = splitCSVLine(lines[0]);
    const rows = [];
    for(let i=1;i<lines.length;i++){
      const parts = splitCSVLine(lines[i]);
      // if row length differs, pad
      while(parts.length < cols.length) parts.push('');
      rows.push(parts);
    }
    return {cols, rows};
  }
  function splitCSVLine(line){
    const res = []; let cur=''; let inQuotes=false;
    for(let i=0;i<line.length;i++){
      const ch = line[i];
      if(ch==='"') { inQuotes = !inQuotes; continue; }
      if(ch===',' && !inQuotes){ res.push(cur); cur=''; continue; }
      cur += ch;
    }
    res.push(cur);
    return res.map(s=>s.trim());
  }

  function renderCurrent(){
    // hide all
    textArea.style.display='none'; tableArea.style.display='none'; chartArea.style.display='none';
    chartContainer.innerHTML='';

    if(currentData.type === 'txt'){
      textArea.style.display='block';
      textPreview.textContent = currentData.raw.slice(0,20000);
      return;
    }

    // csv
    // for sector_pe.csv -> bar chart; for correlation_matrix.csv -> heatmap
    const fname = currentFile.split('/').pop();
    if(fname === 'sector_pe.csv'){
      chartArea.style.display='block'; renderSectorPE(currentData); return;
    }
    if(fname === 'correlation_matrix.csv'){
      chartArea.style.display='block'; renderCorrelation(currentData); return;
    }

    // default: render table
    tableArea.style.display='block'; renderTable(currentData);
  }

  function renderTable(data){
    // data: {cols:[], rows:[[]]}
    const cols = data.cols; const rows = data.rows;
    // build header
    tableHead.innerHTML=''; tableBody.innerHTML=''; columnSelect.innerHTML='';
    const tr = document.createElement('tr');
    cols.forEach((c,ci)=>{
      const th = document.createElement('th'); th.textContent = c || `col${ci}`; tr.appendChild(th);
      const op = document.createElement('option'); op.value = ci; op.textContent = c || `col${ci}`; columnSelect.appendChild(op);
    });
    tableHead.appendChild(tr);

    const filter = (searchInput.value||'').trim().toLowerCase();
    const colIdx = columnSelect.value !== '' ? Number(columnSelect.value) : -1;

    const matched = [];
    for(let r=0;r<rows.length;r++){
      const row = rows[r];
      let ok = true;
      if(filter){
        if(colIdx>=0){ ok = String(row[colIdx]||'').toLowerCase().includes(filter); }
        else { ok = row.some(c=>String(c||'').toLowerCase().includes(filter)); }
      }
      if(ok) matched.push(row);
    }

    // render up to 5000 rows for performance
    const MAX = 5000; const limited = matched.slice(0, MAX);
    for(const row of limited){
      const tr = document.createElement('tr');
      for(let i=0;i<cols.length;i++){
        const td = document.createElement('td'); td.textContent = row[i] || ''; tr.appendChild(td);
      }
      tableBody.appendChild(tr);
    }
    if(matched.length>MAX){
      const trc = document.createElement('tr'); const td = document.createElement('td'); td.colSpan = cols.length; td.className='small-muted'; td.textContent = `Showing ${MAX} of ${matched.length} rows. Refine search to see more.`; trc.appendChild(td); tableBody.appendChild(trc);
    }
  }

  function renderSectorPE(data){
    // expect cols: ticker, sector, forward_pe (or similar). We'll try to identify columns.
    const cols = data.cols; const rows = data.rows;
    // heuristics for PE column
    const lowerCols = cols.map(c=>c.toLowerCase());
    const tickIdx = lowerCols.findIndex(c=>/ticker|symbol|stock/.test(c));
    const sectorIdx = lowerCols.findIndex(c=>/sector/.test(c));
    const peIdx = lowerCols.findIndex(c=>/pe|forward_pe|forward pe|forward_pe_ratio/.test(c));

    const sectors = {};
    for(const r of rows){
      const sector = (r[sectorIdx] || 'Unknown').trim()||'Unknown';
      const pe = Number((r[peIdx] || '').replace(',','.')) || NaN;
      if(!Number.isFinite(pe)) continue;
      if(!sectors[sector]) sectors[sector] = {sum:0, count:0};
      sectors[sector].sum += pe; sectors[sector].count += 1;
    }
    const list = Object.entries(sectors).map(([k,v])=>({sector:k, avg:v.sum/v.count, count:v.count})).sort((a,b)=>b.avg-a.avg);

    chartContainer.innerHTML = '';
    const chart = document.createElement('div'); chart.className='bar-chart';
    list.forEach(item=>{
      const it = document.createElement('div'); it.className='bar-item';
      const bar = document.createElement('div'); bar.className='bar';
      bar.style.height = Math.max(6, Math.round((item.avg / (list[0].avg||1)) * 100)) + '%';
      const lbl = document.createElement('div'); lbl.textContent = item.sector; lbl.style.fontSize='12px'; lbl.style.marginTop='8px';
      const val = document.createElement('div'); val.textContent = Number(item.avg).toFixed(2); val.style.fontSize='11px'; val.style.opacity=0.8;
      it.appendChild(bar); it.appendChild(lbl); it.appendChild(val); chart.appendChild(it);
    });
    chartContainer.appendChild(chart);
  }

  function renderCorrelation(data){
    // assume first row has header of tickers, first column also contains tickers
    const cols = data.cols; const rows = data.rows;
    // build matrix
    const headers = cols.slice(1);
    const matrix = rows.map(r=> r.slice(1).map(v=>Number(v)));
    // create table
    chartContainer.innerHTML = '';
    const wrap = document.createElement('div'); wrap.className='heatmap';
    const table = document.createElement('table');
    const thead = document.createElement('thead'); const trh = document.createElement('tr'); trh.appendChild(document.createElement('th'));
    headers.forEach(h=>{ const th = document.createElement('th'); th.textContent = h; trh.appendChild(th); }); thead.appendChild(trh); table.appendChild(thead);
    const tbody = document.createElement('tbody');
    for(let i=0;i<matrix.length;i++){
      const tr = document.createElement('tr'); const th = document.createElement('th'); th.textContent = rows[i][0]; tr.appendChild(th);
      for(let j=0;j<matrix[i].length;j++){
        const td = document.createElement('td'); const v = matrix[i][j]; td.textContent = (Number.isFinite(v)? v.toFixed(3): '');
        const pct = Math.max(0, Math.min(1, (v+1)/2)); // map -1..1 to 0..1
        const color = `rgba(${Math.round(255*(1-pct))}, ${Math.round(255*pct)}, 120, 0.95)`;
        td.style.background = color; td.style.color = pct>0.6? '#042837':'#eaf6f1'; tr.appendChild(td);
      }
      tbody.appendChild(tr);
    }
    table.appendChild(tbody); wrap.appendChild(table); chartContainer.appendChild(wrap);
  }

  // initial load
  loadCurrent();
})();

