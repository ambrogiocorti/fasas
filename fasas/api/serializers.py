from rest_framework import serializers

from fasas.clinical.models import ClinicalEvent, ParameterReading, Therapy, TherapyAdministration
from fasas.daily.models import DiaryEntry, EvacuationRecord
from fasas.guests.models import Allergy, Guest
from fasas.notifications.models import Notification


class AllergySerializer(serializers.ModelSerializer):
    class Meta:
        model = Allergy
        fields = ["id", "kind", "category", "substance", "reaction", "severity"]


class GuestSerializer(serializers.ModelSerializer):
    tags = serializers.StringRelatedField(many=True)
    allergies = AllergySerializer(many=True, read_only=True)

    class Meta:
        model = Guest
        fields = ["id", "first_name", "last_name", "birth_date", "room", "status", "diet", "diet_texture", "tags",
                  "allergies"]


class TherapySerializer(serializers.ModelSerializer):
    drug = serializers.StringRelatedField()
    dose = serializers.CharField(source="dose_display")

    class Meta:
        model = Therapy
        fields = ["id", "guest", "drug", "dose", "route", "schedule_times", "is_sos", "sos_indication", "status",
                  "instructions", "start_date", "end_date"]


class RecordSerializer(serializers.ModelSerializer):
    created_by = serializers.StringRelatedField(read_only=True)
    shift_date = serializers.DateField(read_only=True)
    shift = serializers.CharField(read_only=True)

    def validate(self, attrs):
        from fasas.core.locking import creation_decision

        guest = attrs.get("guest") or getattr(self.instance, "guest", None)
        decision = creation_decision(guest, attrs.get("occurred_at"))
        if self.instance is None and not decision.allowed:
            raise serializers.ValidationError(decision.message)
        return attrs


class AdministrationSerializer(RecordSerializer):
    class Meta:
        model = TherapyAdministration
        fields = ["id", "guest", "therapy", "scheduled_date", "scheduled_time", "occurred_at", "status", "dose_given",
                  "notes", "is_sos", "sos_reason", "validation_status", "shift_date", "shift", "created_by"]
        read_only_fields = ["guest", "is_sos", "validation_status"]

    def validate(self, attrs):
        therapy = attrs["therapy"]
        attrs["guest"] = therapy.guest
        if therapy.is_sos and not attrs.get("sos_reason"):
            raise serializers.ValidationError({"sos_reason": "Il motivo è obbligatorio per i farmaci SOS."})
        return super().validate(attrs)


class ParameterReadingSerializer(RecordSerializer):
    class Meta:
        model = ParameterReading
        fields = ["id", "guest", "parameter_type", "value", "value_2", "occurred_at", "notes", "shift_date", "shift",
                  "created_by"]


class ClinicalEventSerializer(RecordSerializer):
    class Meta:
        model = ClinicalEvent
        fields = ["id", "guest", "event_type", "severity", "occurred_at", "duration_minutes", "description",
                  "actions_taken", "injuries", "shift_date", "shift", "created_by"]


class DiaryEntrySerializer(RecordSerializer):
    class Meta:
        model = DiaryEntry
        fields = ["id", "guest", "occurred_at", "text", "is_relevant", "shift_date", "shift", "created_by"]


class EvacuationSerializer(RecordSerializer):
    class Meta:
        model = EvacuationRecord
        fields = ["id", "guest", "occurred_at", "outcome", "consistency", "amount", "notes", "shift_date", "shift",
                  "created_by"]


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ["id", "kind", "level", "title", "message", "link", "guest", "created_at", "read_at"]
