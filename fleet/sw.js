// Service worker: cache della shell per avvio rapido e uso offline dell'interfaccia.
// Le chiamate alle API AI vanno sempre in rete (network-first per le richieste cross-origin).
const CACHE = "ouroboros-fleet-v1";
const SHELL = [
  "./",
  "./index.html",
  "./styles.css",
  "./app.js",
  "./providers.js",
  "./manifest.webmanifest",
  "./icon.svg",
];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  // Solo la shell (stessa origine) è servita dalla cache. Tutto il resto va in rete.
  if (url.origin === location.origin && e.request.method === "GET") {
    e.respondWith(
      caches.match(e.request).then((hit) => hit || fetch(e.request).then((res) => {
        const copy = res.clone();
        caches.open(CACHE).then((c) => c.put(e.request, copy)).catch(() => {});
        return res;
      }).catch(() => caches.match("./index.html")))
    );
  }
  // richieste alle API AI: lasciate passare normalmente (network).
});
