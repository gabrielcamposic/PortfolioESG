(function(){
  const PATH = './data/performance_attribution.json';
  const POLL = 10000;
  const els = {
    total: document.getElementById('total'),
    bars: document.getElementById('bars'),
    list: document.getElementById('list'),
    lastFetch: document.getElementById('lastFetch'),
    interval: document.getElementById('interval'),
    refresh: document.getElementById('refresh'),
    download: document.getElementById('download')
  };
  let lastETag = null, lastModified = null, polling = true;
  els.interval.textContent = Math.round(POLL/1000);

  function fmt(v){ return v==null? '—' : Number(v).toFixed(4); }

  function render(data){
    els.total.textContent = fmt(data.total_active_return);
    const items = [
      {k:'allocation_effect', label:'Allocation Effect'},
      {k:'selection_effect', label:'Selection Effect'},
      {k:'interaction_effect', label:'Interaction Effect'}
    ];
    // bars
    els.bars.innerHTML = '';
    const maxAbs = Math.max(...items.map(it=>Math.abs(data[it.k]||0)), 0.0000001);
    for(const it of items){
      const v = data[it.k]||0;
      const pct = Math.abs(v)/maxAbs;
      const width = Math.max(6, Math.round(pct*320));
      const div = document.createElement('div');
      div.className = 'bar ' + (v>=0? 'positive' : 'negative');
      div.style.width = width + 'px';
      div.textContent = `${it.label} ${fmt(v)}`;
      els.bars.appendChild(div);
    }

    // list
    els.list.innerHTML = '';
    for(const it of items){
      const v = data[it.k];
      const li = document.createElement('li');
      const l = document.createElement('div'); l.textContent = it.label;
      const r = document.createElement('div'); r.textContent = fmt(v);
      li.appendChild(l); li.appendChild(r);
      els.list.appendChild(li);
    }

    els.download.href = PATH + '?_=' + Date.now();
  }

  async function fetchIfChanged(){
    try{
      const head = await fetch(PATH, {method:'HEAD', cache:'no-store'});
      if(!head.ok){ /* fallback */ }
      const etag = head.headers.get('ETag');
      const lm = head.headers.get('Last-Modified');
      if(etag && lastETag === etag){ els.lastFetch.textContent = new Date().toLocaleTimeString(); return; }
      if(!etag && lm && lastModified === lm){ els.lastFetch.textContent = new Date().toLocaleTimeString(); return; }
      const resp = await fetch(PATH + '?_=' + Date.now(), {cache:'no-store'});
      if(!resp.ok) throw new Error('fetch failed '+resp.status);
      const data = await resp.json();
      render(data);
      lastETag = resp.headers.get('ETag') || lastETag;
      lastModified = resp.headers.get('Last-Modified') || lastModified;
      els.lastFetch.textContent = new Date().toLocaleTimeString();
    }catch(e){
      console.error('fetch err', e);
      els.lastFetch.textContent = 'error';
    }
  }

  els.refresh.addEventListener('click', ()=> fetchIfChanged());
  fetchIfChanged();
  (function loop(){ if(!polling) return; setTimeout(async ()=>{ await fetchIfChanged(); loop(); }, POLL); })();
})();
