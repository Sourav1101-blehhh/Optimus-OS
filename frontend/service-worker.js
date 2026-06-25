const CACHE_NAME = 'optimus-os-v4';
const ASSETS_TO_CACHE = [
  './',
  './index.html',
  './styles.css',
  './main.js',
  './network.js',
  './ui_controller.js',
  './webgl_core.js',
  './speech.js',
  './manifest.json',
  './static/vendor/three.min.js',
  './static/vendor/marked.min.js',
  './static/vendor/purify.min.js',
  './static/vendor/highlight.min.js',
  'https://fonts.googleapis.com/css2?family=Orbitron:wght@400;500;700;900&family=Share+Tech+Mono&family=Outfit:wght@300;400;600&display=swap'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => {
        return cache.addAll(ASSETS_TO_CACHE);
      })
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames.map((cacheName) => {
          if (cacheName !== CACHE_NAME) {
            return caches.delete(cacheName);
          }
        })
      );
    })
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  if (event.request.url.startsWith('ws://') || event.request.url.startsWith('wss://')) {
    return; // Do not intercept WebSocket connections
  }
  
  event.respondWith(
    caches.match(event.request).then((cachedResponse) => {
      const fetchPromise = fetch(event.request).then((networkResponse) => {
        if (!networkResponse || (networkResponse.status !== 200 && networkResponse.type !== 'opaque')) {
          return networkResponse;
        }
        const responseToCache = networkResponse.clone();
        caches.open(CACHE_NAME).then((cache) => {
          if (event.request.method === 'GET') {
            cache.put(event.request, responseToCache);
          }
        });
        return networkResponse;
      }).catch((err) => {
        console.warn('Network fetch failed', err);
      });
      
      return cachedResponse || fetchPromise;
    })
  );
});
