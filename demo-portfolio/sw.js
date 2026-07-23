/* Service worker minimale per la demo TRENDLINE.
 *
 * Stesso standard usato nel prodotto originale (Pipeline Radar): non fa
 * caching dell'app shell. Serve solo a rendere la pagina installabile
 * (PWA) sulla home del telefono - un requisito di installabilita' per
 * Chrome/Android e' un service worker registrato con un handler "fetch",
 * anche se non fa nulla di speciale. Sempre in rete (network-first puro):
 * se pubblichi un aggiornamento del file, il visitatore vede sempre
 * l'ultima versione, mai una copia vecchia in cache.
 */

self.addEventListener("install", (event) => {
  self.skipWaiting(); // attiva subito la versione nuova del SW
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener("fetch", (event) => {
  // pass-through: sempre rete, nessuna copia in cache
  event.respondWith(fetch(event.request));
});
