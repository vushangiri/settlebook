const CACHE='settlebook-shell-v2';
const ASSETS=['/static/offline.html','/static/icon-192.png','/static/icon-512.png'];
self.addEventListener('install',e=>e.waitUntil(caches.open(CACHE).then(c=>c.addAll(ASSETS))));
self.addEventListener('activate',e=>e.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k!==CACHE).map(k=>caches.delete(k))))));
self.addEventListener('fetch',e=>{if(e.request.method!=='GET')return;const u=new URL(e.request.url);if(u.origin!==location.origin)return;
 if(e.request.mode==='navigate'){e.respondWith(fetch(e.request).catch(()=>caches.match('/static/offline.html')));return}
 if(ASSETS.includes(u.pathname))e.respondWith(caches.match(e.request).then(c=>c||fetch(e.request)));
});
