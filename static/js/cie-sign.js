/* FASAS Sign – stato della firma con CIE e compatibilità del dispositivo. */
(function () {
  "use strict";

  // Compatibilità: mostra le istruzioni per il sistema in uso
  const compat = document.querySelector("[data-compat]");
  if (compat) {
    const ua = navigator.userAgent || "";
    const os = /android/i.test(ua) ? "android"
      : /iphone|ipad|ipod/i.test(ua) || (/macintosh/i.test(ua) && navigator.maxTouchPoints > 1) ? "ios"
      : /windows/i.test(ua) ? "windows" : /macintosh|mac os x/i.test(ua) ? "macos" : /linux|x11/i.test(ua) ? "linux" : "";
    const match = os && compat.querySelector(`[data-os="${os}"]`);
    if (match) {
      match.hidden = false;
      compat.querySelector('[data-os="other"]').hidden = true;
    }
  }

  const panel = document.getElementById("cie-panel");
  if (!panel) return;
  const url = panel.dataset.statusUrl;
  const steps = Array.from(panel.querySelectorAll("[data-step]"));
  const box = (role) => panel.querySelector(`[data-role="${role}"]`);
  const setBox = (role, text) => {
    const el = box(role);
    el.hidden = !text;
    if (text) el.querySelector(".alert-body").textContent = text;
  };
  let timer = null;

  function hintFor(s) {
    if (s.error_code === "pin_wrong") {
      return "PIN errato." + (s.pin_attempts_left != null ? " Tentativi rimasti: " + s.pin_attempts_left + "." : "") +
        " Riprova su FASAS Signer: dopo 3 errori il PIN si blocca.";
    }
    if (s.status === "waiting") {
      if (!s.devices) return "Nessun FASAS Signer abbinato: abbinalo in Impostazioni › Firma digitale.";
      if (!s.device_online) return "Avvia FASAS Signer sul computer con il lettore: la richiesta comparirà lì.";
      if (s.error_code === "card_absent") return "Appoggia la CIE sul lettore e tienila ferma.";
      return s.device ? "Richiesta presa in carico da " + s.device + ": appoggia la CIE sul lettore."
        : "Conferma la richiesta su FASAS Signer (controlla che il codice coincida).";
    }
    if (s.status === "card") return "Carta letta: controllo del certificato e preparazione del documento…";
    if (s.status === "authorizing") return "Digita su FASAS Signer il PIN della CIE (sul computer le ultime 4 cifre).";
    if (s.status === "signing") return "Non allontanare la carta dal lettore.";
    if (s.status === "verifying") return "Verifica crittografica della firma e archiviazione del documento…";
    return "";
  }

  function render(s) {
    panel.dataset.status = s.status;
    const failed = ["failed", "cancelled", "expired"].includes(s.status);
    const signed = s.status === "signed";
    steps.forEach((li, i) => {
      li.classList.toggle("done", signed || (s.step !== null && i < s.step));
      li.classList.toggle("current", !signed && s.step === i);
    });
    panel.classList.toggle("is-failed", failed);
    setBox("hint", s.active ? hintFor(s) : "");
    setBox("error", failed ? s.label + (s.error ? ": " + s.error : "") : "");
    let done = "";
    if (s.status === "signed") {
      const v = s.verification || {};
      done = "Documento firmato correttamente (" + (v.level || "PAdES") + ", firma elettronica avanzata con CIE)" +
        (s.version ? ": creata la versione " + s.version + "." : ".");
      if (v.trusted === false) done += " Attenzione: " + (v.note || "catena di certificazione non verificata") + ".";
      if (v.chain_note) done += " " + v.chain_note;
    }
    setBox("done", done);
    box("cancel").hidden = !s.active || s.status === "verifying";
    box("retry").hidden = !failed;
    const result = box("result");
    result.hidden = !s.result_url;
    if (s.result_url) {
      result.href = s.result_url;
      result.textContent = s.version ? "Vai al documento firmato" : "Scarica il PDF di prova firmato";
    }
    box("expiry").textContent = s.active && s.expires_in > 0
      ? "La richiesta scade tra " + Math.floor(s.expires_in / 60) + ":" + String(s.expires_in % 60).padStart(2, "0") + "." : "";
    if (!s.active) clearInterval(timer);
  }

  async function poll() {
    try {
      const r = await fetch(url, { credentials: "same-origin", cache: "no-store", headers: { "X-Requested-With": "fetch" } });
      if (r.ok) render(await r.json());
    } catch (e) { /* rete assente: si riprova al giro successivo */ }
  }

  poll();
  timer = setInterval(poll, 1500);
})();
