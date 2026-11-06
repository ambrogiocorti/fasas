#!/usr/bin/env python3
"""
Prova completa della versione cloud in esecuzione (usata dalla CI e utile dopo ogni aggiornamento su un servizio
di prova). Fa da browser dietro il dominio: controllo di salute, HTTPS, dominio, file statici, accesso, caricamento
di un documento finto, scaricamento, file e backup nell'object storage. Nessun dato reale.

Variabili (con i valori della CI come predefiniti):
  PROVA_URL           indirizzo del FASAS               (http://127.0.0.1:8123)
  PROVA_DOMINIO       dominio pubblico (FASAS_DOMAIN)   (fasas.prova.it)
  PROVA_UTENTE/PROVA_PASSWORD   amministratore
  PROVA_TOKEN         FASAS_HEALTH_TOKEN
  PROVA_S3            endpoint S3 (vuoto = non controllare i bucket)
  PROVA_BUCKET_FILE / PROVA_BUCKET_BACKUP
Argomento: numero dell'ospite di prova su cui caricare il documento.
"""
import os
import re
import sys
import time

import requests

BASE = os.environ.get("PROVA_URL", "http://127.0.0.1:8123").rstrip("/")
HOST = os.environ.get("PROVA_DOMINIO", "fasas.prova.it")
HTTPS = {"Host": HOST, "X-Forwarded-Proto": "https", "X-Forwarded-For": "93.40.1.2"}
cookies = {}
failures = []


def check(label, condition, detail=""):
    print(("OK  " if condition else "NO  ") + label + (f"  [{detail}]" if detail != "" else ""))
    if not condition:
        failures.append(label)


def get(path, **kwargs):
    response = requests.get(BASE + path, headers={**HTTPS, **kwargs.pop("headers", {})}, cookies=cookies,
                            allow_redirects=False, timeout=60, **kwargs)
    cookies.update(response.cookies.get_dict())
    return response


def post(path, data, files=None):
    headers = {**HTTPS, "Referer": f"https://{HOST}{path}", "Origin": f"https://{HOST}"}
    response = requests.post(BASE + path, data={**data, "csrfmiddlewaretoken": cookies.get("csrftoken", "")},
                             files=files, headers=headers, cookies=cookies, allow_redirects=False, timeout=120)
    cookies.update(response.cookies.get_dict())
    return response


def health_details():
    token = os.environ.get("PROVA_TOKEN", "token-di-prova-salute")
    response = requests.get(BASE + "/salute/", headers={"Host": "10.17.3.4", "Authorization": f"Bearer {token}"},
                            timeout=30)
    return response.json().get("checks", {})


def main():
    guest = sys.argv[1]
    response = requests.get(BASE + "/salute/", headers={"Host": "10.17.3.4:8123"}, timeout=30)
    check("salute con Host interno del servizio di hosting", response.status_code == 200, response.text)
    # il pianificatore recupera all'avvio i job della notte: si attende il backup con la copia fuori sede
    for _ in range(60):
        checks = health_details()
        if checks.get("backup", {}).get("status") == "ok" and checks.get("job", {}).get("status") == "ok":
            break
        time.sleep(3)
    for name in ("database", "file", "backup", "audit", "job"):
        check(f"salute: {name}", checks.get(name, {}).get("status") == "ok", checks.get(name))
    if "backup_fuori_sede" in checks:
        check("salute: backup_fuori_sede", checks["backup_fuori_sede"]["status"] == "ok", checks["backup_fuori_sede"])

    response = requests.get(BASE + "/accesso/entra/", headers={"Host": HOST}, allow_redirects=False, timeout=30)
    check("da HTTP a HTTPS", response.status_code == 301 and response.headers["Location"].startswith(f"https://{HOST}/"),
          response.headers.get("Location"))
    response = requests.get(BASE + "/accesso/entra/", headers={**HTTPS, "Host": "altro-dominio.example"},
                            allow_redirects=False, timeout=30)
    check("dominio non autorizzato rifiutato", response.status_code == 400, response.status_code)
    response = get("/static/css/fasas.css", headers={"Accept-Encoding": "gzip"})
    check("file statici serviti dal FASAS, compressi", response.status_code == 200
          and response.headers.get("Content-Encoding") == "gzip", f"{response.status_code} {response.headers.get('Content-Encoding')}")
    check("HSTS", "max-age" in response.headers.get("Strict-Transport-Security", ""))

    response = get("/accesso/entra/")
    check("pagina di accesso", response.status_code == 200 and "csrftoken" in cookies, response.status_code)
    response = post("/accesso/entra/", {"username": os.environ.get("PROVA_UTENTE", "amministratore"),
                                        "password": os.environ.get("PROVA_PASSWORD", "Prova-Cloud-2026!x")})
    check("accesso del primo amministratore", response.status_code == 302 and response.headers["Location"] == "/",
          f"{response.status_code} {response.headers.get('Location')}")
    check("cookie di sessione solo HTTPS", "secure" in response.headers.get("Set-Cookie", "").lower())
    check("cruscotto", get("/").status_code == 200)

    page = get(f"/documenti/ospite/{guest}/nuovo/").text
    options = re.findall(r'<option value="([^"]+)"', page.split('name="category"', 1)[-1])
    content = b"%PDF-1.4\n% documento di prova senza dati reali\n" + b"x" * 5000 + b"\n%%EOF\n"
    response = post(f"/documenti/ospite/{guest}/nuovo/", {"category": options[0] if options else "", "title": "Prova"},
                    files={"file": ("prova.pdf", content, "application/pdf")})
    check("caricamento di un documento", response.status_code == 302, response.status_code)
    page = get(response.headers.get("Location", "/")).text
    version = re.search(r"/documenti/versione/(\d+)/scarica/", page)
    check("scheda del documento", version is not None)
    if version:
        response = get(f"/documenti/versione/{version.group(1)}/scarica/")
        check("scaricato uguale all'originale (decifrato dal FASAS)", response.content == content, len(response.content))

    endpoint = os.environ.get("PROVA_S3", "http://127.0.0.1:5055")
    if endpoint:
        import boto3

        s3 = boto3.client("s3", endpoint_url=endpoint, region_name="eu-central-1",
                          aws_access_key_id=os.environ.get("PROVA_S3_ID", "prova"),
                          aws_secret_access_key=os.environ.get("PROVA_S3_SEGRETO", "prova"))
        objects = s3.list_objects_v2(Bucket=os.environ.get("PROVA_BUCKET_FILE", "fasas-documenti")).get("Contents", [])
        check("documento nel bucket dei file", len(objects) >= 1, [o["Key"] for o in objects])
        if objects:
            body = s3.get_object(Bucket=os.environ.get("PROVA_BUCKET_FILE", "fasas-documenti"),
                                 Key=objects[-1]["Key"])["Body"].read()
            check("nel bucket solo dati cifrati", content not in body and b"documento di prova" not in body)
        backups = s3.list_objects_v2(Bucket=os.environ.get("PROVA_BUCKET_BACKUP", "fasas-backup")).get("Contents", [])
        check("backup cifrato nel bucket dei backup", any(o["Key"].endswith(".fbk") for o in backups),
              [o["Key"] for o in backups])

    print("TUTTO OK" if not failures else f"NON RIUSCITI: {', '.join(failures)}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
