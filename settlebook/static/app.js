const device=document.querySelector('#device');
const csrf=()=>document.querySelector('meta[name="csrf-token"]').content;
async function theme(value){
 device.classList.toggle('dark',value==='dark'||(value==='system'&&matchMedia('(prefers-color-scheme:dark)').matches));
 try{localStorage.setItem('theme',value)}catch(e){}
 document.querySelector('#theme').textContent=device.classList.contains('dark')?'☀':'☾';
 if(document.querySelector('#unread'))try{await fetch('/api/theme',{method:'POST',headers:{'Content-Type':'application/json','X-CSRFToken':csrf()},body:JSON.stringify({theme:value})})}catch(e){}
}
document.querySelector('#theme').onclick=()=>theme(device.classList.contains('dark')?'light':'dark');
document.addEventListener('click',e=>{if(e.target.closest('#system-theme'))theme('system')});
matchMedia('(prefers-color-scheme:dark)').addEventListener('change',()=>{try{if(!localStorage.getItem('theme')||localStorage.getItem('theme')==='system')theme('system')}catch(e){}});
function connectivity(){const offline=!navigator.onLine;const n=document.querySelector('#network');n.hidden=!offline;n.textContent='You are offline. Financial submissions are disabled until reconnected.';document.querySelectorAll('form[method="post"] button').forEach(b=>{if(offline){if(!b.disabled){b.dataset.offline='1';b.disabled=true}}else if(b.dataset.offline){b.disabled=false;delete b.dataset.offline}})}
addEventListener('online',connectivity);addEventListener('offline',connectivity);connectivity();
document.addEventListener('submit',e=>{if(e.target.method==='post'&&!navigator.onLine){e.preventDefault();connectivity()}});
document.body.addEventListener('htmx:configRequest',e=>e.detail.headers['X-CSRFToken']=csrf());
let revision=null;
let polling=false;
async function poll(){if(!document.querySelector('#unread')||!navigator.onLine||document.hidden||polling)return;polling=true;try{const r=await fetch('/api/sync?revision='+encodeURIComponent(revision||''),{cache:'no-store',signal:AbortSignal.timeout(10000)});if(r.redirected){document.querySelector('#refresh').hidden=false;document.querySelector('#refresh').textContent='Session expired. Sign in again.';return}if(!r.ok)return;const d=await r.json();document.querySelector('#unread').textContent=d.unread?String(d.unread):'♧';if(revision!==null&&d.revision!==revision)document.querySelector('#refresh').hidden=false;revision=d.revision}catch(e){}finally{polling=false}}
setTimeout(poll,1500);setInterval(poll,30000);document.addEventListener('visibilitychange',poll);
if('serviceWorker' in navigator)navigator.serviceWorker.register('/sw.js');
if(location.hash){document.querySelector(location.hash)?.setAttribute('open','')}

// Keep navigation responsive while retaining ordinary links as a no-JS fallback.
const navigation=document.querySelector('.bottom');
function navigationState(){
 navigation.querySelectorAll('a').forEach(a=>{
  const active=new URL(a.href).pathname===location.pathname;
  a.classList.toggle('active',active);
  if(active)a.setAttribute('aria-current','page');else a.removeAttribute('aria-current');
 });
}
function navigationError(){
 const notice=document.querySelector('#network');
 notice.hidden=false;
 notice.textContent='Page could not load. Check your connection and tap the tab to retry.';
}
document.body.addEventListener('htmx:beforeRequest',e=>{
 if(!navigation.contains(e.detail.elt))return;
 if(!navigator.onLine){e.preventDefault();connectivity();return}
 document.querySelector('#screen').setAttribute('aria-busy','true');
});
document.body.addEventListener('htmx:afterRequest',e=>{
 if(!navigation.contains(e.detail.elt))return;
 document.querySelector('#screen').removeAttribute('aria-busy');
 if(e.detail.failed&&e.detail.xhr.statusText!=='abort')navigationError();
});
document.body.addEventListener('htmx:afterSwap',e=>{
 if(e.detail.target.id!=='screen')return;
 document.querySelector('#screen').scrollTop=0;
 connectivity();
 // A session expiry must render the full sign-in page, including its header.
 if(e.detail.xhr.responseURL&&new URL(e.detail.xhr.responseURL).pathname==='/login'){
  location.assign(e.detail.xhr.responseURL);return;
 }
});
document.body.addEventListener('htmx:pushedIntoHistory',navigationState);
document.body.addEventListener('htmx:historyRestore',navigationState);
navigationState();
