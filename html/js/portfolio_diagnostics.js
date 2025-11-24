(function(){
  const PATH = './data/portfolio_diagnostics.json';
  const POLL = 10000;
  const els = {
    momentum_signal_strength: document.getElementById('momentum_signal_strength'),
    momentum_bar: document.getElementById('momentum_bar'),
    forward_pe_implied_upside: document.getElementById('forward_pe_implied_upside'),
    weighted_dividend_yield: document.getElementById('weighted_dividend_yield'),
    turnover: document.getElementById('turnover'),
    liquidity_score: document.getElementById('liquidity_score'),
    tracking_error: document.getElementById('tracking_error'),
    information_ratio: document.getElementById('information_ratio'),
    lastFetch: document.getElementById('lastFetch'),
    interval: document.getElementById('interval'),
    refreshBtn: document.getElementById('refreshBtn'),
    downloadJson: document.getElementById('downloadJson')
  };

  let lastETag = null, lastModified = null;
  els.interval.textContent = Math.round(POLL/1000);

  function pct(v){ return (Number(v)*100).toFixed(2) + '%'; }
  function fmt(v){ return v==null? '—' : Number(v).toLocaleString(); }

  function render(data){
    els.momentum_signal_strength.textContent = data.momentum_signal_strength != null ? Number(data.momentum_signal_strength).toFixed(4) : '—';
    // momentum bar: assume range -1 .. +1 -> map to 0..100
    const ms = Number(data.momentum_signal_strength || 0);
    const posPct = Math.round((ms + 1)/2 * 100);
    els.momentum_bar.style.width = posPct + '%';

    els.forward_pe_implied_upside.textContent = data.forward_pe_implied_upside != null ? (Number(data.forward_pe_implied_upside)*100).toFixed(2) + '%' : '—';
    els.weighted_dividend_yield.textContent = data.weighted_dividend_yield != null ? Number(data.weighted_dividend_yield).toLocaleString() : '—';
    els.turnover.textContent = data.turnover != null ? (Number(data.turnover)*100).toFixed(2) + '%' : '—';
    els.liquidity_score.textContent = data.liquidity_score != null ? Number(data.liquidity_score).toLocaleString() : '—';
    els.tracking_error.textContent = data.tracking_error != null ? (Number(data.tracking_error)*100).toFixed(2) + '%' : '—';
    els.information_ratio.textContent = data.information_ratio != null ? Number(data.information_ratio).toFixed(4) : '—';

    // update download link to avoid caching
    els.downloadJson.href = PATH + '?_=' + Date.now();
  }

  async function fetchIfChanged(){
    try{
      const head = await fetch(PATH, {method:'HEAD', cache:'no-store'});
      if(head && head.ok){
        const etag = head.headers.get('ETag');
        const lm = head.headers.get('Last-Modified');
        if(etag && etag === lastETag){ els.lastFetch.textContent = new Date().toLocaleTimeString(); return; }
        if(!etag && lm && lm === lastModified){ els.lastFetch.textContent = new Date().toLocaleTimeString(); return; }
      }
      const resp = await fetch(PATH + '?_=' + Date.now(), {cache:'no-store'});
      if(!resp.ok) throw new Error('fetch failed '+resp.status);
      const data = await resp.json();
      render(data);
      lastETag = resp.headers.get('ETag') || lastETag;
      lastModified = resp.headers.get('Last-Modified') || lastModified;
      els.lastFetch.textContent = new Date().toLocaleTimeString();
    }catch(err){
      console.error('fetch err', err);
      els.lastFetch.textContent = 'error';
    }
  }

  els.refreshBtn.addEventListener('click', ()=> fetchIfChanged());
  // initial
  fetchIfChanged();
  (function loop(){ setTimeout(async ()=>{ await fetchIfChanged(); loop(); }, POLL); })();
})();

