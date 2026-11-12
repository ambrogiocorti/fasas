#!/usr/bin/env python3
"""
Prova di carico del FASAS: N operatori lavorano insieme come in un turno (cruscotto, elenco ospiti, cartella,
giro farmaci, contatore notifiche e, ogni tanto, una rilevazione di parametri). Misura i tempi di risposta.

Solo su un'installazione di prova con dati di fantasia (manage.py fasas_dati_carico), MAI in produzione:
    python scripts/prova_carico.py --url http://127.0.0.1:8000 --utenti 20 --durata 60
"""
import argparse
import random
import re
import statistics
import threading
import time
from collections import defaultdict
from datetime import datetime

import requests

lock = threading.Lock()
timings = defaultdict(list)
errors = defaultdict(int)


def timed(session, name, method, url, **kwargs):
    started = time.perf_counter()
    try:
        response = session.request(method, url, timeout=30, allow_redirects=False, **kwargs)
        _plain_cookies(session)  # il server rinnova il cookie di sessione a ogni pagina
        # un rimando (es. al login) non è una pagina servita: conta come errore, tranne dopo un salvataggio
        ok = response.status_code < 300 or (method == "POST" and response.status_code == 302)
    except requests.RequestException:
        response, ok = None, False
    elapsed = (time.perf_counter() - started) * 1000
    with lock:
        timings[name].append(elapsed)
        if not ok:
            errors[name] += 1
    return response


def _plain_cookies(session):
    # In produzione i cookie sono «Secure» (solo HTTPS): in una prova locale in HTTP vanno inviati lo stesso
    for cookie in session.cookies:
        cookie.secure = False


def csrf(session, base, path):
    page = session.get(base + path, timeout=30)
    _plain_cookies(session)
    match = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', page.text)
    return page, (match.group(1) if match else "")


def operator(base, username, password, deadline, guests):
    session = requests.Session()
    _, token = csrf(session, base, "/accesso/entra/")
    login = session.post(base + "/accesso/entra/", data={"csrfmiddlewaretoken": token, "username": username,
                                                         "password": password}, allow_redirects=False, timeout=30)
    _plain_cookies(session)
    if login.status_code != 302:
        with lock:
            errors["accesso"] += 1
        return
    iteration = 0
    while time.time() < deadline:
        iteration += 1
        guest = random.choice(guests)
        timed(session, "cruscotto", "GET", base + "/")
        timed(session, "elenco ospiti", "GET", base + "/ospiti/")
        timed(session, "cartella ospite", "GET", f"{base}/ospiti/{guest}/")
        timed(session, "giro farmaci", "GET", base + "/sanitario/giro-farmaci/")
        timed(session, "contatore notifiche", "GET", base + "/notifiche/conteggio/")
        if iteration % 3 == 0:  # una rilevazione ogni tre giri, come in turno
            page, token = csrf(session, base, f"/sanitario/ospite/{guest}/parametri/rapido/")
            field = re.search(r'name="(p_\d+)"', page.text)
            if field:
                timed(session, "salva parametri", "POST", f"{base}/sanitario/ospite/{guest}/parametri/rapido/", data={
                    "csrfmiddlewaretoken": token, "occurred_at": datetime.now().strftime("%Y-%m-%dT%H:%M"),
                    field.group(1): "36.6"}, headers={"Referer": base + "/"})
        time.sleep(random.uniform(0.5, 1.5))  # tempo di lettura dell'operatore


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--utenti", type=int, default=20)
    parser.add_argument("--durata", type=int, default=60, help="secondi")
    parser.add_argument("--password", default="Carico-Prova-2026!")
    parser.add_argument("--ospiti", default="", help="id degli ospiti separati da virgola (default: 1-60)")
    args = parser.parse_args()
    guests = [int(x) for x in args.ospiti.split(",")] if args.ospiti else list(range(1, 61))
    deadline = time.time() + args.durata
    threads = [threading.Thread(target=operator, args=(args.url.rstrip("/"), f"carico{i:02d}", args.password,
                                                        deadline, guests)) for i in range(1, args.utenti + 1)]
    started = time.time()
    for thread in threads:
        thread.start()
        time.sleep(0.2)
    for thread in threads:
        thread.join()
    total = sum(len(v) for v in timings.values())
    print(f"{args.utenti} operatori per {args.durata} s: {total} richieste ({total / (time.time() - started):.1f} al secondo)")
    print(f"{'pagina':22} {'richieste':>9} {'mediana':>9} {'95%':>9} {'massimo':>9} {'errori':>7}")
    for name, values in timings.items():
        values = sorted(values)
        p95 = values[min(len(values) - 1, int(len(values) * 0.95))]
        print(f"{name:22} {len(values):9d} {statistics.median(values):7.0f}ms {p95:7.0f}ms {max(values):7.0f}ms "
              f"{errors[name]:7d}")
    if errors.get("accesso"):
        print(f"accessi falliti: {errors['accesso']}")


if __name__ == "__main__":
    main()
