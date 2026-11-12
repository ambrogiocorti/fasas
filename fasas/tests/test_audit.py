from django.db import connection

from fasas.audit.context import audit_context
from fasas.audit.models import AuditLog, ImmutableRecordError
from fasas.audit.services import verify_chain
from fasas.clinical.models import ClinicalEvent

from .base import FasasTestCase


class AuditLogTests(FasasTestCase):
    def test_create_and_update_are_tracked_with_old_and_new_values(self):
        with audit_context(user=self.operator):
            event = ClinicalEvent.objects.create(guest=self.guest, event_type="fall", description="Caduta in bagno")
        with audit_context(user=self.coordinator, reason="Correzione descrizione"):
            event.description = "Caduta in corridoio"
            event.save()
        entries = AuditLog.objects.filter(object_id=str(event.pk), content_type__model="clinicalevent").order_by("id")
        self.assertEqual([e.action for e in entries], ["create", "update"])
        update = entries.last()
        self.assertEqual(update.username, "coord")
        self.assertEqual(update.changes["description"], ["Caduta in bagno", "Caduta in corridoio"])
        self.assertEqual(update.reason, "Correzione descrizione")
        self.assertEqual(update.guest_id, self.guest.pk)
        self.assertEqual(event.created_by, self.operator)

    def test_entries_cannot_be_modified_or_deleted(self):
        entry = AuditLog.objects.first()
        entry.reason = "manomissione"
        with self.assertRaises(ImmutableRecordError):
            entry.save()
        with self.assertRaises(ImmutableRecordError):
            entry.delete()
        with self.assertRaises(ImmutableRecordError):
            AuditLog.objects.all().delete()
        with self.assertRaises(ImmutableRecordError):
            AuditLog.objects.update(reason="x")

    def test_hash_chain_detects_tampering(self):
        ok, count, _ = verify_chain()
        self.assertTrue(ok)
        self.assertGreater(count, 0)
        if connection.vendor == "postgresql":
            from django.db import DatabaseError, transaction

            with self.assertRaises(DatabaseError), transaction.atomic(), connection.cursor() as cursor:
                cursor.execute("UPDATE audit_auditlog SET reason = 'alterato'")
            return
        target = AuditLog.objects.order_by("id")[1]
        with connection.cursor() as cursor:
            cursor.execute("UPDATE audit_auditlog SET reason = 'alterato' WHERE id = %s", [target.pk])
        ok, _, broken = verify_chain()
        self.assertFalse(ok)
        self.assertEqual(broken, target.pk)

    def test_voiding_is_logged_as_void(self):
        with audit_context(user=self.operator):
            event = ClinicalEvent.objects.create(guest=self.guest, event_type="fall", description="x")
        event.void(self.coordinator, "Registrata per errore sull'ospite sbagliato")
        self.assertFalse(ClinicalEvent.objects.filter(pk=event.pk).exists())
        self.assertTrue(ClinicalEvent.all_objects.filter(pk=event.pk).exists())
        self.assertTrue(AuditLog.objects.filter(action="void", object_id=str(event.pk)).exists())
