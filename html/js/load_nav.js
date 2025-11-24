(function(){
  async function loadNav(){
    try{
      const resp = await fetch('./nav.html', {cache:'no-store'});
      if(!resp.ok) return;
      const html = await resp.text();
      const frag = document.createElement('div'); frag.innerHTML = html;
      // Insert at top of body
      const navEl = frag.firstElementChild;
      document.body.insertBefore(navEl, document.body.firstChild);
      // mark active link based on current pathname
      const path = location.pathname.split('/').pop() || 'latest_run_summary.html';
      const links = document.querySelectorAll('.site-nav .nav-link');
      links.forEach(a=> a.classList.toggle('active', a.getAttribute('href') === './'+path));

      // hook up nav toggle (hamburger) for small screens
      const toggle = document.querySelector('.site-nav .nav-toggle');
      const menu = document.querySelector('.site-nav .menu');
      if(toggle && menu){
        toggle.addEventListener('click', ()=>{
          const open = menu.classList.toggle('open');
          toggle.setAttribute('aria-expanded', String(open));
        });
        // close menu when a link is clicked (use capture to ensure it runs before navigation)
        links.forEach(a => a.addEventListener('click', ()=>{ if(menu.classList.contains('open')){ menu.classList.remove('open'); toggle.setAttribute('aria-expanded','false'); } }));
        // close when clicking outside menu
        document.addEventListener('click', (e)=>{
          if(!menu.contains(e.target) && !toggle.contains(e.target) && menu.classList.contains('open')){
            menu.classList.remove('open'); toggle.setAttribute('aria-expanded','false');
          }
        });
      }
    }catch(err){
      console.error('failed to load nav', err);
    }
  }
  if(document.readyState === 'loading') document.addEventListener('DOMContentLoaded', loadNav); else loadNav();
})();
