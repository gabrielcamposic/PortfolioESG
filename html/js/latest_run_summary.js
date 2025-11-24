(function(){
  const JSON_PATH = 'data/latest_run_summary.json';
  const POLL_INTERVAL = 10000; // ms

  const els = {
    runId: document.getElementById('runId'),
    lastUpdated: document.getElementById('lastUpdated'),
    sharpe: document.getElementById('sharpe'),
    expRet: document.getElementById('expRet'),
    vol: document.getElementById('vol'),
    stocksTableBody: document.querySelector('#stocksTable tbody'),
    pe: document.getElementById('pe'),
    momentum: document.getElementById('momentum'),
    bpe: document.getElementById('bpe'),
    sectorList: document.getElementById('sectorList'),
    concentrationList: document.getElementById('concentrationList'),
    lastFetch: document.getElementById('lastFetch'),
    interval: document.getElementById('interval'),
    refreshBtn: document.getElementById('refreshBtn'),
    downloadJson: document.getElementById('downloadJson')
  };

  let lastETag = null;
  let lastModified = null;
  let polling = true;

  els.interval.textContent = Math.round(POLL_INTERVAL/1000);

  function formatPct(v){
    if(v===null || v===undefined) return '—';
    return (Number(v).toFixed(2)) + '%';
  }

  function clearTable(){
    els.stocksTableBody.innerHTML = '';
  }

  function render(data){
    const p = data.best_portfolio_details || {};
    els.runId.textContent = data.last_updated_run_id || '—';
    els.lastUpdated.textContent = data.last_updated_timestamp || '—';
    els.sharpe.textContent = p.sharpe_ratio != null ? Number(p.sharpe_ratio).toFixed(4) : '—';
    els.expRet.textContent = p.expected_return_annual_pct != null ? Number(p.expected_return_annual_pct).toFixed(2) + '%' : '—';
    els.vol.textContent = p.expected_volatility_annual_pct != null ? Number(p.expected_volatility_annual_pct).toFixed(2) + '%' : '—';

    clearTable();
    const stocks = p.stocks || [];
    const weights = p.weights || [];
    for(let i=0;i<stocks.length;i++){
      const tr = document.createElement('tr');
      const th = document.createElement('th'); th.textContent = i+1;
      const td1 = document.createElement('td'); td1.textContent = stocks[i] || '—';
      const td2 = document.createElement('td'); td2.textContent = weights[i]!=null ? (Number(weights[i])*100).toFixed(2)+'%' : '—';
      tr.appendChild(th); tr.appendChild(td1); tr.appendChild(td2);
      els.stocksTableBody.appendChild(tr);
    }

    els.pe.textContent = p.portfolio_weighted_pe != null ? Number(p.portfolio_weighted_pe).toFixed(2) : '—';
    const mom = p.momentum_valuation && p.momentum_valuation.portfolio_momentum;
    els.momentum.textContent = mom != null ? Number(mom).toFixed(4) : '—';
    const bpe = p.momentum_valuation && p.momentum_valuation.benchmark_forward_pe;
    els.bpe.textContent = bpe != null ? Number(bpe).toFixed(2) : '—';

    // sectors
    els.sectorList.innerHTML = '';
    const sectors = p.sector_exposure || {};
    const keys = Object.keys(sectors).sort((a,b)=>sectors[b]-sectors[a]);
    for(const k of keys){
      const li = document.createElement('li');
      li.textContent = `${k}: ${(Number(sectors[k])*100).toFixed(2)}%`;
      els.sectorList.appendChild(li);
    }

    // concentration
    els.concentrationList.innerHTML = '';
    const cr = p.concentration_risk || {};
    if(Object.keys(cr).length===0){
      const li = document.createElement('li'); li.textContent = '—'; els.concentrationList.appendChild(li);
    } else {
      if(cr.hhi!=null){ const li = document.createElement('li'); li.textContent = `HHI: ${Number(cr.hhi).toFixed(4)}`; els.concentrationList.appendChild(li); }
      if(cr.top_5_holdings_pct!=null){ const li = document.createElement('li'); li.textContent = `Top 5 holdings %: ${(Number(cr.top_5_holdings_pct)*100).toFixed(2)}%`; els.concentrationList.appendChild(li); }
      if(Array.isArray(cr.top_5_holdings)){
        for(const h of cr.top_5_holdings){
          const li = document.createElement('li'); li.textContent = `${h.stock}: ${(Number(h.weight)*100).toFixed(2)}%`; els.concentrationList.appendChild(li);
        }
      }
    }

    // update download link to avoid caching issues
    els.downloadJson.href = JSON_PATH + '?_=' + Date.now();
  }

  async function fetchIfChanged(){
    try{
      const headResp = await fetch(JSON_PATH, {method:'HEAD', cache:'no-store'});
      if(!headResp.ok){
        console.warn('HEAD fetch failed', headResp.status);
        // still try GET once
      }
      const etag = headResp.headers.get('ETag');
      const lm = headResp.headers.get('Last-Modified');
      // if we have ETag/Last-Modified and they match previous, skip
      if(etag && lastETag === etag){
        els.lastFetch.textContent = new Date().toLocaleTimeString();
        return; // no change
      }
      if(!etag && lm && lastModified === lm){
        els.lastFetch.textContent = new Date().toLocaleTimeString();
        return;
      }

      // fetch body
      const resp = await fetch(JSON_PATH + '?_=' + Date.now(), {cache:'no-store'});
      if(!resp.ok) throw new Error('Failed to fetch JSON: '+resp.status);
      const data = await resp.json();
      render(data);
      lastETag = resp.headers.get('ETag') || lastETag;
      lastModified = resp.headers.get('Last-Modified') || lastModified;
      els.lastFetch.textContent = new Date().toLocaleTimeString();
    }catch(err){
      console.error('Fetch error', err);
      els.lastFetch.textContent = 'error';
    }
  }

  async function loop(){
    if(!polling) return;
    await fetchIfChanged();
    setTimeout(loop, POLL_INTERVAL);
  }

  els.refreshBtn.addEventListener('click', ()=>{ fetchIfChanged(); });

  // initial load
  fetchIfChanged();
  loop();
})();

