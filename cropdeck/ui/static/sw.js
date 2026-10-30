// Service worker of the installed app window (PWA).
//
// It keeps exactly one thing: the page shown when cropdeck is not running, with what that page
// needs. App pages are never cached, so the window never shows a stale screen as current - when
// the server answers, everything comes from it.
const CACHE = "cropdeck-offline-v1";
const KEPT = ["/offline", "/static/tokens.css", "/static/app.css", "/static/img/icon.svg"];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(KEPT)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const path = new URL(event.request.url).pathname;
  if (event.request.mode === "navigate") {
    event.respondWith(fetch(event.request).catch(() => caches.match("/offline")));
  } else if (KEPT.includes(path)) {
    event.respondWith(fetch(event.request).catch(() => caches.match(path)));
  }
});
