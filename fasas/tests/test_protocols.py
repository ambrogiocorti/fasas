import datetime
from decimal import Decimal

from django.utils import timezone

from fasas.clinical.models import ClinicalEvent, ParameterReading, ParameterType
from fasas.clinical.services import register_administration
from fasas.daily.models import EvacuationRecord
from fasas.protocols.engine import run_periodic_checks
from fasas.protocols.models import Protocol, ProtocolActivation

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
