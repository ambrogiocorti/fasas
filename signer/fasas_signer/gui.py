"""
Finestra del FASAS Signer (tkinter, incluso in Python per Windows, macOS e Linux).

La rete gira in un thread separato; le finestre di conferma e del PIN si aprono nel thread dell'interfaccia.
"""
import queue
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from . import __version__, config
from .card import CardError, current_os, make_card
from .client import ServerClient, ServerError
from .console import describe
from .engine import Service, UserInterface

PLATFORM = {"windows": "windows", "macos": "macos", "linux": "linux"}.get(current_os(), "other")


class TkUI(UserInterface):
    def __init__(self, app):
        self.app = app

    def _call(self, func, *args):
        """Esegue func nel thread dell'interfaccia e ne attende il risultato."""
        done, box = threading.Event(), {}

        def run():
            try:
                box["value"] = func(*args)
            finally:
                done.set()

        self.app.calls.put(run)
        done.wait()
        return box.get("value")

    def confirm(self, request):
        return self._call(self.app.confirm_dialog, request)

    def ask_pin(self, request, message=None):
        return self._call(self.app.pin_dialog, request, message)

    def info(self, text):
        self.app.calls.put(lambda: self.app.set_status(text))

    def done(self, request, result):
        level = (result.get("verification") or {}).get("level", "PAdES")
        self.app.calls.put(lambda: (self.app.set_status("Documento firmato correttamente."),
                                    messagebox.showinfo("FASAS Signer", f"Documento firmato correttamente ({level}).")))

    def failed(self, request, message):
        self.app.calls.put(lambda: (self.app.set_status(f"Firma non riuscita: {message}"),
                                    messagebox.showerror("FASAS Signer", f"Firma non riuscita: {message}")))


class App:
    def __init__(self):
        self.settings = config.load()
        self.root = tk.Tk()
        self.root.title(f"FASAS Signer {__version__}")
        self.root.geometry("560x360")
        self.calls = queue.Queue()
        self.status = tk.StringVar(value="Avvio…")
        self.components = tk.StringVar(value="")
        self.service = None
        frame = ttk.Frame(self.root, padding=16)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="FASAS Signer – firma con CIE", font=("TkDefaultFont", 14, "bold")).pack(anchor="w")
        ttk.Label(frame, text="Firma elettronica avanzata. Il PIN si digita solo qui e va solo alla carta.",
                  wraplength=520).pack(anchor="w", pady=(2, 12))
        if self.settings.get("carta_di_prova"):
            tk.Label(frame, text="CARTA DI PROVA – non è una CIE: le firme non hanno valore legale",
                     bg="#b00020", fg="white", font=("TkDefaultFont", 11, "bold"), padx=8, pady=6).pack(fill="x", pady=(0, 10))
        ttk.Label(frame, textvariable=self.status, wraplength=520, font=("TkDefaultFont", 11)).pack(anchor="w")
        ttk.Label(frame, textvariable=self.components, wraplength=520, foreground="#555").pack(anchor="w", pady=8)
        buttons = ttk.Frame(frame)
        buttons.pack(anchor="w", pady=8)
        ttk.Button(buttons, text="Abbina al FASAS…", command=self.pair_dialog).pack(side="left", padx=(0, 8))
        ttk.Button(buttons, text="Controlla lettore e carta", command=self.check_components).pack(side="left")
        self.root.after(100, self._drain)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.start_service()

    def _drain(self):
        while True:
            try:
                self.calls.get_nowait()()
            except queue.Empty:
                break
        self.root.after(100, self._drain)

    def set_status(self, text):
        self.status.set(text)

    def card(self):
        return make_card(self.settings)

    def check_components(self):
        try:
            info = self.card().status()
        except CardError as exc:
            self.components.set(str(exc))
            return
        readers = ", ".join(info.get("readers", [])) or "nessuno"
        self.components.set(
            f"Software CIE: {'trovato' if info.get('middleware_found') else 'NON trovato'}"
            f"{' (' + info['middleware_path'] + ')' if info.get('middleware_path') else ''}\n"
            f"Lettori: {readers}\nCarta sul lettore: {'sì' if info.get('card_present') else 'no'}")

    def start_service(self):
        self.check_components()
        if not self.settings.get("server") or not self.settings.get("token"):
            self.set_status("Non abbinato: nel FASAS apri Impostazioni › Firma digitale › «Abbina un nuovo FASAS Signer».")
            return
        try:
            client = ServerClient(self.settings["server"], self.settings["token"],
                                  allow_http=self.settings.get("allow_http", False))
            me = client.me()
        except (ValueError, ServerError) as exc:
            self.set_status(str(exc))
            return
        try:
            card = self.card()
        except CardError as exc:
            self.set_status(str(exc))
            return
        self.set_status(f"In linea come {me['user']}: in attesa di richieste di firma dal FASAS.")
        self.service = Service(client, card, TkUI(self))
        threading.Thread(target=self.service.run, daemon=True).start()

    def pair_dialog(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Abbina al FASAS")
        dialog.transient(self.root)
        dialog.grab_set()
        default = "http://127.0.0.1:8000/" if self.settings.get("carta_di_prova") else "https://"
        server = tk.StringVar(value=self.settings.get("server", default))
        code = tk.StringVar()
        name = tk.StringVar(value=self.settings.get("name", "PC con lettore CIE"))
        for row, (label, var) in enumerate((("Indirizzo del FASAS", server), ("Codice di abbinamento", code),
                                            ("Nome di questo computer", name))):
            ttk.Label(dialog, text=label).grid(row=row, column=0, sticky="w", padx=12, pady=6)
            ttk.Entry(dialog, textvariable=var, width=38).grid(row=row, column=1, padx=12, pady=6)

        def pair():
            try:
                client = ServerClient(server.get(), allow_http=self.settings.get("allow_http", False))
                data = client.pair(code.get(), name.get(), PLATFORM)
            except (ValueError, ServerError) as exc:
                messagebox.showerror("Abbinamento", str(exc), parent=dialog)
                return
            self.settings.update({"server": server.get().strip(), "token": data["token"], "name": name.get()})
            config.save(self.settings)
            dialog.destroy()
            messagebox.showinfo("Abbinamento", f"Abbinato all'utente {data['user']}.")
            if self.service:
                self.service.stop_event.set()
            self.start_service()

        ttk.Button(dialog, text="Abbina", command=pair).grid(row=3, column=1, sticky="e", padx=12, pady=12)

    def _dialog(self, title):
        dialog = tk.Toplevel(self.root)
        dialog.title(title)
        dialog.transient(self.root)
        dialog.resizable(False, False)
        dialog.grab_set()
        dialog.lift()
        dialog.focus_force()
        return dialog

    def confirm_dialog(self, request):
        """Prima di qualsiasi operazione sulla carta: cosa si firma e codice di controllo da confrontare col FASAS."""
        self.root.deiconify()
        dialog = self._dialog("Richiesta di firma con CIE")
        result = {"ok": False}
        ttk.Label(dialog, text="Richiesta di firma con CIE", font=("TkDefaultFont", 13, "bold")).pack(padx=18, pady=(16, 6))
        ttk.Label(dialog, text=describe(request), justify="left", wraplength=440).pack(padx=18, anchor="w")
        ttk.Label(dialog, text=request["verify_code"], font=("TkFixedFont", 22, "bold")).pack(pady=10)
        ttk.Label(dialog, text="Firma elettronica avanzata con la tua CIE. Firma solo se il codice coincide con "
                               "quello mostrato nella pagina del FASAS.", wraplength=440).pack(padx=18)

        def answer(value):
            result["ok"] = value
            dialog.destroy()

        row = ttk.Frame(dialog)
        row.pack(pady=14)
        sign = ttk.Button(row, text="Firma con CIE", command=lambda: answer(True))
        sign.pack(side="left", padx=6)
        ttk.Button(row, text="Rifiuta", command=lambda: answer(False)).pack(side="left", padx=6)
        sign.focus_set()
        dialog.bind("<Return>", lambda _e: answer(True))
        dialog.bind("<Escape>", lambda _e: answer(False))
        dialog.protocol("WM_DELETE_WINDOW", lambda: answer(False))
        self.root.wait_window(dialog)
        return result["ok"]

    def pin_dialog(self, request, message=None):
        dialog = self._dialog("PIN della CIE")
        result = {"pin": None}
        ttk.Label(dialog, text=f"Codice di controllo: {request['verify_code']}",
                  font=("TkDefaultFont", 13, "bold")).pack(padx=16, pady=(16, 4))
        hint = ("Carta di prova: digita il PIN scelto alla creazione (di solito 1234)." if self.settings.get("carta_di_prova")
                else "Appoggia la CIE sul lettore e digita le ultime 4 cifre del PIN.")
        ttk.Label(dialog, text=hint).pack(padx=16)
        if message:
            ttk.Label(dialog, text=message, foreground="#b00020").pack(padx=16, pady=4)
        pin = tk.StringVar()
        entry = ttk.Entry(dialog, textvariable=pin, show="•", width=12, justify="center")
        entry.pack(pady=10)
        entry.focus_set()

        def ok(_event=None):
            value = pin.get().strip()
            if not value.isdigit() or not 4 <= len(value) <= 8:
                messagebox.showwarning("PIN", "Il PIN è composto da cifre (di norma le ultime 4).", parent=dialog)
                return
            result["pin"] = value
            pin.set("")
            dialog.destroy()

        def cancel():
            pin.set("")
            dialog.destroy()

        entry.bind("<Return>", ok)
        dialog.bind("<Escape>", lambda _e: cancel())
        row = ttk.Frame(dialog)
        row.pack(pady=(0, 14))
        ttk.Button(row, text="Firma", command=ok).pack(side="left", padx=6)
        ttk.Button(row, text="Annulla", command=cancel).pack(side="left", padx=6)
        dialog.protocol("WM_DELETE_WINDOW", cancel)
        self.root.wait_window(dialog)
        return result["pin"]

    def close(self):
        if self.service:
            self.service.stop_event.set()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def main():
    App().run()
