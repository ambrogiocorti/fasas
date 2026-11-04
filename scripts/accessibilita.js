// Controllo di accessibilità (axe-core, WCAG 2.1 A e AA) delle pagine principali, per ogni ruolo, in chiaro e in
// scuro. Fallisce se trova violazioni gravi o critiche. Serve il FASAS avviato con i dati demo:
//   python manage.py fasas_demo --ambiente-di-prova && python manage.py runserver 127.0.0.1:8765
//   npm install --no-save axe-core@4.10.2 playwright@1.49.1 && npx playwright install chromium
//   node scripts/accessibilita.js
// Il controllo automatico non sostituisce la prova con le persone: docs/PIANO_PILOTA.md.
const { chromium } = require('playwright');
const fs = require('fs');
const AXE = fs.readFileSync(require.resolve('axe-core/axe.min.js'), 'utf8');
const base = process.env.BASE || 'http://127.0.0.1:8765';
const password = process.env.PASSWORD || 'Demo-Fasas-2026!';
const plan = {
  operatore: ['/', '/sanitario/giro-farmaci/', '/giornaliero/checklist/', '/ospiti/', '/pilota/segnala/?da=/', '/impostazioni/', '/profilo/'],
  coordinatore: ['/', '/ospiti/1/', '/magazzino/farmaci/nuovo/', '/magazzino/elenco-ufficiale/', '/pilota/indicatori/', '/report/', '/report/ispezione/', '/firma/app/'],
  medico: ['/', '/firma/credenziale/'],
  admin: ['/', '/configurazione/', '/configurazione/moduli/', '/pilota/segnalazioni/', '/firma/app/pubblica/'],
  amministrativo: ['/'],
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
      await page.fill('input[name=username]', user);
      await page.fill('input[name=password]', password);
      await Promise.all([page.waitForNavigation(), page.click('button.btn-primary')]);
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
