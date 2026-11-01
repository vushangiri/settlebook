const device=document.querySelector('#device');
const csrf=()=>document.querySelector('meta[name="csrf-token"]').content;
async function theme(value){
 device.classList.toggle('dark',value==='dark'||(value==='system'&&matchMedia('(prefers-color-scheme:dark)').matches));
 try{localStorage.setItem('theme',value)}catch(e){}
 document.querySelector('#theme').textContent=device.classList.contains('dark')?'☀':'☾';
 if(document.querySelector('#unread'))try{await fetch('/api/theme',{method:'POST',headers:{'Content-Type':'application/json','X-CSRFToken':csrf()},body:JSON.stringify({theme:value})})}catch(e){}
}
document.querySelector('#theme').onclick=()=>theme(device.classList.contains('dark')?'light':'dark');
document.querySelector('#system-theme')?.addEventListener('click',()=>theme('system'));
matchMedia('(prefers-color-scheme:dark)').addEventListener('change',()=>{try{if(!localStorage.getItem('theme')||localStorage.getItem('theme')==='system')theme('system')}catch(e){}});
function connectivity(){const offline=!navigator.onLine;const n=document.querySelector('#network');n.hidden=!offline;n.textContent='You are offline. Financial submissions are disabled until reconnected.';document.querySelectorAll('form[method="post"] button').forEach(b=>{if(offline){if(!b.disabled){b.dataset.offline='1';b.disabled=true}}else if(b.dataset.offline){b.disabled=false;delete b.dataset.offline}})}
addEventListener('online',connectivity);addEventListener('offline',connectivity);connectivity();
document.addEventListener('submit',e=>{if(e.target.method==='post'&&!navigator.onLine){e.preventDefault();connectivity()}});
document.body.addEventListener('htmx:configRequest',e=>e.detail.headers['X-CSRFToken']=csrf());
let revision=null;
async function poll(){if(!document.querySelector('#unread')||!navigator.onLine||document.hidden)return;try{const r=await fetch('/api/sync?revision='+encodeURIComponent(revision||''),{cache:'no-store'});if(r.redirected){document.querySelector('#refresh').hidden=false;document.querySelector('#refresh').textContent='Session expired. Sign in again.';return}if(!r.ok)return;const d=await r.json();document.querySelector('#unread').textContent=d.unread?String(d.unread):'♧';if(revision!==null&&d.revision!==revision)document.querySelector('#refresh').hidden=false;revision=d.revision}catch(e){}}
poll();setInterval(poll,12000);document.addEventListener('visibilitychange',poll);
if('serviceWorker' in navigator)navigator.serviceWorker.register('/sw.js');
if(location.hash){document.querySelector(location.hash)?.setAttribute('open','')}
