"""API REST: base per la futura app mobile degli operatori. Stesse regole di permessi e blocco del web."""
from django.utils import timezone
from rest_framework import mixins, serializers, viewsets
from rest_framework.authtoken.models import Token
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from fasas.accounts import twofactor
from fasas.accounts.models import AccessLog
from fasas.accounts.services import is_locked_out, record_access
from fasas.audit.context import set_current_user
from fasas.clinical.models import ClinicalEvent, ParameterReading, Therapy, TherapyAdministration
from fasas.clinical.services import register_administration, scheduled_doses
from fasas.core.middleware import client_ip
from fasas.core.shifts import Shift, resolve_shift
from fasas.daily.models import DiaryEntry, EvacuationRecord
from fasas.guests.services import guests_in_care
from fasas.notifications.models import Notification

from . import serializers as s


class AuditedMixin:
    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        set_current_user(request.user)


class GuestViewSet(AuditedMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = s.GuestSerializer

    def get_queryset(self):
        return guests_in_care().prefetch_related("allergies")


class TherapyViewSet(AuditedMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = s.TherapySerializer
    queryset = Therapy.objects.filter(status=Therapy.Status.ACTIVE).select_related("drug")

    def get_queryset(self):
        qs = super().get_queryset()
        guest = self.request.query_params.get("guest")
        return qs.filter(guest_id=guest) if guest else qs


class RecordViewSet(AuditedMixin, mixins.CreateModelMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                    viewsets.GenericViewSet):
    model = None

    def get_queryset(self):
        qs = self.model.objects.select_related("guest", "created_by").order_by("-occurred_at")
        params = self.request.query_params
        if params.get("guest"):
            qs = qs.filter(guest_id=params["guest"])
        if params.get("date"):
            qs = qs.filter(shift_date=params["date"])
        return qs


class AdministrationViewSet(RecordViewSet):
    model = TherapyAdministration
    serializer_class = s.AdministrationSerializer

    def perform_create(self, serializer):
        data = serializer.validated_data
        therapy = data["therapy"]
        if data.get("scheduled_time") and TherapyAdministration.objects.filter(
            therapy=therapy, scheduled_date=data.get("scheduled_date"), scheduled_time=data["scheduled_time"]
        ).exists():
            raise serializers.ValidationError("Dose già registrata.")
        serializer.instance = register_administration(
            therapy, self.request.user, status=data.get("status", TherapyAdministration.Status.GIVEN),
            scheduled_date=data.get("scheduled_date"), scheduled_time=data.get("scheduled_time"),
            occurred_at=data.get("occurred_at"), notes=data.get("notes", ""), dose_given=data.get("dose_given", ""),
            sos_reason=data.get("sos_reason", ""),
        )


class ParameterViewSet(RecordViewSet):
    model = ParameterReading
    serializer_class = s.ParameterReadingSerializer


class EventViewSet(RecordViewSet):
    model = ClinicalEvent
    serializer_class = s.ClinicalEventSerializer


class DiaryViewSet(RecordViewSet):
    model = DiaryEntry
    serializer_class = s.DiaryEntrySerializer


class EvacuationViewSet(RecordViewSet):
    model = EvacuationRecord
    serializer_class = s.EvacuationSerializer


class NotificationViewSet(AuditedMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = s.NotificationSerializer

    def get_queryset(self):
        return Notification.objects.filter(recipient=self.request.user)

    @action(detail=True, methods=["post"])
    def read(self, request, pk=None):
        notification = self.get_object()
        notification.read_at = notification.read_at or timezone.now()
        notification.save(update_fields=["read_at"])
        return Response({"read_at": notification.read_at})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def current_shift(request):
    """Turno corrente con le dosi programmate: la schermata principale dell'app operatori."""
    if not request.user.has_perm("clinical.view_therapyadministration"):
        return Response({"detail": "Permesso negato."}, status=403)
    day, shift = resolve_shift()
    doses = scheduled_doses(day, shift, guests_in_care())
    return Response({
        "date": day, "shift": shift, "shift_label": Shift(shift).label,
        "doses": [{
            "therapy": d.therapy.pk, "guest": d.guest.pk, "guest_name": str(d.guest), "drug": str(d.therapy.drug),
            "dose": d.therapy.dose_display, "day": d.day, "time": d.time.strftime("%H:%M"), "done": d.done,
            "status": d.administration.status if d.administration else None,
        } for d in doses],
    })


class TokenView(ObtainAuthToken):
    """Token per l'app mobile, con lo stesso blocco anti-forzatura del login web."""

    def post(self, request, *args, **kwargs):
        username = request.data.get("username", "")
        if username and is_locked_out(username, client_ip(request)):
            raise PermissionDenied("Troppi tentativi falliti. Riprova più tardi.")
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        need = twofactor.requirement(user, request)
        if need in ("setup", "refused"):
            raise PermissionDenied("Attiva prima la verifica in due passaggi dal sito del FASAS.")
        if need == "verify" and not twofactor.verify(user, request.data.get("otp", "")):
            record_access(request, AccessLog.Event.OTP_FAILED, user.get_username(), user)
            raise PermissionDenied("Codice di verifica («otp») mancante, errato o già usato.")
        token, _ = Token.objects.get_or_create(user=user)
        return Response({"token": token.key})
