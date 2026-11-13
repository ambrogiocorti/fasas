// Controllo di accessibilità (axe-core, WCAG 2.1 A e AA) delle pagine principali, per ogni ruolo, in chiaro e in
// scuro. Fallisce se trova violazioni gravi o critiche. Serve il FASAS avviato con i dati demo:
//   python manage.py fasas_demo --ambiente-di-prova && python manage.py runserver 127.0.0.1:8765
//   npm install --no-save axe-core@4.10.2 playwright@1.49.1 && npx playwright install chromium
//   node scripts/accessibilita.js
// Il controllo automatico non sostituisce la prova con le persone: docs/PIANO_PILOTA.md.
const { chromium } = require('playwright');
const fs = require('fs');
const AXE = fs.readFileSync(require.resolve('axe-core/axe.min.js'), 'utf8');
const crypto = require('crypto');

// Verifica in due passaggi (obbligatoria per coordinatore, medico e amministratore): lo script la attiva con un
// codice TOTP calcolato dalla chiave mostrata nella pagina, come farebbe l'app sul telefono.
const secrets = {};
const usedStep = {};
function totp(secret, step) {
  const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567';
  let bits = '';
  for (const c of secret.replace(/[\s=]/g, '').toUpperCase()) bits += alphabet.indexOf(c).toString(2).padStart(5, '0');
  const key = Buffer.from(bits.match(/.{8}/g).map((b) => parseInt(b, 2)));
  const counter = Buffer.alloc(8);
  counter.writeBigUInt64BE(BigInt(step));
  const h = crypto.createHmac('sha1', key).update(counter).digest();
  const o = h[h.length - 1] & 15;
  return String((h.readUInt32BE(o) & 0x7fffffff) % 1000000).padStart(6, '0');
}
async function freshCode(user) {
  let step = Math.floor(Date.now() / 30000);
  while (usedStep[user] === step) { await new Promise((r) => setTimeout(r, 1000)); step = Math.floor(Date.now() / 30000); }
  usedStep[user] = step;
  return totp(secrets[user], step);
}
async function login(page, user) {
  await page.fill('input[name=username]', user);
  await page.fill('input[name=password]', password);
  await Promise.all([page.waitForNavigation(), page.click('button.btn-primary')]);
  const where = new URL(page.url()).pathname;
  if (where.startsWith('/accesso/attiva-verifica')) {
    secrets[user] = (await page.textContent('.mono')).trim();
    await page.fill('input[name=code]', await freshCode(user));
    await Promise.all([page.waitForNavigation(), page.click('button.btn-primary')]);
  } else if (where.startsWith('/accesso/verifica')) {
    if (!secrets[user]) throw new Error(`Verifica in due passaggi già attiva per ${user}: usare un database nuovo.`);
    await page.fill('input[name=code]', await freshCode(user));
    await Promise.all([page.waitForNavigation(), page.click('button.btn-primary')]);
  }
  await page.goto(base + '/');
  if (new URL(page.url()).pathname.startsWith('/accesso')) throw new Error(`Accesso non riuscito per ${user}`);
}
const base = process.env.BASE || 'http://127.0.0.1:8765';
const password = process.env.PASSWORD || 'Demo-Fasas-2026!';
const plan = {
  operatore: ['/', '/sanitario/giro-farmaci/', '/giornaliero/checklist/', '/ospiti/', '/pilota/segnala/?da=/', '/impostazioni/', '/profilo/',
    '/attivita/', '/cassa/ospite/1/', '/turni/scadenze/mie/', '/moduli/miei/'],
  coordinatore: ['/', '/ospiti/1/', '/sanitario/ospite/1/parametri/', '/magazzino/farmaci/nuovo/', '/magazzino/elenco-ufficiale/',
    '/pilota/indicatori/', '/pilota/segnalazioni/', '/report/', '/report/ispezione/', '/firma/app/', '/sanitario/sos/da-validare/',
    '/protocolli/', '/cerca/?q=a', '/turni/', '/report/indicatori-qualita/', '/turni/scadenze/', '/famiglie/gestione/',
    '/famiglie/gestione/collegamento/1/', '/attivita/ospite/1/', '/moduli/ospite/1/', '/moduli/ospite/1/5/'],
  medico: ['/', '/firma/credenziale/', '/documenti/da-firmare/'],
  gestore: ['/', '/configurazione/', '/configurazione/moduli/', '/pilota/segnalazioni/', '/firma/app/pubblica/', '/audit/', '/moduli/', '/moduli/3/',
    '/moduli/3/distribuisci/', '/moduli/intestazione/'],
  ufficio: ['/', '/amministrazione/prospetti/', '/amministrazione/presenze/', '/cassa/', '/cassa/ospite/1/', '/moduli/ospiti/'],
  familiare: ['/famiglie/1/'],
};
(async () => {
  const browser = await chromium.launch();
  const results = {};
  let pages = 0;
  for (const [user, urls] of Object.entries(plan)) {
    for (const scheme of ['light', 'dark']) {
      const ctx = await browser.newContext({ colorScheme: scheme, viewport: { width: 1280, height: 900 } });
      const page = await ctx.newPage();
      await page.goto(base + '/accesso/entra/');
      if (scheme === 'light' && user === 'operatore') await scan(page, 'login', scheme);
      await login(page, user);
      for (const url of urls) {
        const r = await page.goto(base + url);
        if (!r || r.status() >= 400) { console.log('ERRORE', r && r.status(), user, url); continue; }
        await scan(page, `${user} ${url}`, scheme);
      }
      await ctx.close();
    }
  }
  async function scan(page, label, scheme) {
    pages += 1;
    await page.addScriptTag({ content: AXE });
    const res = await page.evaluate(async () => await window.axe.run(document, {
      runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'] } }));
    for (const v of res.violations) {
      if (!['serious', 'critical'].includes(v.impact)) continue;
      const key = `${v.id} (${v.impact})`;
      results[key] = results[key] || { help: v.help, where: new Set(), samples: new Set() };
      results[key].where.add(`${label} [${scheme}]`);
      v.nodes.slice(0, 3).forEach((n) => results[key].samples.add(n.target.join(' ') + (n.any[0] ? ' :: ' + n.any[0].message : '')));
    }
  }
  console.log(`Pagine controllate: ${pages}`);
  for (const [key, r] of Object.entries(results)) {
    console.log(`\n${key}: ${r.help}`);
    console.log('  pagine: ' + [...r.where].slice(0, 6).join(' | ') + (r.where.size > 6 ? ` (+${r.where.size - 6})` : ''));
    [...r.samples].slice(0, 6).forEach((s) => console.log('  - ' + s.slice(0, 220)));
  }
  console.log(`\nViolazioni gravi: ${Object.keys(results).length}`);
  await browser.close();
  process.exitCode = Object.keys(results).length ? 1 : 0;
})();
