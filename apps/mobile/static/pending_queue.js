/* Phone-side outbox. A submission is written here BEFORE it is sent and removed only after the
   server confirms it (HTTP 200 + ok:true). Retries reuse the same client_submission_id, so the
   server returns the original record instead of creating a duplicate. */
(function(){
const DB='sl_audit_queue',STORE='pending';
let dbp=null,mem=new Map();
function open(){
  if(dbp)return dbp;
  dbp=new Promise((res,rej)=>{
    if(!window.indexedDB){rej(new Error('no indexedDB'));return;}
    const r=indexedDB.open(DB,1);
    r.onupgradeneeded=()=>r.result.createObjectStore(STORE,{keyPath:'id'});
    r.onsuccess=()=>res(r.result);r.onerror=()=>rej(r.error);
  }).catch(e=>{console.warn('IndexedDB unavailable, outbox is memory-only',e);return null;});
  return dbp;
}
function tx(mode,fn){return open().then(db=>{
  if(!db)return fn(null);
  return new Promise((res,rej)=>{const t=db.transaction(STORE,mode),s=t.objectStore(STORE);let out;
    const rq=fn(s);if(rq)rq.onsuccess=()=>{out=rq.result};t.oncomplete=()=>res(out);t.onerror=()=>rej(t.error);t.onabort=()=>rej(t.error);});
});}
const Q={
  async put(rec){const db=await open();if(!db){mem.set(rec.id,rec);return;}await tx('readwrite',s=>s.put(rec));},
  async del(id){const db=await open();if(!db){mem.delete(id);return;}await tx('readwrite',s=>s.delete(id));},
  async all(){const db=await open();if(!db)return [...mem.values()];return (await tx('readonly',s=>s.getAll()))||[];},
  newId(){return (window.crypto&&crypto.randomUUID)?crypto.randomUUID():('c'+Date.now().toString(36)+Math.random().toString(36).slice(2,10));},
  build(rec){const fd=new FormData();rec.fields.forEach(([k,v])=>fd.append(k,v));rec.photos.forEach(p=>fd.append('photos',p.blob,p.name));return fd;},
  /* returns {state:'saved',data} | {state:'pending',error} | {state:'failed',error} */
  async send(rec){
    rec.attempts=(rec.attempts||0)+1;rec.lastTry=new Date().toISOString();
    const ctl=new AbortController(),timer=setTimeout(()=>ctl.abort(),60000);
    try{
      const r=await fetch('/api/v2/audit',{method:'POST',body:Q.build(rec),signal:ctl.signal,credentials:'same-origin'});
      let d=null;try{d=await r.json();}catch(e){}
      if(r.ok&&d&&d.ok){await Q.del(rec.id);return {state:'saved',data:d};}
      if(r.status>=500||!d){rec.state='pending';rec.error='Server problem ('+r.status+'). Kept on this phone - retry.';await Q.put(rec);return {state:'pending',error:rec.error};}
      rec.state='failed';rec.error=(d&&d.error)||('Rejected ('+r.status+')');await Q.put(rec);return {state:'failed',error:rec.error,status:r.status};
    }catch(e){
      rec.state='pending';rec.error=e.name==='AbortError'?'No answer from the server within 60 s. Kept on this phone - retry.':'No connection to the server. Kept on this phone - retry when online.';
      await Q.put(rec);return {state:'pending',error:rec.error};
    }finally{clearTimeout(timer);}
  },
  async flush(onChange){
    if(Q._flushing)return;Q._flushing=true;
    try{for(const rec of await Q.all()){if(rec.state==='failed')continue;await Q.send(rec);if(onChange)onChange();}}
    finally{Q._flushing=false;}
  },
  esc(x){return String(x==null?'':x).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));},
  async renderList(el){
    if(!el)return;
    const rows=await Q.all();
    if(!rows.length){el.innerHTML='<div class="muted">Nothing waiting. Every submission on this phone has been confirmed by the server.</div>';return;}
    el.innerHTML=rows.sort((a,b)=>a.created<b.created?1:-1).map(r=>`<div class="mobile-row pend ${r.state}"><div><b>${Q.esc(r.label)}</b><small>${r.state==='failed'?'REJECTED - needs correction':'NOT SAVED YET - waiting to send'} · ${r.photos.length} photo(s) · tries ${r.attempts||0}</small><small>${Q.esc(r.error||'')}</small></div><div class="mobile-row-right">${r.state==='failed'?'':'<button class="button" data-retry="'+Q.esc(r.id)+'">Retry</button>'}<button class="button" data-drop="${Q.esc(r.id)}">Discard</button></div></div>`).join('');
    el.querySelectorAll('[data-retry]').forEach(b=>b.onclick=async()=>{b.disabled=true;const rec=(await Q.all()).find(x=>x.id===b.dataset.retry);if(rec)await Q.send(rec);Q.renderList(el);});
    el.querySelectorAll('[data-drop]').forEach(b=>b.onclick=async()=>{if(confirm('Discard this unsent submission? Its photos and quantities will be lost.')){await Q.del(b.dataset.drop);Q.renderList(el);}});
  },
  async renderBanner(el){
    if(!el)return;await Q.flush();const rows=await Q.all();
    if(!rows.length){el.classList.add('hidden');return;}
    el.classList.remove('hidden');
    el.innerHTML='<div class="alert danger"><b>'+rows.length+' submission(s) NOT saved on the server.</b> <a href="/mobile/submissions">Review / retry</a></div>';
  }
};
window.addEventListener('online',()=>Q.flush());
window.SLQueue=Q;
})();
