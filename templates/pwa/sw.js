/* FASAS Digitale – service worker (versione {{ version }}).
 *
 * - Notifiche push: mostra l'avviso e al tocco apre FASAS sulla pagina collegata.
 * - Modalità offline: conserva solo l'«involucro» dell'applicazione (pagina offline, stile, script, icone).
 *   Le pagine con dati sanitari NON vengono mai salvate nella cache: i dati per lavorare senza rete
 *   sono nel pacchetto cifrato gestito da offline.js.
 */
"use strict";

const VERSION = "{{ version }}";
const CACHE = "fasas-shell-" + VERSION;
const OFFLINE_URL = "{{ offline_url }}";
const SHELL = [OFFLINE_URL, {% for url in shell %}"{{ url }}"{% if not forloop.last %}, {% endif %}{% endfor %}];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k.startsWith("fasas-shell-") && k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  // Navigazione: sempre dalla rete; se la rete manca si apre la modalità offline.
  if (request.mode === "navigate") {
    event.respondWith(fetch(request).catch(() => caches.match(OFFLINE_URL)));
    return;
  }
  // Involucro dell'applicazione: dalla cache, aggiornato in background.
  if (SHELL.includes(url.pathname)) {
    event.respondWith(
      caches.open(CACHE).then((cache) => cache.match(url.pathname).then((cached) => {
        const network = fetch(request).then((response) => {
          if (response.ok) cache.put(url.pathname, response.clone());
          return response;
        }).catch(() => cached);
        return cached || network;
      }))
    );
  }
  // Tutto il resto (pagine, dati, documenti) passa dalla rete e non viene memorizzato.
});

self.addEventListener("push", (event) => {
  let data = {};
  try { data = event.data ? event.data.json() : {}; } catch (e) { data = { title: "FASAS", body: event.data && event.data.text() }; }
  const options = {
    body: data.body || "",
    tag: data.tag || "fasas",
    renotify: true,
    requireInteraction: data.level === "critical",
    icon: "{{ icon_url }}",
    badge: "{{ badge_url }}",
    vibrate: data.level === "critical" ? [300, 120, 300, 120, 300] : [200],
    data: { url: data.url || "/notifiche/" },
  };
  event.waitUntil(self.registration.showNotification(data.title || "FASAS", options));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const target = new URL(event.notification.data && event.notification.data.url || "/", self.location.origin).href;
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((windows) => {
      for (const client of windows) {
        if (client.url.startsWith(self.location.origin) && "focus" in client) {
          return client.focus().then((c) => (c && "navigate" in c ? c.navigate(target) : null));
        }
      }
      return self.clients.openWindow(target);
    })
  );
});

self.addEventListener("message", (event) => {
  if (event.data === "skip-waiting") self.skipWaiting();
});
