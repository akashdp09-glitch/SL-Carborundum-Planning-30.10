(function(){
const input=document.getElementById('scanInput'), result=document.getElementById('scanResult'), actions=document.getElementById('actions'), qtyBox=document.getElementById('qtyBox'), qtyInput=document.getElementById('qtyInput'), reasonBox=document.getElementById('reasonBox'), reasonInput=document.getElementById('reasonInput');
let current=null; let station=window.STATION;
function showResult(data){result.classList.remove('hidden'); result.innerHTML=`<b>${data.wo.production_code}</b><br><b>${data.wo.product_code}</b><br>Customer: ${data.wo.customer_name||'—'}<br>Qty: ${data.wo.qty}<br>Current: <b>${data.status}</b><br>Process: ${data.current_process||'—'}<br>Location: ${data.current_location||'—'}<br>Produced: ${data.produced} · Remaining: ${data.remaining}`; actions.classList.remove('hidden');}
function showError(msg){result.classList.remove('hidden');result.innerHTML=`<div class="alert danger">${msg}</div>`}
function normalizeScanCode(value){
  const raw=(value||'').trim();
  try {
    const u=new URL(raw, window.location.origin);
    const parts=u.pathname.split('/').filter(Boolean);
    const qIndex=parts.indexOf('q');
    if(qIndex>=0 && parts[qIndex+1]) return parts[qIndex+1];
  } catch(e) {}
  return raw;
}
async function loadWO(code){code=normalizeScanCode(code); const r=await fetch('/api/wo/'+encodeURIComponent(code)); const d=await r.json(); if(!d.ok){showError(d.error); current=null; return} current=d; showResult(d)}
input.addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault(); const code=input.value.trim(); if(code) loadWO(code); input.value='';}});
document.querySelectorAll('[data-reason]').forEach(b=>b.addEventListener('click',()=>{reasonInput.value=b.dataset.reason;}));
document.querySelectorAll('[data-event]').forEach(b=>b.addEventListener('click',async()=>{
  if(!current){showError('Scan a Work Order first');return}
  const type=b.dataset.event;
  if(!station){showError('This computer has no station configured. Use /scan?station=GR-01, or ask admin.');return}
  if(['PARTIAL_COMPLETE','COMPLETE','REWORK'].includes(type)){qtyBox.classList.remove('hidden'); if(type==='COMPLETE' && current.wo.qty) qtyInput.value=current.wo.qty;}
  else qtyBox.classList.add('hidden');
  if(['HOLD','REWORK'].includes(type)) reasonBox.classList.remove('hidden'); else reasonBox.classList.add('hidden');
  if(['PARTIAL_COMPLETE','COMPLETE','REWORK'].includes(type) && (!qtyInput.value || Number(qtyInput.value)<=0)){showError('Enter quantity');return}
  const payload={wo_id:current.wo.wo_id,event_type:type,terminal_code:station,qty:qtyInput.value?Number(qtyInput.value):null,reason:reasonInput.value||'',notes:''};
  const r=await fetch('/api/scan',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}); const d=await r.json();
  if(!d.ok){showError(d.error);return}
  showError(''); result.classList.remove('hidden'); result.innerHTML=`<div class="alert good">Saved: ${type}</div>`; current={...current,status:d.status,current_process:d.current_process,current_location:d.current_location,produced:d.produced,remaining:d.remaining};
  setTimeout(()=>{input.focus();input.value='';qtyInput.value='';reasonInput.value='';},250); 
}));
if(input) input.focus();
})();
