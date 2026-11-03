import datetime
from decimal import Decimal

from django.urls import reverse
from django.utils import timezone

from fasas.clinical.models import ClinicalEvent, ParameterReading, ParameterType
from fasas.clinical.services import register_administration
from fasas.daily.models import EvacuationRecord
from fasas.protocols import engine
from fasas.protocols.engine import run_periodic_checks
from fasas.protocols.models import Protocol, ProtocolActionLog, ProtocolActivation

from .base import FasasTestCase


class ProtocolEngineTests(FasasTestCase):
    def test_evacuation_protocol_after_three_days_and_auto_resolve(self):
        EvacuationRecord.objects.create(guest=self.guest, outcome=True,
                                        occurred_at=timezone.now() - datetime.timedelta(days=4))
        run_periodic_checks()
        activation = ProtocolActivation.objects.get(guest=self.guest, protocol__kind="evacuation")
        self.assertIn("4 giorni", activation.trigger_summary)
        self.assertEqual(len(activation.protocol.action_list), 3)
        run_periodic_checks()  # nessun duplicato
        self.assertEqual(ProtocolActivation.objects.filter(guest=self.guest, protocol__kind="evacuation").count(), 1)
        EvacuationRecord.objects.create(guest=self.guest, outcome=True)
        activation.refresh_from_db()
        self.assertEqual(activation.status, "resolved")
        self.assertTrue(activation.auto_resolved)

    def test_no_evacuation_protocol_when_recent(self):
        EvacuationRecord.objects.create(guest=self.guest, outcome=True,
                                        occurred_at=timezone.now() - datetime.timedelta(days=1))
        run_periodic_checks()
        self.assertFalse(ProtocolActivation.objects.filter(guest=self.guest).exists())

    def test_fever_and_glycemia(self):
        temp = ParameterType.objects.get(code="temperatura")
        glyc = ParameterType.objects.get(code="glicemia")
        ParameterReading.objects.create(guest=self.guest, parameter_type=temp, value=Decimal("37.2"))
        self.assertFalse(ProtocolActivation.objects.exists())
        ParameterReading.objects.create(guest=self.guest, parameter_type=temp, value=Decimal("38.3"))
        ParameterReading.objects.create(guest=self.guest, parameter_type=glyc, value=Decimal("55"))
        kinds = set(ProtocolActivation.objects.values_list("protocol__kind", flat=True))
        self.assertEqual(kinds, {"fever", "glycemia"})

    def test_seizure_and_agitation(self):
        ClinicalEvent.objects.create(guest=self.guest, event_type="seizure", description="Crisi", duration_minutes=4)
        self.assertTrue(ProtocolActivation.objects.filter(protocol__kind="seizure").exists())
        ClinicalEvent.objects.create(guest=self.guest, event_type="agitation", description="Agitato")
        self.assertFalse(ProtocolActivation.objects.filter(protocol__kind="agitation").exists())  # soglia 2 episodi
        ClinicalEvent.objects.create(guest=self.guest, event_type="agitation", description="Ancora agitato")
        self.assertTrue(ProtocolActivation.objects.filter(protocol__kind="agitation").exists())

    def test_sos_protocol(self):
        sos = self.make_therapy(is_sos=True, schedule_times=[], sos_indication="Agitazione")
        register_administration(sos, self.doctor, sos_reason="1")
        self.assertFalse(ProtocolActivation.objects.filter(protocol__kind="sos").exists())
        register_administration(sos, self.doctor, sos_reason="2")
        self.assertTrue(ProtocolActivation.objects.filter(protocol__kind="sos").exists())

    def test_protocol_limited_to_tag(self):
        from fasas.guests.models import ClinicalTag

        diabetic = ClinicalTag.objects.create(name="Diabetico")
        protocol = Protocol.objects.get(kind="glycemia")
        protocol.applies_to_all = False
        protocol.save()
        protocol.tags.add(diabetic)
        glyc = ParameterType.objects.get(code="glicemia")
        ParameterReading.objects.create(guest=self.guest, parameter_type=glyc, value=Decimal("300"))
        self.assertFalse(ProtocolActivation.objects.exists())
        self.guest.tags.add(diabetic)
        ParameterReading.objects.create(guest=self.guest, parameter_type=glyc, value=Decimal("300"))
        self.assertTrue(ProtocolActivation.objects.exists())

    def test_activation_workflow_views(self):
        ClinicalEvent.objects.create(guest=self.guest, event_type="seizure", description="Crisi")
        activation = ProtocolActivation.objects.get()
        self.login(self.operator)
        label = activation.protocol.action_list[0]
        self.client.post(f"/protocolli/attivazione/{activation.pk}/azione/", {"action_label": label, "notes": "fatto"})
        activation.refresh_from_db()
        self.assertEqual(activation.status, "in_progress")
        self.client.post(f"/protocolli/attivazione/{activation.pk}/chiudi/", {"status": "resolved", "notes": "Crisi risolta"})
        activation.refresh_from_db()
        self.assertEqual(activation.status, "resolved")


class ProtocolValidationTests(FasasTestCase):
    """Un protocollo si attiva solo dopo che il medico ne ha validato soglie e azioni."""

    def test_unvalidated_protocol_does_not_fire_and_change_requires_new_validation(self):
        from django.urls import reverse

        from fasas.protocols.models import Protocol

        protocol = Protocol.objects.filter(kind=Protocol.Kind.FEVER).first()
        Protocol.objects.filter(pk=protocol.pk).update(validated_at=None, validated_by="")
        protocol.refresh_from_db()
        self.assertFalse(protocol.applies_to(self.guest))
        self.login(self.admin)
        self.assertContains(self.client.get("/"), "non sono ancora validati")
        self.login(self.coordinator)
        self.assertEqual(self.client.post(reverse("protocols:validate", args=[protocol.pk])).status_code, 403)
        self.login(self.doctor)
        page = self.client.get(reverse("protocols:list"))
        self.assertContains(page, "da validare: non si attiva")
        self.client.post(reverse("protocols:validate", args=[protocol.pk]))
        protocol.refresh_from_db()
        self.assertEqual((protocol.validated_by_user, protocol.is_validated), (self.doctor, True))
        self.assertTrue(protocol.applies_to(self.guest))
        # il coordinatore cambia la soglia: il protocollo torna da validare
        self.login(self.coordinator)
        self.client.post(reverse("protocols:update", args=[protocol.pk]), {
            "name": protocol.name, "kind": protocol.kind, "description": protocol.description,
            "p_fever_threshold": "38.0", "p_fever_parameter": "temperatura", "actions": protocol.actions,
            "severity": protocol.severity, "applies_to_all": "on", "active": "on"})
        protocol.refresh_from_db()
        self.assertEqual(protocol.params["threshold"], 38.0)
        self.assertFalse(protocol.is_validated)
        self.assertFalse(protocol.applies_to(self.guest))


class GuidedProtocolEditorTests(FasasTestCase):
    """Report di analisi, P1: parametri guidati con controlli di dominio, azioni confermate una volta sola."""

    def form_data(self, **extra):
        data = {"name": "Febbre alta", "kind": "fever", "description": "", "actions": "Avvisare il medico\nRinfrescare",
                "severity": "warning", "applies_to_all": "on", "active": "on",
                "p_fever_threshold": "38.5", "p_fever_parameter": "temperatura"}
        data.update(extra)
        return data

    def test_typed_parameters_are_saved_without_json(self):
        self.login(self.coordinator)
        page = self.client.get(reverse("protocols:create") + "?kind=fever")
        self.assertNotContains(page, "JSON")
        self.assertContains(page, 'data-protocol-kind="glycemia"')
        self.client.post(reverse("protocols:create"), self.form_data())
        protocol = Protocol.objects.get(name="Febbre alta")
        self.assertEqual(protocol.params, {"threshold": 38.5, "parameter": "temperatura"})

    def test_out_of_range_and_inconsistent_values_are_refused(self):
        self.login(self.coordinator)
        response = self.client.post(reverse("protocols:create"), self.form_data(p_fever_threshold="45"))
        self.assertContains(response, "minore o uguale a 41")
        response = self.client.post(reverse("protocols:create"), self.form_data(
            kind="glycemia", p_glycemia_min="140", p_glycemia_max="120", p_glycemia_parameter="glicemia"))
        self.assertContains(response, "deve superare la minima")
        self.assertFalse(Protocol.objects.filter(name="Febbre alta").exists())

    def _activation(self):
        protocol = Protocol.objects.create(name="Prova", kind="seizure", actions="Somministrare SOS\nAvvisare il medico",
                                           params={"min_duration_minutes": 0}, validated_by="Medico",
                                           validated_at=timezone.now())
        return engine.activate(protocol, self.guest, "Crisi di prova")[0]

    def test_only_listed_actions_once(self):
        activation = self._activation()
        self.login(self.operator)
        url = reverse("protocols:action_done", args=[activation.pk])
        self.client.post(url, {"action_label": "Azione inventata", "notes": ""})
        self.assertFalse(ProtocolActionLog.objects.exists())
        self.client.post(url, {"action_label": "Somministrare SOS", "notes": "ok"})
        response = self.client.post(url, {"action_label": "Somministrare SOS", "notes": "di nuovo"}, follow=True)
        self.assertContains(response, "già confermata")
        self.assertEqual(ProtocolActionLog.objects.count(), 1)

    def test_actions_of_the_moment_are_kept(self):
        activation = self._activation()
        Protocol.objects.filter(pk=activation.protocol_id).update(actions="Nuova azione")
        activation.refresh_from_db()
        self.assertEqual(activation.action_labels, ["Somministrare SOS", "Avvisare il medico"])
