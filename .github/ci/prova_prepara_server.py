"""
Collaudo di scripts/prepara_server.sh: lo esegue in un terminale virtuale e risponde alle domande.

    sudo python3 .github/ci/prova_prepara_server.py <cartella del FASAS> '<risposte JSON>'

Le risposte sono coppie [testo della domanda (espressione regolare), risposta], date nell'ordine in cui lo
script le pone. Esce con il codice dello script; fallisce se lo script si ferma su una domanda imprevista.
"""
import json
import os
import pty
import re
import select
import sys
import time

folder, answers = sys.argv[1], json.loads(sys.argv[2])
timeout = int(os.environ.get("PROVA_TIMEOUT", "1800"))
pid, fd = pty.fork()
if pid == 0:
    os.chdir(folder)
    os.execvp("bash", ["bash", "scripts/prepara_server.sh"])

output, given, status, last_output = b"", 0, None, time.time()
deadline = time.time() + timeout
while time.time() < deadline:
    ready, _, _ = select.select([fd], [], [], 1)
    if ready:
        try:
            chunk = os.read(fd, 4096)
        except OSError:
            chunk = b""
        if chunk:
            output += chunk
            last_output = time.time()
            sys.stdout.write(chunk.decode(errors="replace"))
            sys.stdout.flush()
            tail = output.decode(errors="replace")[-500:]
            if given < len(answers) and re.search(answers[given][0], tail):
                time.sleep(0.3)
                os.write(fd, (answers[given][1] + "\n").encode())
                given += 1
    done, code = os.waitpid(pid, os.WNOHANG)
    if done:
        status = os.waitstatus_to_exitcode(code)
        break
    if given == len(answers) and re.search(r"\]: $|: $", output.decode(errors="replace")[-200:]) \
            and time.time() - last_output > 30:
        print("\nPROVA FALLITA: lo script aspetta una risposta non prevista")
        os.kill(pid, 9)
        sys.exit(2)
else:
    os.kill(pid, 9)
    print("\nPROVA FALLITA: tempo scaduto")
    sys.exit(2)
print(f"\n[prova] risposte date: {given}/{len(answers)}, codice di uscita: {status}")
sys.exit(status if given == len(answers) else 3)
