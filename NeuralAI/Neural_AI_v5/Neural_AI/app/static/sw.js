/* Neural AI service worker: makes the site installable and shows a friendly page when offline.
   Network-first, so you always get the latest version when online. Never caches /api or /v1. */
const CACHE = "neural-shell-v1";
const OFFLINE_URL = "/static/offline.html";
const PRECACHE = [OFFLINE_URL, "/static/css/style.css", "/static/icons/icon-192.png"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(PRECACHE)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const req = e.request, url = new URL(req.url);
  if (req.method !== "GET" || url.origin !== self.location.origin) return;
  if (url.pathname.startsWith("/api/") || url.pathname.startsWith("/v1/")) return; // always live, never cached
  e.respondWith(
    fetch(req).then((res) => {
      if (res.ok && (url.pathname.startsWith("/static/") || req.mode === "navigate")) {
        const copy = res.clone();
        caches.open(CACHE).then((c) => c.put(req, copy));
      }
      return res;
    }).catch(async () => {
      const hit = await caches.match(req);
      if (hit) return hit;
      if (req.mode === "navigate") return (await caches.match(OFFLINE_URL)) || Response.error();
      return Response.error();
    })
  );
});
