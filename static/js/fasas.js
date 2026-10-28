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
})();
