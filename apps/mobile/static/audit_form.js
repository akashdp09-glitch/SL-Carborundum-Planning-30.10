(function(){
const cfg=JSON.parse(document.getElementById('auditCfg').textContent);
const $=id=>document.getElementById(id),Q=window.SLQueue;
const form=$('auditForm'),result=$('auditResult'),submit=$('submitBtn');
let csid=Q.newId(),inFlight=false,gps={status:'NOT_REQUESTED'},photos=[],status=cfg.defaultStatus,unitVal=cfg.units[0]||'';

/* status buttons */
document.querySelectorAll('[data-status]').forEach(b=>b.onclick=()=>{status=b.dataset.status;document.querySelectorAll('[data-status]').forEach(x=>x.classList.toggle('selected',x===b));});
const first=document.querySelector('[data-status="'+status+'"]');if(first)first.classList.add('selected');
/* unit chips */
document.querySelectorAll('[data-unit]').forEach(b=>b.onclick=()=>{unitVal=b.dataset.unit;document.querySelectorAll('[data-unit]').forEach(x=>x.classList.toggle('selected',x===b));});
const u0=document.querySelector('[data-unit="'+unitVal+'"]');if(u0)u0.classList.add('selected');
/* quantity unknown */
const qty=$('qty'),qunk=$('qtyUnknown');
function syncQty(){qty.disabled=qunk.checked;if(qunk.checked)qty.value='';}
qunk.onchange=syncQty;
/* locations: building > section > position */
const L=cfg.locations,selB=$('locBuilding'),selS=$('locSection'),selP=$('locPosition'),manual=$('locText'),unkLoc=$('locUnknown');
const uniq=a=>[...new Set(a)];
function fill(sel,vals,ph){sel.innerHTML='<option value="">'+ph+'</option>'+vals.map(v=>'<option value="'+Q.esc(v)+'">'+(v===''?'(none)':Q.esc(v))+'</option>').join('');}
function onB(){fill(selS,uniq(L.filter(l=>l.building===selB.value).map(l=>l.section)).filter(Boolean),'Section / แผนก');onS();}
function onS(){fill(selP,uniq(L.filter(l=>l.building===selB.value&&l.section===selS.value).map(l=>l.position)).filter(Boolean),'Machine / rack / bin (optional)');}
fill(selB,uniq(L.map(l=>l.building)).filter(Boolean),'Building (optional)');
selB.onchange=onB;selS.onchange=onS;onB();
function chosenLocation(){
  if(!selS.value&&!selB.value&&!selP.value)return null;
  const m=L.find(l=>l.building===selB.value&&l.section===selS.value&&l.position===selP.value);
  return m?m.id:null;
}
if(cfg.prefillLocationId){const m=L.find(l=>l.id===cfg.prefillLocationId);if(m){selB.value=m.building;onB();selS.value=m.section;onS();selP.value=m.position;}}
/* GPS - permission based, never required, never used to identify indoor racks */
$('gpsBtn').onclick=()=>{
  const out=$('gpsOut');
  if(!navigator.geolocation){gps={status:'UNAVAILABLE'};out.textContent='GPS not supported on this device. Choose the location from the list.';return;}
  out.textContent='Asking for location…';
  navigator.geolocation.getCurrentPosition(p=>{gps={status:'CAPTURED',lat:p.coords.latitude,lon:p.coords.longitude,acc:p.coords.accuracy};out.textContent='GPS captured ±'+Math.round(p.coords.accuracy)+' m (outdoor guide only - still choose the rack/area).';},
    e=>{gps={status:e.code===1?'DENIED':'UNAVAILABLE'};out.textContent=e.code===1?'Location permission denied - choose the location from the list.':'GPS unavailable here - choose the location from the list.';},{enableHighAccuracy:true,timeout:10000,maximumAge:30000});
};
/* photos */
function addFiles(list){for(const f of list){if(photos.length>=cfg.maxPhotos)break;photos.push(f);}renderPhotos();}
function renderPhotos(){const box=$('photoPreview');box.innerHTML='';photos.forEach((f,i)=>{const w=document.createElement('div');w.className='ph';const im=document.createElement('img');im.className='audit-photo-thumb';im.alt='photo '+(i+1);im.src=URL.createObjectURL(f);const x=document.createElement('button');x.type='button';x.textContent='✕';x.setAttribute('aria-label','Remove photo');x.onclick=()=>{photos.splice(i,1);renderPhotos();};w.append(im,x);box.append(w);});$('photoCount').textContent=photos.length+' / '+cfg.maxPhotos;}
$('photoCam').onchange=e=>{addFiles(e.target.files);e.target.value='';};
$('photoGal').onchange=e=>{addFiles(e.target.files);e.target.value='';};

function collect(){
  const f=[['client_submission_id',csid],['mode',cfg.mode],['client_time',new Date().toISOString()],['status',status],['process',$('process').value.trim()],['notes',$('notes').value.trim()]];
  if(cfg.mode==='WO'){f.push(['wo_id',cfg.woId]);f.push(['batch_ref',$('batch').value.trim()]);}
  else{f.push(['description',$('desc').value.trim()]);f.push(['markings',$('marks').value.trim()]);}
  if(qunk.checked)f.push(['qty_unknown','1']);else if(qty.value!=='')f.push(['verified_qty',qty.value]);
  f.push(['qty_unit',unitVal]);
  const lid=chosenLocation();
  if(lid)f.push(['location_id',lid]);
  else if(manual.value.trim())f.push(['location_text',manual.value.trim()]);
  else if(unkLoc.checked)f.push(['location_unknown','1']);
  if($('locNotes').value.trim())f.push(['location_notes',$('locNotes').value.trim()]);
  f.push(['gps_status',gps.status]);if(gps.status==='CAPTURED'){f.push(['gps_lat',gps.lat],['gps_lon',gps.lon],['gps_accuracy_m',gps.acc]);}
  return f;
}
function localCheck(){
  if(!qunk.checked&&qty.value==='')return 'Enter the counted quantity or tick "Quantity unknown".';
  if(!chosenLocation()&&!manual.value.trim()&&!unkLoc.checked&&status!=='NOT_FOUND')return 'Choose the location, type it, or tick "Location unknown".';
  if(cfg.mode==='UNIDENTIFIED'){if(!photos.length)return 'Take at least one photo of the part.';if(!$('desc').value.trim()&&!$('marks').value.trim())return 'Add a description or the visible markings (write "none visible" if there are none).';}
  return '';
}
function show(msg,cls){result.className='result '+(cls||'');result.innerHTML=msg;result.scrollIntoView({block:'center',behavior:'smooth'});}

form.addEventListener('submit',async e=>{
  e.preventDefault();
  if(inFlight)return;                       /* double tap / repeated scan */
  const bad=localCheck();if(bad){show('⚠ '+Q.esc(bad),'bad');return;}
  inFlight=true;submit.disabled=true;submit.textContent='Sending… กำลังส่ง';
  const rec={id:csid,mode:cfg.mode,created:new Date().toISOString(),label:(cfg.mode==='WO'?cfg.woLabel+' · ':'Unidentified · ')+status,fields:collect(),photos:photos.map((f,i)=>({name:f.name||('photo'+(i+1)+'.jpg'),type:f.type,blob:f})),state:'pending',attempts:0};
  try{await Q.put(rec);}catch(err){}        /* outbox first, so a crash/offline never loses it */
  const r=await Q.send(rec);
  inFlight=false;submit.disabled=false;submit.textContent=cfg.submitLabel;
  if(r.state==='saved'){
    const d=r.data;
    show('<div class="ok-big">✔ Saved on the server</div><div><b>'+Q.esc(d.tracking_id)+'</b></div><div>Received '+Q.esc(d.server_received_at)+' (Bangkok)'+(d.duplicate?' · <b>already saved earlier - no duplicate created</b>':'')+(d.photos!==undefined?' · '+d.photos+' photo(s)':'')+'</div>'
      +'<a class="button operator-main-button" href="/mobile/part/'+encodeURIComponent(d.tracking_id)+'">Open record</a>'
      +(cfg.mode==='WO'?'<a class="button operator-main-button" href="/mobile/audit/'+encodeURIComponent(cfg.woId)+'">➕ Another location / batch for this WO</a>':'<a class="button operator-main-button" href="/mobile/unidentified">➕ Another unidentified part</a>')
      +(cfg.mode==='UNIDENTIFIED'?'<a class="button operator-main-button" target="_blank" href="/labels/print?id='+encodeURIComponent(d.tracking_id)+'">🖨 QR label for '+Q.esc(d.tracking_id)+'</a>':'')
      +'<a class="button operator-main-button" href="/mobile/scan">📷 Scan next</a>','good');
    form.classList.add('hidden');
  }else if(r.state==='pending'){
    show('<b>⚠ NOT saved on the server yet.</b><br>'+Q.esc(r.error)+'<br>Everything you entered is still here and also kept on this phone. <a href="/mobile/submissions">See pending submissions</a>. Tap the button again to retry - it will not create a duplicate.','bad');
  }else{
    show('<b>✖ Rejected:</b> '+Q.esc(r.error)+'<br>Correct it and send again.','bad');
  }
});
syncQty();
Q.flush();
})();
