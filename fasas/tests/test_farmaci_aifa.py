"""Elenco ufficiale dei medicinali (open data AIFA) e controllo della confezione nel giro farmaci.
I file sono costruiti per il test sul formato atteso: il file vero va provato al primo caricamento."""
import io

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.urls import reverse

from fasas.pharmacy.models import OfficialListImport, OfficialPackage
from fasas.pharmacy.official import OfficialListError, aic_in_code, import_list, normalize_aic, parse, search

from .base import FasasTestCase

CSV = ("codice_aic;cod_farmaco;cod_confezione;denominazione;descrizione;codice_ditta;ragione_sociale;"
       "stato_amministrativo;tipo_procedura;forma;codice_atc;pa_associati;link\n"
       "012745093;012745;093;TACHIPIRINA;\"500 mg compresse\" 20 compresse;1;ANGELINI S.p.A.;Autorizzata;N;"
       "COMPRESSA;N02BE01;PARACETAMOLO;\n"
       "12745168;012745;168;TACHIPIRINA;1000 mg compresse 16 compresse;1;ANGELINI S.p.A.;Autorizzata;N;"
       "COMPRESSA;N02BE01;PARACETAMOLO;\n"
       ";;;SENZA CODICE;x;;;;;;;;\n").encode("utf-8")


class OfficialListTests(FasasTestCase):
    def test_parse_csv_semicolon(self):
        packages, skipped = parse(CSV, "confezioni.csv")
        self.assertEqual(skipped, 1)
        self.assertEqual([p["aic"] for p in packages], ["012745093", "012745168"])
        self.assertEqual(packages[0]["ingredients"], "PARACETAMOLO")
        self.assertEqual(packages[0]["atc"], "N02BE01")

    def test_parse_split_codes_comma_and_title_row(self):
        data = ("Elenco medicinali al 01/11/2026\n"
                "Codice farmaco,Codice confezione,Farmaco,Confezione,Principio attivo,Titolare AIC\n"
                "34567,12,ESEMPIO,10 mg 30 compresse,esempina,Ditta Srl\n").encode("cp1252")
        packages, _ = parse(data, "lista.csv")
        self.assertEqual(packages[0]["aic"], "034567012")
        self.assertEqual(packages[0]["holder"], "Ditta Srl")

    def test_parse_xlsx(self):
        from openpyxl import Workbook

        wb = Workbook()
        wb.active.append(["AIC", "Denominazione", "ATC"])
        wb.active.append([12745093, "TACHIPIRINA", "N02BE01"])
        buffer = io.BytesIO()
        wb.save(buffer)
        packages, _ = parse(buffer.getvalue(), "lista.xlsx")
        self.assertEqual(packages[0]["aic"], "012745093")

    def test_unknown_header_refused(self):
        with self.assertRaises(OfficialListError):
            parse(b"a;b;c\n1;2;3\n", "x.csv")

    def test_codes(self):
        self.assertEqual(normalize_aic("12745093"), "012745093")
        self.assertEqual(normalize_aic("1234567890"), "")
        self.assertTrue(aic_in_code("A012745093", "012745093"))       # bollino (codice 39)
        self.assertTrue(aic_in_code("]d2010801274509300", "12745093"))  # codice più lungo che contiene l'AIC
        self.assertFalse(aic_in_code("012745168", "012745093"))

    def test_import_replaces_and_search(self):
        import_list(CSV, "confezioni.csv", self.coordinator)
        import_list(CSV, "confezioni.csv", self.coordinator)
        self.assertEqual(OfficialPackage.objects.count(), 2)
        self.assertEqual(OfficialListImport.objects.count(), 2)
        self.assertEqual([p.aic for p in search("tachi 1000")], ["012745168"])
        self.assertEqual(sorted(p.aic for p in search("paracetamolo")), ["012745093", "012745168"])
        self.assertEqual([p.aic for p in search("A012745093")], ["012745093"])
        self.assertEqual([p.aic for p in search("0127451")], ["012745168"])

    def test_command(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "confezioni.csv"
            path.write_bytes(CSV)
            out = io.StringIO()
            call_command("fasas_farmaci_aifa", str(path), stdout=out)
        self.assertIn("2 confezioni caricate", out.getvalue())

    def test_web_upload_search_and_drug_form(self):
        self.login(self.coordinator)
        url = reverse("pharmacy:official_list")
        self.client.post(url, {"file": SimpleUploadedFile("confezioni.csv", CSV, "text/csv")})
        self.assertContains(self.client.get(url + "?q=tachipirina"), "012745093")
        data = self.client.get(reverse("pharmacy:official_search") + "?q=012745093").json()
        self.assertEqual(data["results"][0]["ingredients"], "PARACETAMOLO")
        self.assertContains(self.client.get(reverse("pharmacy:drug_create")), "data-official-search")

    def test_operator_cannot_upload(self):
        self.login(self.doctor)
        response = self.client.post(reverse("pharmacy:official_list"),
                                    {"file": SimpleUploadedFile("confezioni.csv", CSV, "text/csv")})
        self.assertEqual(response.status_code, 403)

    def test_drug_aic_must_be_nine_digits(self):
        from fasas.pharmacy.forms import DrugForm

        form = DrugForm(data={"name": "X", "active_ingredient": "x", "aic_code": "12A", "form": "tablet",
                              "stock_unit": "cp", "min_stock": "0", "active": "on"})
        self.assertIn("aic_code", form.errors)


class PackCheckTests(FasasTestCase):
    def test_board_shows_pack_check_when_drug_has_aic(self):
        drug = self.make_drug()
        self.make_therapy(drug=drug, schedule_times=["08:00", "14:30", "21:30"])
        self.login(self.operator)
        url = reverse("clinical:board")
        self.assertNotContains(self.client.get(url), "data-pack-check")
        drug.aic_code = "012745093"
        drug.save()
        page = self.client.get(url)
        self.assertContains(page, "data-pack-check")
        self.assertContains(page, 'data-aic="012745093"')
