/* FASAS Digitale – modalità offline.
 *
 * Sicurezza dei dati sul dispositivo
 * - Il pacchetto del turno e le registrazioni in attesa sono cifrati con AES-GCM (chiave «DK», 256 bit).
 * - DK è salvata solo «avvolta» con una chiave derivata dalla password dell'utente (PBKDF2-SHA256):
 *   senza la password non si leggono i dati, anche avendo il tablet in mano.
 * - Durante la sessione DK è tenuta come chiave non esportabile; viene cancellata all'uscita, alla
 *   pagina di accesso e dopo l'inattività configurata (blocco automatico).
 * - Il service worker non memorizza mai pagine o dati sanitari: solo questo «involucro».
 */
(function () {
  "use strict";

  const DB_NAME = "fasas-offline";
  const ITERATIONS = 300000;
  const PACK_REFRESH_MS = 30 * 60 * 1000;
  const PACK_PURGE_MS = 72 * 3600 * 1000;
  const SYNCED_KEEP_MS = 24 * 3600 * 1000;
  const enc = new TextEncoder();
  const dec = new TextDecoder();
  const subtle = window.crypto && window.crypto.subtle;

  // --- IndexedDB -------------------------------------------------------------------------
  function openDb() {
    return new Promise((resolve, reject) => {
      const req = indexedDB.open(DB_NAME, 1);
      req.onupgradeneeded = () => {
        const db = req.result;
        db.createObjectStore("keys");      // username -> [{iv, wrapped}] (DK avvolta con le password)
        db.createObjectStore("session");   // username -> {key: CryptoKey non esportabile, active: ms}
        db.createObjectStore("packs");     // username -> {iv, data, generated_at, fetched_at}
        const queue = db.createObjectStore("queue", { keyPath: "uuid" });
        queue.createIndex("user", "user");
      };
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  }
  async function tx(store, mode, fn) {
    const db = await openDb();
    return new Promise((resolve, reject) => {
      const t = db.transaction(store, mode);
      const result = fn(t.objectStore(store));
      t.oncomplete = () => resolve(result && "result" in result ? result.result : result);
      t.onerror = () => reject(t.error);
    });
  }
  const get = (store, key) => tx(store, "readonly", (s) => s.get(key));
  const put = (store, value, key) => tx(store, "readwrite", (s) => (key === undefined ? s.put(value) : s.put(value, key)));
  const del = (store, key) => tx(store, "readwrite", (s) => s.delete(key));
  const all = (store) => tx(store, "readonly", (s) => s.getAll());
  const allKeys = (store) => tx(store, "readonly", (s) => s.getAllKeys());
  const clear = (store) => tx(store, "readwrite", (s) => s.clear());

  // --- Crittografia ---------------------------------------------------------------------------
  const b64 = (buf) => btoa(String.fromCharCode(...new Uint8Array(buf)));
  const unb64 = (text) => Uint8Array.from(atob(text), (c) => c.charCodeAt(0));

  async function passwordKey(username, password) {
    const material = await subtle.importKey("raw", enc.encode(password), "PBKDF2", false, ["deriveBits"]);
    const salt = enc.encode("fasas-offline:" + location.origin + ":" + username.toLowerCase());
    return subtle.deriveBits({ name: "PBKDF2", hash: "SHA-256", salt, iterations: ITERATIONS }, material, 256);
  }
  const importWrapping = (raw) => subtle.importKey("raw", raw, "AES-GCM", false, ["wrapKey", "unwrapKey"]);

  async function wrapDk(dk, wrappingRaw) {
    const iv = crypto.getRandomValues(new Uint8Array(12));
    const wrapped = await subtle.wrapKey("raw", dk, await importWrapping(wrappingRaw), { name: "AES-GCM", iv });
    return { iv: b64(iv), wrapped: b64(wrapped) };
  }
  async function unwrapDk(entries, wrappingRaw, extractable) {
    const kek = await importWrapping(wrappingRaw);
    for (const entry of entries || []) {
      try {
        return await subtle.unwrapKey("raw", unb64(entry.wrapped), kek, { name: "AES-GCM", iv: unb64(entry.iv) },
          "AES-GCM", extractable, ["encrypt", "decrypt"]);
      } catch (e) { /* password diversa: si prova la voce successiva */ }
    }
    return null;
  }
  async function encrypt(dk, obj) {
    const iv = crypto.getRandomValues(new Uint8Array(12));
    const data = await subtle.encrypt({ name: "AES-GCM", iv }, dk, enc.encode(JSON.stringify(obj)));
    return { iv: b64(iv), data: b64(data) };
  }
  async function decrypt(dk, box) {
    const plain = await subtle.decrypt({ name: "AES-GCM", iv: unb64(box.iv) }, dk, unb64(box.data));
    return JSON.parse(dec.decode(plain));
  }

  // --- Sessione sul dispositivo ----------------------------------------------------------------
  async function startSession(username, wrappingRaw) {
    let dk = await unwrapDk(await get("keys", username), wrappingRaw, true);
    if (!dk) dk = await subtle.generateKey({ name: "AES-GCM", length: 256 }, true, ["encrypt", "decrypt"]);
    await put("keys", [await wrapDk(dk, wrappingRaw)], username);
    const sessionKey = await subtle.importKey("raw", await subtle.exportKey("raw", dk), "AES-GCM", false, ["encrypt", "decrypt"]);
    await put("session", { key: sessionKey, active: Date.now() }, username);
    return sessionKey;
  }
  async function sessionKey(username, idleMinutes) {
    const s = await get("session", username);
    if (!s) return null;
    if (idleMinutes && Date.now() - s.active > idleMinutes * 60000) {
      await del("session", username);
      return null;
    }
    return s.key;
  }
  async function touch(username) {
    const s = await get("session", username);
    if (s) { s.active = Date.now(); await put("session", s, username); }
  }
  const lockAll = () => clear("session").catch(() => {});

  // --- Rete ----------------------------------------------------------------------------------
  async function serverStatus(url) {
    try {
      const r = await fetch(url, { credentials: "same-origin", cache: "no-store", headers: { "X-Requested-With": "fetch" } });
      if (r.status === 401) return { online: true, authenticated: false };
      if (!r.ok) return { online: false };
      return await r.json();
    } catch (e) {
      return { online: false };
    }
  }

  async function pendingFor(username) {
    return (await all("queue")).filter((r) => r.user === username && r.state === "pending");
  }

  async function syncPending(username, dk, syncUrl, csrf) {
    const pending = await pendingFor(username);
    if (!pending.length) return { sent: 0, results: [] };
    const records = [];
    for (const item of pending) records.push(await decrypt(dk, item.box));
    const r = await fetch(syncUrl, {
      method: "POST", credentials: "same-origin", cache: "no-store",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrf, "X-Requested-With": "fetch" },
      body: JSON.stringify({ user: username, records }),
    });
    if (!r.ok) throw new Error("sync " + r.status);
    const data = await r.json();
    for (const result of data.results) {
      const item = pending.find((p) => p.uuid === result.uuid);
      if (!item) continue;
      item.state = result.status === "ok" ? "synced" : "problem";
      item.result = { status: result.status, message: result.message || "" };
      item.synced_at = Date.now();
      await put("queue", item);
    }
    return { sent: pending.length, results: data.results };
  }

  async function refreshPack(username, dk, packUrl, force) {
    const current = await get("packs", username);
    if (!force && current && Date.now() - current.fetched_at < PACK_REFRESH_MS) return current;
    const r = await fetch(packUrl, { credentials: "same-origin", cache: "no-store", headers: { "X-Requested-With": "fetch" } });
    if (!r.ok) return current;
    const pack = await r.json();
    const box = await encrypt(dk, pack);
    const entry = { ...box, generated_at: pack.generated_at, expires_at: pack.expires_at, fetched_at: Date.now() };
    await put("packs", entry, username);
    return entry;
  }

  async function housekeeping() {
    const now = Date.now();
    for (const username of await allKeys("packs")) {
      const p = await get("packs", username);
      if (p && now - p.fetched_at > PACK_PURGE_MS) await del("packs", username);
    }
    for (const item of await all("queue")) {
      if (item.state === "synced" && now - (item.synced_at || 0) > SYNCED_KEEP_MS) await del("queue", item.uuid);
    }
  }

  // --- Integrazione con le pagine normali -------------------------------------------------------
  function hookLogin(form) {
    form.addEventListener("submit", function (e) {
      if (form.dataset.offlineReady === "1") return;
      const user = form.querySelector("[name=username]");
      const pass = form.querySelector("[name=password]");
      if (!user || !pass || !user.value || !pass.value) return;
      e.preventDefault();
      passwordKey(user.value.trim(), pass.value)
        .then((raw) => { sessionStorage.setItem("fasas-offline-k", JSON.stringify({ user: user.value.trim(), k: b64(raw) })); })
        .catch(() => {})
        .finally(() => { form.dataset.offlineReady = "1"; form.requestSubmit ? form.requestSubmit() : form.submit(); });
    });
  }

  function hookPasswordChange(form, username) {
    form.addEventListener("submit", function (e) {
      if (form.dataset.offlineReady === "1") return;
      const old = form.querySelector("[name=old_password]");
      const neu = form.querySelector("[name=new_password1]");
      if (!old || !neu || !old.value || !neu.value) return;
      e.preventDefault();
      (async () => {
        const entries = (await get("keys", username)) || [];
        const dk = await unwrapDk(entries, await passwordKey(username, old.value), true);
        if (dk) await put("keys", entries.concat([await wrapDk(dk, await passwordKey(username, neu.value))]), username);
      })().catch(() => {}).finally(() => { form.dataset.offlineReady = "1"; form.requestSubmit ? form.requestSubmit() : form.submit(); });
    });
  }

  async function onAuthenticatedPage(body) {
    const username = body.dataset.offlineUser;
    const stash = sessionStorage.getItem("fasas-offline-k");
    let dk = null;
    if (stash) {
      sessionStorage.removeItem("fasas-offline-k");
      try {
        const data = JSON.parse(stash);
        if (data.user.toLowerCase() === username.toLowerCase()) dk = await startSession(username, unb64(data.k));
      } catch (e) { /* si riprova al prossimo accesso */ }
    }
    dk = dk || (await sessionKey(username, Number(body.dataset.offlineIdle || 0)));
    await touch(username);
    await housekeeping();
    if (!dk) return;
    const csrf = (document.querySelector("meta[name=csrf-token]") || {}).content || "";
    try {
      const outcome = await syncPending(username, dk, body.dataset.offlineSyncUrl, csrf);
      if (outcome.sent) {
        const problems = outcome.results.filter((r) => r.status !== "ok").length;
        const note = document.getElementById("offline-sync-note");
        if (note) {
          note.hidden = false;
          note.querySelector("[data-text]").textContent = `${outcome.sent} registrazioni fatte senza rete sono state sincronizzate`
            + (problems ? `: ${problems} da verificare nella pagina Modalità offline.` : ".");
        }
      }
    } catch (e) { /* rete instabile: si riprova alla prossima pagina */ }
    try { await refreshPack(username, dk, body.dataset.offlinePackUrl, false); } catch (e) { /* idem */ }
    const ready = document.querySelector("[data-offline-ready]");
    if (ready) {
      const pack = await get("packs", username);
      const pending = (await pendingFor(username)).length;
      ready.textContent = pack
        ? `Su questo dispositivo: dati del turno salvati alle ${time(pack.generated_at)}` + (pending ? ` · ${pending} registrazioni da inviare.` : ".")
        : "Su questo dispositivo i dati del turno non sono ancora salvati: ricaricare la pagina con la rete attiva.";
    }
  }

  // --- Applicazione offline ----------------------------------------------------------------------
  const $ = (sel, root) => (root || document).querySelector(sel);
  const el = (tag, attrs, ...children) => {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v === null || v === undefined || v === false) continue;
      if (k === "class") node.className = v;
      else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
      else node.setAttribute(k, v === true ? "" : v);
    }
    for (const c of children.flat()) if (c !== null && c !== undefined && c !== false) node.append(c.nodeType ? c : String(c));
    return node;
  };
  const time = (iso) => (iso ? new Date(iso).toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" }) : "");
  const dateTime = (iso) => (iso ? new Date(iso).toLocaleString("it-IT", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }) : "");
  const uuid = () => (crypto.randomUUID ? crypto.randomUUID() : ([1e7] + -1e3 + -4e3 + -8e3 + -1e11).replace(/[018]/g, (c) =>
    (c ^ (crypto.getRandomValues(new Uint8Array(1))[0] & (15 >> (c / 4)))).toString(16)));

  function App(root) {
    this.root = root;
    this.urls = { status: root.dataset.statusUrl, pack: root.dataset.packUrl, sync: root.dataset.syncUrl, login: root.dataset.loginUrl };
    this.user = null; this.dk = null; this.pack = null; this.queue = []; this.online = false; this.tab = "round";
  }

  App.prototype.start = async function () {
    if (!subtle || !window.indexedDB) {
      this.message("Questo browser non supporta la modalità offline sicura. Usare il foglio di emergenza stampato.");
      return;
    }
    const users = await allKeys("packs");
    for (const username of users) {
      const pack = await get("packs", username);
      const key = await sessionKey(username, 0);
      if (key) {
        try { this.pack = await decrypt(key, pack); this.user = username; this.dk = key; } catch (e) { /* chiave non valida */ }
        if (this.pack) {
          const idle = this.pack.idle_minutes || 30;
          if (!(await sessionKey(username, idle))) { this.pack = null; this.user = null; this.dk = null; continue; }
          break;
        }
      }
    }
    this.users = users;
    document.addEventListener("click", () => this.user && touch(this.user), { passive: true });
    setInterval(() => this.heartbeat(), 20000);
    setInterval(() => this.checkIdle(), 30000);
    this.heartbeat();
    this.render();
  };

  App.prototype.checkIdle = async function () {
    if (!this.user || !this.pack) return;
    if (!(await sessionKey(this.user, this.pack.idle_minutes || 30))) this.lock("Bloccato per inattività.");
  };

  App.prototype.lock = async function (note) {
    if (this.user) await del("session", this.user);
    this.user = null; this.dk = null; this.pack = null;
    this.render(note);
  };

  App.prototype.heartbeat = async function () {
    const status = await serverStatus(this.urls.status);
    this.online = !!status.online;
    this.authenticated = !!status.authenticated;
    this.serverUser = status.user || null;
    if (this.user && status.authenticated && status.user === this.user && this.dk) {
      try {
        const outcome = await syncPending(this.user, this.dk, this.urls.sync, status.csrf);
        if (outcome.sent) this.toast(`${outcome.sent} registrazioni sincronizzate.`);
        const fresh = await refreshPack(this.user, this.dk, this.urls.pack, outcome.sent > 0);
        if (fresh) this.pack = await decrypt(this.dk, fresh);
      } catch (e) { /* si riprova */ }
    }
    await this.loadQueue();
    this.renderBar();
    if (this.user && this.tab === "queue") this.renderMain();
  };

  App.prototype.loadQueue = async function () {
    this.queue = this.user ? (await all("queue")).filter((q) => q.user === this.user) : [];
    this.queue.sort((a, b) => b.created_at - a.created_at);
    this.decoded = {};
    for (const item of this.queue) {
      try { this.decoded[item.uuid] = await decrypt(this.dk, item.box); } catch (e) { /* ignora */ }
    }
  };

  App.prototype.record = async function (payload) {
    payload.uuid = uuid();
    payload.occurred_at = new Date().toISOString();
    await put("queue", { uuid: payload.uuid, user: this.user, state: "pending", created_at: Date.now(), box: await encrypt(this.dk, payload) });
    await touch(this.user);
    await this.loadQueue();
    this.toast("Registrato sul dispositivo: verrà inviato appena torna la rete.");
    this.render();
    if (this.online) this.heartbeat();
  };

  App.prototype.message = function (text) {
    this.root.replaceChildren(el("div", { class: "card" }, el("p", {}, text)));
  };

  App.prototype.toast = function (text) {
    const t = $("#offline-toast");
    t.textContent = text; t.hidden = false;
    clearTimeout(this._toast);
    this._toast = setTimeout(() => { t.hidden = true; }, 4000);
  };

  App.prototype.renderBar = function () {
    const state = $("[data-net]");
    if (state) {
      state.className = "pill " + (this.online ? "pill-ok" : "pill-danger");
      state.textContent = this.online ? (this.authenticated ? "rete disponibile" : "rete disponibile · accesso richiesto") : "senza rete";
    }
    const pending = this.queue.filter((q) => q.state === "pending").length;
    const counter = $("[data-pending]");
    if (counter) counter.textContent = pending;
    const login = $("[data-login]");
    if (login) login.hidden = !(this.online && !this.authenticated);
    const back = $("[data-back]");
    if (back) back.hidden = !(this.online && this.authenticated);
  };

  App.prototype.render = function (note) {
    this.renderBar();
    const main = $("[data-main]");
    $("[data-user]").textContent = this.user && this.pack ? this.pack.user.name : "";
    $("[data-lock]").hidden = !this.user;
    $("[data-print]").hidden = !this.pack;
    if (!this.user || !this.pack) return this.renderUnlock(main, note);
    this.renderMain();
  };

  App.prototype.renderUnlock = function (main, note) {
    const options = this.users.map((u) => el("option", { value: u }, u));
    const form = el("form", { class: "card offline-unlock", onsubmit: (e) => this.unlock(e) },
      el("h2", {}, "Sblocca i dati del turno"),
      el("p", { class: "muted" }, "I dati sono cifrati su questo dispositivo. Inserisci la tua password di FASAS: funziona anche senza rete."),
      note ? el("div", { class: "alert alert-info" }, el("div", { class: "alert-body" }, note)) : null,
      this.users.length ? null : el("div", { class: "alert alert-warning" }, el("div", { class: "alert-body" },
        "Su questo dispositivo non ci sono dati del turno: vengono scaricati automaticamente quando si usa FASAS con la rete. Usare il foglio di emergenza stampato.")),
      el("div", { class: "form-grid compact" },
        el("div", { class: "field" }, el("label", { for: "off-user" }, "Utente"), el("select", { id: "off-user", name: "user" }, options)),
        el("div", { class: "field" }, el("label", { for: "off-pass" }, "Password"), el("input", { id: "off-pass", name: "password", type: "password", autocomplete: "current-password", required: true }))),
      el("div", { class: "errors", "data-error": true, hidden: true }),
      el("div", { class: "form-actions" }, el("button", { class: "btn btn-primary", type: "submit", disabled: !this.users.length }, "Sblocca")));
    main.replaceChildren(form);
  };

  App.prototype.unlock = async function (e) {
    e.preventDefault();
    const form = e.target;
    const username = form.user.value;
    const error = $("[data-error]", form);
    error.hidden = true;
    form.querySelector("button").disabled = true;
    try {
      const raw = await passwordKey(username, form.password.value);
      const dk = await unwrapDk(await get("keys", username), raw, false);
      if (!dk) throw new Error("password");
      const pack = await decrypt(dk, await get("packs", username));
      await put("session", { key: dk, active: Date.now() }, username);
      this.user = username; this.dk = dk; this.pack = pack;
      await this.loadQueue();
      this.render();
      this.heartbeat();
    } catch (err) {
      error.textContent = "Password non corretta per questo utente.";
      error.hidden = false;
      form.querySelector("button").disabled = false;
    }
  };

  App.prototype.guest = function (id) { return this.pack.guests.find((g) => g.id === id) || { name: "?" }; };

  App.prototype.localDone = function (dose) {
    return this.queue.find((q) => {
      const d = this.decoded[q.uuid];
      return d && d.kind === "administration" && d.therapy === dose.therapy && d.day === dose.day && d.time === dose.time;
    });
  };

  App.prototype.renderMain = function () {
    const main = $("[data-main]");
    const pack = this.pack;
    const expired = new Date(pack.expires_at) < new Date();
    const head = el("div", { class: "page-head" },
      el("div", {}, el("h1", {}, "Modalità senza rete"),
        el("span", { class: "subtitle" }, `${pack.community} · dati aggiornati al ${dateTime(pack.generated_at)} · ${pack.shifts.map((s) => s.label.toLowerCase()).join(" e ")}`)));
    const warn = expired ? el("div", { class: "alert alert-danger" }, el("div", { class: "alert-body" },
      "Dati di oltre 12 ore fa: terapie e stati potrebbero essere cambiati. Verificare con il foglio di emergenza o con il coordinatore.")) : null;
    const tabs = el("div", { class: "tabs" }, [["round", "Giro farmaci"], ["guests", "Ospiti"], ["queue", `Da inviare (${this.queue.filter((q) => q.state !== "synced").length})`]]
      .map(([key, label]) => el("a", { href: "#", class: this.tab === key ? "active" : "", onclick: (e) => { e.preventDefault(); this.tab = key; this.renderMain(); } }, label)));
    const body = this.tab === "round" ? this.renderRound() : this.tab === "guests" ? this.renderGuests() : this.renderQueue();
    main.replaceChildren(head, warn || "", tabs, body);
  };

  App.prototype.renderRound = function () {
    const pack = this.pack;
    const wrap = el("div", {});
    for (const shift of pack.shifts) {
      const doses = pack.doses.filter((d) => d.shift === shift.code && d.shift_day === shift.day);
      const byGuest = {};
      doses.forEach((d) => (byGuest[d.guest] = byGuest[d.guest] || []).push(d));
      const card = el("div", { class: "card" }, el("div", { class: "card-head" }, el("h2", {}, `Turno ${shift.label.toLowerCase()} · ${time(shift.start)}–${time(shift.end)}`)));
      if (!doses.length) card.append(el("p", { class: "muted" }, "Nessuna dose programmata."));
      for (const [guestId, list] of Object.entries(byGuest)) {
        const guest = this.guest(Number(guestId));
        const allergy = guest.allergies.length ? el("span", { class: "pill pill-danger" }, "Allergie: " + guest.allergies.map((a) => a.substance).join(", ")) : null;
        const rows = list.map((dose) => {
          const local = this.localDone(dose);
          let state;
          if (dose.done) state = el("span", { class: "pill pill-ok" }, `${dose.done.status} ${time(dose.done.at)}${dose.done.by ? " · " + dose.done.by : ""}`);
          else if (local) state = el("span", { class: "pill pill-info" }, `${(this.pack.administration_statuses.find((s) => s.code === this.decoded[local.uuid].status) || {}).label || ""} ${time(this.decoded[local.uuid].occurred_at)} · da inviare`);
          else if (pack.permissions.administration) state = el("span", { class: "offline-actions" },
            el("button", { class: "btn btn-sm btn-primary", type: "button", onclick: () => this.administer(dose, "given") }, "Somministrato"),
            el("button", { class: "btn btn-sm", type: "button", onclick: () => this.administer(dose, "refused") }, "Rifiutato"),
            el("button", { class: "btn btn-sm", type: "button", onclick: () => this.administer(dose, "not_given") }, "Non dato"));
          return el("tr", {}, el("td", { class: "mono nowrap" }, dose.time), el("td", {}, el("strong", {}, dose.drug), " ", dose.dose, el("br"), el("small", { class: "muted" }, [dose.route, dose.instructions].filter(Boolean).join(" · "))), el("td", { class: "num" }, state));
        });
        card.append(el("div", { class: "offline-guest" }, el("h3", {}, guest.name, guest.room ? el("small", { class: "muted" }, " · camera " + guest.room) : null, " ", allergy),
          el("div", { class: "table-wrap" }, el("table", {}, el("tbody", {}, rows)))));
      }
      wrap.append(card);
    }
    return wrap;
  };

  App.prototype.renderGuests = function () {
    const pack = this.pack;
    const grid = el("div", { class: "grid grid-2" });
    for (const g of pack.guests) {
      const protocols = pack.protocols.filter((p) => p.guest === g.id);
      const sos = pack.sos.filter((s) => s.guest === g.id);
      const params = pack.parameters.filter((p) => p.guest === g.id);
      const card = el("div", { class: "card offline-guest" },
        el("div", { class: "card-head" }, el("h2", {}, g.name), el("small", { class: "muted" }, [g.room && "camera " + g.room, g.age + " anni", !g.present && g.status].filter(Boolean).join(" · "))),
        g.allergies.length ? el("div", { class: "alert alert-danger" }, el("div", { class: "alert-body" }, el("strong", {}, "Allergie: "), g.allergies.map((a) => `${a.substance} (${a.severity.toLowerCase()})`).join("; "))) : el("p", { class: "muted" }, "Nessuna allergia nota."),
        g.tags.length ? el("p", {}, g.tags.map((t) => el("span", { class: "chip", style: `--chip:${t.color}` }, t.name)), g.tags.filter((t) => t.alert).map((t) => el("div", { class: "help" }, "⚠ " + t.alert))) : null,
        g.diet ? el("p", {}, el("strong", {}, "Dieta: "), g.diet) : null,
        protocols.map((p) => el("div", { class: "alert alert-warning" }, el("div", { class: "alert-body" }, el("strong", {}, p.name), ": ", p.summary, p.pending.length ? el("br") : null, p.pending.length ? "Da fare: " + p.pending.join("; ") : null))),
        params.length ? el("p", {}, el("small", { class: "muted" }, "Ultimi parametri: "), params.map((p) => el("span", { class: "pill" + (p.out_of_range ? " pill-danger" : "") }, `${p.type} ${p.value}`))) : null,
        sos.length ? el("div", {}, el("h3", {}, "Al bisogno (SOS)"), sos.map((s) => el("p", {}, el("strong", {}, s.drug), " ", s.dose, " – ", s.indication || "",
          el("br"), el("small", { class: "muted" }, this.sosInfo(s)), " ",
          pack.permissions.administration ? el("button", { class: "btn btn-sm", type: "button", onclick: () => this.sosDialog(g, s) }, "Somministra SOS") : null))) : null,
        el("p", {}, el("small", { class: "muted" }, "Contatti: "), g.contacts.length ? g.contacts.map((c) => `${c.name} (${c.relationship}) ${c.phone}`).join(" · ") : "—",
          g.doctor.name ? el("br") : null, g.doctor.name ? el("small", { class: "muted" }, `Medico curante: ${g.doctor.name} ${g.doctor.phone || ""}`) : null),
        el("div", { class: "form-actions" },
          pack.permissions.parameter ? el("button", { class: "btn btn-sm", type: "button", onclick: () => this.parameterDialog(g) }, "Parametri") : null,
          pack.permissions.diary ? el("button", { class: "btn btn-sm", type: "button", onclick: () => this.diaryDialog(g) }, "Diario") : null,
          pack.permissions.event ? el("button", { class: "btn btn-sm btn-danger", type: "button", onclick: () => this.eventDialog(g) }, "Evento") : null));
      grid.append(card);
    }
    return grid;
  };

  App.prototype.sosInfo = function (s) {
    const localGiven = this.queue.map((q) => this.decoded[q.uuid]).filter((d) => d && d.kind === "sos" && d.therapy === s.therapy).map((d) => d.occurred_at);
    const given = s.given_24h.concat(localGiven).filter((t) => Date.now() - new Date(t) < 24 * 3600 * 1000).sort();
    const parts = [];
    if (s.max_daily) parts.push(`max ${s.max_daily} in 24 ore, già somministrate ${given.length}`);
    if (s.min_interval_hours) parts.push(`intervallo minimo ${s.min_interval_hours} ore`);
    if (given.length) parts.push(`ultima ${dateTime(given[given.length - 1])}`);
    return parts.join(" · ") || "nessun limite indicato";
  };

  App.prototype.administer = function (dose, status) {
    const label = (this.pack.administration_statuses.find((s) => s.code === status) || {}).label;
    if (!window.confirm(`${this.guest(dose.guest).name} – ${dose.drug} ${dose.dose} alle ${dose.time}: ${label}?`)) return;
    this.record({ kind: "administration", therapy: dose.therapy, guest: dose.guest, day: dose.day, time: dose.time, status });
  };

  App.prototype.dialog = function (title, fields, onSave) {
    const dlg = $("#offline-dialog");
    const form = el("form", { method: "dialog" }, el("h2", {}, title), el("div", { class: "form-grid compact" }, fields),
      el("div", { class: "errors", "data-error": true, hidden: true }),
      el("div", { class: "form-actions" }, el("button", { class: "btn btn-primary", value: "save" }, "Registra"), el("button", { class: "btn", value: "cancel", formnovalidate: true }, "Annulla")));
    form.addEventListener("submit", (e) => {
      if (e.submitter && e.submitter.value === "cancel") return;
      const error = onSave(new FormData(form));
      if (error) { e.preventDefault(); const box = $("[data-error]", form); box.textContent = error; box.hidden = false; }
    });
    dlg.replaceChildren(form);
    dlg.showModal();
  };
  const field = (label, input, full) => el("div", { class: "field" + (full ? " full" : "") }, el("label", {}, label), input);

  App.prototype.sosDialog = function (guest, s) {
    const warning = this.sosInfo(s);
    this.dialog(`SOS – ${guest.name}: ${s.drug} ${s.dose}`, [
      el("p", { class: "full help" }, `Indicazione: ${s.indication || "—"} · ${warning}`),
      field("Motivo della somministrazione *", el("textarea", { name: "reason", required: true, rows: 3 }), true),
      field("Dose data", el("input", { name: "dose", value: s.dose })),
      field("Note", el("input", { name: "notes" })),
    ], (data) => {
      if (!data.get("reason").trim()) return "Indicare il motivo.";
      this.record({ kind: "sos", therapy: s.therapy, guest: guest.id, reason: data.get("reason"), dose: data.get("dose"), notes: data.get("notes") });
    });
  };

  App.prototype.parameterDialog = function (guest) {
    const types = this.pack.parameter_types;
    const select = el("select", { name: "type" }, types.map((t) => el("option", { value: t.id }, `${t.name} (${t.unit})`)));
    const second = el("input", { name: "value_2", inputmode: "decimal" });
    const secondField = field("Diastolica", second);
    const sync = () => { const t = types.find((x) => String(x.id) === select.value); secondField.hidden = !(t && t.bp); };
    select.addEventListener("change", sync);
    this.dialog(`Parametri – ${guest.name}`, [field("Parametro", select), field("Valore *", el("input", { name: "value", inputmode: "decimal", required: true })), secondField, field("Note", el("input", { name: "notes" }), true)], (data) => {
      const value = String(data.get("value") || "").replace(",", ".");
      if (!value || isNaN(Number(value))) return "Inserire un valore numerico.";
      this.record({ kind: "parameter", guest: guest.id, parameter_type: Number(data.get("type")), value, value_2: String(data.get("value_2") || "").replace(",", "."), notes: data.get("notes") });
    });
    sync();
  };

  App.prototype.diaryDialog = function (guest) {
    this.dialog(`Diario – ${guest.name}`, [field("Nota *", el("textarea", { name: "text", rows: 5, required: true }), true),
      el("div", { class: "field checkbox full" }, el("input", { type: "checkbox", name: "relevant", id: "off-rel" }), el("label", { for: "off-rel" }, "Clinicamente rilevante"))], (data) => {
      if (!data.get("text").trim()) return "Scrivere la nota.";
      this.record({ kind: "diary", guest: guest.id, text: data.get("text"), relevant: data.get("relevant") === "on" });
    });
  };

  App.prototype.eventDialog = function (guest) {
    const p = this.pack;
    this.dialog(`Evento – ${guest.name}`, [
      field("Tipo", el("select", { name: "event_type" }, p.event_types.map((t) => el("option", { value: t.code }, t.label)))),
      field("Gravità", el("select", { name: "severity" }, p.severities.map((t) => el("option", { value: t.code }, t.label)))),
      field("Durata (minuti)", el("input", { name: "duration_minutes", inputmode: "numeric" })),
      field("Descrizione *", el("textarea", { name: "description", rows: 3, required: true }), true),
      field("Interventi effettuati", el("textarea", { name: "actions_taken", rows: 2 }), true),
      el("div", { class: "field checkbox" }, el("input", { type: "checkbox", name: "doctor_notified", id: "off-doc" }), el("label", { for: "off-doc" }, "Medico avvisato")),
      el("div", { class: "field checkbox" }, el("input", { type: "checkbox", name: "emergency_services_called", id: "off-118" }), el("label", { for: "off-118" }, "Chiamato 118/112")),
    ], (data) => {
      if (!data.get("description").trim()) return "Descrivere l'evento.";
      this.record({ kind: "event", guest: guest.id, event_type: data.get("event_type"), severity: data.get("severity"), duration_minutes: data.get("duration_minutes"),
        description: data.get("description"), actions_taken: data.get("actions_taken"), doctor_notified: data.get("doctor_notified") === "on",
        emergency_services_called: data.get("emergency_services_called") === "on" });
    });
  };

  App.prototype.renderQueue = function () {
    const labels = { administration: "Somministrazione", sos: "SOS", parameter: "Parametro", diary: "Diario", event: "Evento" };
    const states = { pending: ["pill-warn", "da inviare"], synced: ["pill-ok", "inviata"], problem: ["pill-danger", "da verificare"] };
    const rows = this.queue.map((q) => {
      const d = this.decoded[q.uuid] || {};
      const g = this.guest(d.guest);
      const what = d.kind === "administration" || d.kind === "sos" ? (this.pack.doses.concat(this.pack.sos).find((x) => x.therapy === d.therapy) || {}).drug
        : d.kind === "parameter" ? ((this.pack.parameter_types.find((t) => t.id === d.parameter_type) || {}).name + " " + d.value) : (d.text || d.description || "").slice(0, 60);
      const [cls, text] = states[q.state] || ["", q.state];
      return el("tr", {}, el("td", { class: "nowrap" }, dateTime(d.occurred_at)), el("td", {}, labels[d.kind] || d.kind), el("td", {}, g.name), el("td", {}, what || ""),
        el("td", {}, el("span", { class: "pill " + cls }, text), q.result && q.result.message ? el("div", { class: "help" }, q.result.message) : null));
    });
    let info = null;
    if (this.online && !this.authenticated) {
      info = el("div", { class: "alert alert-info" }, el("div", { class: "alert-body" }, "La rete è tornata: ", el("a", { href: this.urls.login }, "accedi"), " per inviare le registrazioni."));
    } else if (this.online && this.serverUser && this.serverUser !== this.user) {
      info = el("div", { class: "alert alert-warning" }, el("div", { class: "alert-body" }, `Sul server è collegato ${this.serverUser}: per inviare queste registrazioni accedere come ${this.user}.`));
    }
    return el("div", { class: "card table-wrap" }, info, el("table", {}, el("thead", {}, el("tr", {}, ["Ora", "Tipo", "Ospite", "Dettaglio", "Stato"].map((h) => el("th", {}, h)))),
      el("tbody", {}, rows.length ? rows : el("tr", {}, el("td", { colspan: 5, class: "empty" }, "Nessuna registrazione fatta senza rete.")))));
  };

  // --- Avvio ------------------------------------------------------------------------------------
  document.addEventListener("DOMContentLoaded", function () {
    if (!subtle || !window.indexedDB) return;
    const login = document.querySelector("[data-offline-login]");
    if (login) { lockAll(); hookLogin(login); }
    document.querySelectorAll("[data-offline-logout]").forEach((f) => f.addEventListener("submit", () => { lockAll(); }));
    const body = document.body;
    if (body.dataset.offlineUser) {
      const pwd = document.querySelector("form input[name=old_password]");
      if (pwd && pwd.form.querySelector("[name=new_password1]")) hookPasswordChange(pwd.form, body.dataset.offlineUser);
      onAuthenticatedPage(body).catch(() => {});
    }
    const app = document.querySelector("[data-offline-app]");
    if (app) {
      const instance = new App(app);
      $("[data-lock]").addEventListener("click", () => instance.lock("Dati bloccati."));
      $("[data-print]").addEventListener("click", () => { instance.tab = "round"; instance.renderMain(); window.print(); });
      instance.start();
    }
  });
})();
