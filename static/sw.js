/* Service worker minimale per SENTINEL.
 *
 * SCELTA DELIBERATA: NON fa caching dell'app shell (HTML/JS/CSS).
 * Serve solo a rendere la web-app installabile sulla home del telefono
 * (PWA), non a farla funzionare offline. Il caching aggressivo
 * reintrodurrebbe esattamente il problema che abbiamo appena risolto lato
 * server con "Cache-Control: no-store" - ti mostrerebbe una versione vecchia
 * dell'app dopo un deploy. Quindi qui si va SEMPRE in rete (network-first
 * puro): l'app e' sempre quella aggiornata su Cloud Run.
 *
 * Le icone e il manifest li gestisce gia' la cache HTTP del browser, non
 * serve intercettarli qui.
 */

self.addEventListener("install", (event) => {
  self.skipWaiting(); // attiva subito la versione nuova del SW
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener("fetch", (event) => {
  // pass-through: sempre rete, nessuna copia in cache dell'app
  event.respondWith(fetch(event.request));
});
