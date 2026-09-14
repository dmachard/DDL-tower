const CACHE_NAME = 'ddltower-{{CACHE_VERSION}}';

self.addEventListener('install', (event) => {
    // Activate worker immediately without waiting
    self.skipWaiting();
});

self.addEventListener('activate', (event) => {
    // Clean up older caches and claim clients immediately
    event.waitUntil(
        caches.keys().then((cacheNames) => {
            return Promise.all(
                cacheNames.filter((name) => name !== CACHE_NAME).map((name) => caches.delete(name))
            );
        }).then(() => self.clients.claim())
    );
});

self.addEventListener('fetch', (event) => {
    const url = new URL(event.request.url);

    // Bypass Service Worker for API calls and non-GET requests
    if (event.request.method !== 'GET' || url.pathname.startsWith('/api/') || url.pathname.startsWith('/posters/')) {
        return;
    }

    // Network-First strategy: always fetch fresh from server, fallback to cache if offline
    event.respondWith(
        fetch(event.request)
            .then((networkResponse) => {
                if (networkResponse && networkResponse.status === 200 && networkResponse.type === 'basic') {
                    const responseToCache = networkResponse.clone();
                    caches.open(CACHE_NAME).then((cache) => {
                        cache.put(event.request, responseToCache);
                    });
                }
                return networkResponse;
            })
            .catch(() => caches.match(event.request))
    );
});
