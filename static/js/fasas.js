/* FASAS Digitale – script dell'interfaccia (nessuna dipendenza esterna). */
(function () {
  "use strict";

  // Menu laterale su mobile
  document.addEventListener("click", function (e) {
    const toggle = e.target.closest("[data-nav-toggle]");
    if (toggle) {
      document.body.classList.toggle("nav-open");
      return;
    }
    if (document.body.classList.contains("nav-open") && !e.target.closest(".sidebar")) {
      document.body.classList.remove("nav-open");
    }
  });

  // Tasto "/" per andare alla ricerca (se non si sta già scrivendo in un campo)
  document.addEventListener("keydown", function (e) {
    if (e.key !== "/" || e.ctrlKey || e.metaKey || e.altKey) return;
    const tag = (document.activeElement && document.activeElement.tagName) || "";
    if (/^(INPUT|TEXTAREA|SELECT)$/.test(tag) || document.activeElement.isContentEditable) return;
    const input = document.querySelector("[data-search-input]");
    if (input) { e.preventDefault(); input.focus(); input.select(); }
  });

  // Conferma per azioni importanti: <button data-confirm="Messaggio">
  document.addEventListener("submit", function (e) {
    const btn = e.submitter;
    const msg = (btn && btn.dataset.confirm) || e.target.dataset.confirm;
    if (msg && !window.confirm(msg)) e.preventDefault();
  });

  // Mostra/nasconde campi in base a una checkbox: <div data-show-if="id_is_sos">
  function syncConditional() {
    document.querySelectorAll("[data-show-if]").forEach(function (el) {
      const ref = document.getElementById(el.dataset.showIf);
      if (!ref) return;
      const invert = el.dataset.invert === "1";
      el.hidden = invert ? ref.checked : !ref.checked;
    });
  }
  document.addEventListener("change", syncConditional);
  document.addEventListener("DOMContentLoaded", syncConditional);

  // Polling notifiche: aggiorna il contatore e mostra un avviso per le notifiche critiche
  const bell = document.querySelector("[data-notifications-url]");
  if (bell) {
    const url = bell.dataset.notificationsUrl;
    const badge = bell.querySelector(".badge");
    const toast = document.getElementById("critical-toast");
    let lastCritical = null;
    try { lastCritical = sessionStorage.getItem("fasas-last-critical"); } catch (err) { /* storage non disponibile */ }
    const poll = function () {
      fetch(url, { headers: { "X-Requested-With": "fetch" }, credentials: "same-origin" })
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (data) {
          if (!data) return;
          if (badge) {
            badge.textContent = data.count;
            badge.hidden = data.count === 0;
          }
          if (data.critical && String(data.critical.id) !== lastCritical && toast) {
            lastCritical = String(data.critical.id);
            try { sessionStorage.setItem("fasas-last-critical", lastCritical); } catch (err) { /* ignore */ }
            toast.querySelector("[data-title]").textContent = data.critical.title;
            toast.querySelector("[data-message]").textContent = data.critical.message;
            toast.style.display = "block";
          }
        })
        .catch(function () { /* rete assente: si riprova al prossimo giro */ });
    };
    setInterval(poll, 60000);
    setTimeout(poll, 3000);
    if (toast) toast.querySelector("button").addEventListener("click", function () { toast.style.display = "none"; });
  }

  // --- Grafici parametri (SVG) -------------------------------------------------------------
  function el(name, attrs) {
    const node = document.createElementNS("http://www.w3.org/2000/svg", name);
    Object.keys(attrs || {}).forEach(function (k) { node.setAttribute(k, attrs[k]); });
    return node;
  }

  function fmtDate(d) {
    return d.toLocaleDateString("it-IT", { day: "2-digit", month: "2-digit" });
  }

  function drawChart(container, series) {
    const W = container.clientWidth || 600, H = container.clientHeight || 220;
    const pad = { l: 42, r: 12, t: 12, b: 26 };
    const pts = series.points.map(function (p) { return { t: new Date(p.t), v: p.v, v2: p.v2 }; });
    if (!pts.length) return;
    const values = [];
    pts.forEach(function (p) { values.push(p.v); if (p.v2 !== null && p.v2 !== undefined) values.push(p.v2); });
    if (series.min !== null) values.push(series.min);
    if (series.max !== null) values.push(series.max);
    let lo = Math.min.apply(null, values), hi = Math.max.apply(null, values);
    if (lo === hi) { lo -= 1; hi += 1; }
    const margin = (hi - lo) * 0.1;
    lo -= margin; hi += margin;
    const t0 = pts[0].t.getTime(), t1 = pts[pts.length - 1].t.getTime();
    const span = Math.max(t1 - t0, 1);
    const x = function (t) { return pad.l + (pts.length === 1 ? (W - pad.l - pad.r) / 2 : ((t.getTime() - t0) / span) * (W - pad.l - pad.r)); };
    const y = function (v) { return pad.t + (1 - (v - lo) / (hi - lo)) * (H - pad.t - pad.b); };

    const svg = el("svg", { viewBox: "0 0 " + W + " " + H, role: "img", "aria-label": "Andamento " + series.name });
    if (series.min !== null && series.max !== null) {
      svg.appendChild(el("rect", { class: "band", x: pad.l, width: W - pad.l - pad.r, y: y(series.max),
        height: Math.max(0, y(series.min) - y(series.max)) }));
    }
    for (let i = 0; i <= 4; i++) {
      const v = lo + (hi - lo) * i / 4, yy = y(v);
      svg.appendChild(el("line", { class: "grid-line", x1: pad.l, x2: W - pad.r, y1: yy, y2: yy }));
      const label = el("text", { x: pad.l - 6, y: yy + 4, "text-anchor": "end" });
      label.textContent = (Math.round(v * 10) / 10).toString().replace(".", ",");
      svg.appendChild(label);
    }
    svg.appendChild(el("line", { class: "axis", x1: pad.l, x2: W - pad.r, y1: H - pad.b, y2: H - pad.b }));
    const ticks = Math.min(6, pts.length);
    for (let i = 0; i < ticks; i++) {
      const p = pts[Math.round(i * (pts.length - 1) / Math.max(ticks - 1, 1))];
      const label = el("text", { x: x(p.t), y: H - 8, "text-anchor": "middle" });
      label.textContent = fmtDate(p.t);
      svg.appendChild(label);
    }
    const path = function (key) {
      return pts.filter(function (p) { return p[key] !== null && p[key] !== undefined; })
        .map(function (p, i) { return (i ? "L" : "M") + x(p.t).toFixed(1) + " " + y(p[key]).toFixed(1); }).join(" ");
    };
    svg.appendChild(el("path", { class: "line", d: path("v") }));
    const hasV2 = pts.some(function (p) { return p.v2 !== null && p.v2 !== undefined; });
    if (hasV2) svg.appendChild(el("path", { class: "line2", d: path("v2") }));

    const tip = document.getElementById("chart-tip");
    pts.forEach(function (p) {
      const out = (series.min !== null && p.v < series.min) || (series.max !== null && p.v > series.max);
      const c = el("circle", { class: "pt" + (out ? " out" : ""), cx: x(p.t), cy: y(p.v), r: 3.5, tabindex: 0 });
      const text = p.t.toLocaleString("it-IT", { dateStyle: "short", timeStyle: "short" }) + " – " +
        String(p.v).replace(".", ",") + (hasV2 && p.v2 !== null ? "/" + String(p.v2).replace(".", ",") : "") + " " + series.unit;
      c.appendChild(el("title")).textContent = text;
      if (tip) {
        c.addEventListener("mouseenter", function (e) { tip.textContent = text; tip.style.display = "block";
          tip.style.left = (e.clientX + 12) + "px"; tip.style.top = (e.clientY - 28) + "px"; });
        c.addEventListener("mouseleave", function () { tip.style.display = "none"; });
      }
      svg.appendChild(c);
      if (hasV2 && p.v2 !== null && p.v2 !== undefined) {
        svg.appendChild(el("circle", { class: "pt2", cx: x(p.t), cy: y(p.v2), r: 3 }));
      }
    });
    container.innerHTML = "";
    container.appendChild(svg);
  }

  function renderCharts() {
    const source = document.getElementById("charts-data");
    if (!source) return;
    const data = JSON.parse(source.textContent);
    document.querySelectorAll("[data-chart]").forEach(function (node) {
      const series = data[Number(node.dataset.chart)];
      if (series) drawChart(node, series);
    });
  }
  document.addEventListener("DOMContentLoaded", renderCharts);
  let resizeTimer;
  window.addEventListener("resize", function () { clearTimeout(resizeTimer); resizeTimer = setTimeout(renderCharts, 200); });

  // Service worker: notifiche push e modalità senza rete
  const swUrl = document.body && document.body.dataset.swUrl;
  if (swUrl && "serviceWorker" in navigator) {
    navigator.serviceWorker.register(swUrl, { scope: "/" }).catch(function () { /* browser senza supporto */ });
  }

  // Calendario turni: pennello per assegnare codici trascinando sulle caselle, poi un unico salvataggio
  const rotaTable = document.querySelector("[data-rota]");
  const rotaToolbar = document.querySelector("[data-rota-toolbar]");
  const rotaForm = document.querySelector("[data-rota-save]");
  if (rotaTable && rotaToolbar && rotaForm) {
    rotaTable.setAttribute("data-rota-editable", "");
    const changes = new Map();
    let paint = null;
    let painting = false;
    let submitting = false;
    const saveBtn = rotaForm.querySelector("button");
    const refreshSave = function () {
      rotaForm.elements.changes.value = JSON.stringify(Array.from(changes.values()));
      saveBtn.disabled = changes.size === 0;
      saveBtn.querySelector("[data-count]").textContent = changes.size;
    };
    rotaToolbar.querySelectorAll("[data-paint]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        paint = btn.dataset.paint;
        rotaToolbar.querySelectorAll("[data-paint]").forEach(function (b) { b.classList.toggle("selected", b === btn); });
      });
    });
    const apply = function (cell) {
      if (paint === null) return;
      const key = cell.dataset.user + "|" + cell.dataset.day;
      const change = changes.get(key) || { user: Number(cell.dataset.user), day: cell.dataset.day, code: cell.textContent.trim() };
      if (paint === "*lead") {
        if (!change.code) return;
        cell.classList.toggle("lead");
        change.lead = cell.classList.contains("lead");
      } else {
        change.code = paint;
        cell.textContent = paint;
        cell.className = cell.className.replace(/\bcode-\S+/, "code-" + (paint || "none"));
        if (!paint) { cell.classList.remove("lead"); change.lead = false; }
      }
      cell.classList.add("changed");
      changes.set(key, change);
      refreshSave();
    };
    rotaTable.addEventListener("mousedown", function (e) {
      const cell = e.target.closest(".rota-cell");
      if (!cell) return;
      e.preventDefault();
      painting = paint !== "*lead";
      apply(cell);
    });
    rotaTable.addEventListener("mouseover", function (e) {
      if (!painting) return;
      const cell = e.target.closest(".rota-cell");
      if (cell) apply(cell);
    });
    document.addEventListener("mouseup", function () { painting = false; });
    rotaForm.addEventListener("submit", function () { submitting = true; });
    window.addEventListener("beforeunload", function (e) {
      if (changes.size && !submitting) { e.preventDefault(); e.returnValue = ""; }
    });
    refreshSave();
  }

  // Notifiche push sul dispositivo (pagina «Notifiche sul telefono»): controlli, attivazione, prova locale
  const pushBox = document.querySelector("[data-push]");
  if (pushBox) {
    const status = pushBox.querySelector("[data-push-status]");
    const enableBtn = pushBox.querySelector("[data-push-enable]");
    const disableBtn = pushBox.querySelector("[data-push-disable]");
    const localBtn = pushBox.querySelector("[data-push-local]");
    const localResult = pushBox.querySelector("[data-push-local-result]");
    const csrf = (document.querySelector("meta[name=csrf-token]") || {}).content || "";
    const isIos = /iphone|ipad|ipod/i.test(navigator.userAgent);
    const isAndroid = /android/i.test(navigator.userAgent);
    const standalone = window.matchMedia("(display-mode: standalone)").matches || navigator.standalone;
    const knownNode = document.getElementById("push-endpoints");
    const known = knownNode ? JSON.parse(knownNode.textContent) : [];
    const keyBytes = function (b64) {
      const pad = "=".repeat((4 - (b64.length % 4)) % 4);
      const raw = atob((b64 + pad).replace(/-/g, "+").replace(/_/g, "/"));
      return Uint8Array.from(raw, function (c) { return c.charCodeAt(0); });
    };
    const sameKey = function (sub) {
      const key = sub.options && sub.options.applicationServerKey;
      if (!key) return true; // browser che non la espongono
      const a = new Uint8Array(key);
      const b = keyBytes(pushBox.dataset.publicKey);
      return a.length === b.length && a.every(function (v, i) { return v === b[i]; });
    };
    const sha256 = function (text) {
      return crypto.subtle.digest("SHA-256", new TextEncoder().encode(text)).then(function (buf) {
        return Array.from(new Uint8Array(buf), function (b) { return b.toString(16).padStart(2, "0"); }).join("");
      });
    };
    const post = function (url, body) {
      return fetch(url, { method: "POST", credentials: "same-origin", body: JSON.stringify(body),
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrf } });
    };
    const check = function (name, ok, help) {
      const item = pushBox.querySelector('[data-check="' + name + '"]');
      item.className = ok ? "ok" : "ko";
      item.querySelector("use").setAttribute("href", ok ? "#i-check-circle" : "#i-alert-circle");
      const note = item.querySelector("small");
      note.textContent = ok ? "" : help;
      note.hidden = ok;
      return ok;
    };
    const buttons = function (enable, local, disable) {
      enableBtn.hidden = !enable;
      localBtn.hidden = !local;
      disableBtn.hidden = !disable;
    };
    let failure = ""; // esito dell'ultima attivazione non riuscita, mostrato al posto dello stato
    const say = function (text) { status.textContent = failure || text; };
    const refresh = function () {
      buttons(false, false, false);
      if (!check("secure", window.isSecureContext, "La pagina è aperta da " + location.origin + ": i browser permettono " +
          "le notifiche solo in HTTPS oppure su http://127.0.0.1 e http://localhost. Sul computer che esegue il FASAS apri " +
          "http://127.0.0.1:" + (location.port || "80") + "/; sugli altri dispositivi serve il FASAS pubblicato in HTTPS" +
          (isAndroid ? " (per la sola prova, in Chrome: chrome://flags › «Insecure origins treated as secure» › aggiungi " +
            location.origin + " › Relaunch)." : "."))) {
        say("Con questo indirizzo il browser non permette le notifiche.");
        return;
      }
      const supported = "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
      if (!check("support", supported, isIos && !standalone
          ? "Su iPhone e iPad: aggiungi FASAS alla schermata Home e aprilo dall'icona (serve iOS 16.4 o successivo)."
          : "Questo browser non supporta le notifiche push, oppure è una finestra in incognito/InPrivate.")) {
        if (isIos && !standalone) pushBox.querySelector("[data-push-ios]").hidden = false;
        say("Questo browser non supporta le notifiche push.");
        return;
      }
      const permission = Notification.permission;
      check("permission", permission === "granted", permission === "denied"
        ? "Bloccato: clicca l'icona a sinistra dell'indirizzo › Notifiche › Consenti, poi ricarica la pagina."
        : "Non ancora concesso: premi «Attiva le notifiche su questo dispositivo» e scegli «Consenti».");
      if (permission === "denied") {
        say("Le notifiche sono bloccate nelle impostazioni del browser per questo sito.");
        return;
      }
      const slow = setTimeout(function () {
        check("worker", false, "Non si è attivato: ricarica la pagina; se resta così chiudi e riapri il browser.");
        say("Il service worker del FASAS non è attivo.");
      }, 6000);
      navigator.serviceWorker.ready.then(function (reg) {
        clearTimeout(slow);
        check("worker", true);
        return reg.pushManager.getSubscription();
      }).then(function (sub) {
        const local = permission === "granted";
        if (!sub) {
          check("subscription", false, "Questo browser non è iscritto: premi «Attiva le notifiche su questo dispositivo».");
          buttons(true, local, false);
          say("Notifiche non attive su questo dispositivo.");
          return null;
        }
        if (!sameKey(sub)) {
          check("subscription", false, "Iscrizione creata con una chiave del server diversa da quella attuale: " +
            "premi «Attiva le notifiche su questo dispositivo» per rinnovarla.");
          buttons(true, local, true);
          say("Notifiche da riattivare su questo dispositivo.");
          return null;
        }
        return sha256(sub.endpoint).then(function (hash) {
          const linked = known.indexOf(hash) !== -1;
          check("subscription", linked, "Il browser è iscritto ma il FASAS non lo ha tra i tuoi dispositivi (rimosso, " +
            "scaduto o attivato da un altro utente): premi «Attiva le notifiche su questo dispositivo».");
          buttons(!linked, local, true);
          say(linked ? "Notifiche attive su questo dispositivo." : "Notifiche da ricollegare al tuo utente.");
        });
      });
    };
    enableBtn.addEventListener("click", function () {
      enableBtn.disabled = true;
      Notification.requestPermission().then(function (permission) {
        if (permission !== "granted") {
          throw new Error(permission === "denied"
            ? "permesso negato: sbloccalo dall'icona a sinistra dell'indirizzo e ricarica la pagina"
            : "il permesso non è stato concesso (se il browser non ha mostrato la richiesta, clicca la campanella " +
              "barrata o l'icona a sinistra dell'indirizzo)");
        }
        return navigator.serviceWorker.ready;
      }).then(function (reg) {
        return reg.pushManager.getSubscription().then(function (old) {
          return old && !sameKey(old) ? old.unsubscribe() : null;
        }).then(function () {
          return reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: keyBytes(pushBox.dataset.publicKey) });
        });
      }).then(function (sub) {
        return post(pushBox.dataset.subscribeUrl, sub.toJSON());
      }).then(function (r) {
        if (!r.ok) throw new Error("il FASAS ha rifiutato l'iscrizione (" + r.status + ")");
        window.location.reload();
      }).catch(function (err) {
        enableBtn.disabled = false;
        failure = "Attivazione non riuscita: " + (err && err.message || err) + ".";
        refresh();
      });
    });
    localBtn.addEventListener("click", function () {
      localResult.hidden = false;
      navigator.serviceWorker.ready.then(function (reg) {
        return reg.showNotification("FASAS · Prova locale", {
          body: "Se leggi questo avviso, browser e sistema operativo mostrano le notifiche del FASAS.",
          tag: "fasas-local-test", icon: pushBox.dataset.icon, badge: pushBox.dataset.badge,
          data: { url: location.pathname },
        });
      }).then(function () {
        localResult.textContent = "Il browser ha mostrato la notifica «FASAS · Prova locale». Se non l'hai vista comparire, " +
          "il blocco è nel sistema operativo (notifiche del browser disattivate o «Non disturbare»): vedi «Non compare nulla?».";
      }).catch(function (err) {
        localResult.textContent = "Il browser non ha potuto mostrare la notifica: " + (err && err.message || err) + ".";
      });
    });
    disableBtn.addEventListener("click", function () {
      navigator.serviceWorker.ready.then(function (reg) { return reg.pushManager.getSubscription(); }).then(function (sub) {
        if (!sub) return null;
        return post(pushBox.dataset.unsubscribeUrl, { endpoint: sub.endpoint }).then(function () { return sub.unsubscribe(); });
      }).then(function () { window.location.reload(); });
    });
    refresh();
  }
})();
