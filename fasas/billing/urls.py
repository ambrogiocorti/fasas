from django.urls import path

from . import views

app_name = "billing"

urlpatterns = [
    path("presenze/", views.attendance_view, name="attendance"),
    path("presenze/ospite/<int:guest_pk>/correggi/", views.correction, name="correction"),
    path("presenze/chiudi/", views.close_month_view, name="close_month"),
    path("presenze/riapri/", views.reopen_month_view, name="reopen_month"),
    path("presenze/excel/", views.attendance_excel, name="attendance_excel"),
    path("rette/", views.fees, name="fees"),
    path("rette/ospite/<int:guest_pk>/nuova/", views.fee_edit, name="fee_create"),
    path("rette/<int:pk>/", views.fee_edit, name="fee_update"),
    path("prospetti/", views.statements, name="statements"),
    path("prospetti/genera/", views.generate, name="generate"),
    path("prospetti/emetti/", views.issue_all, name="issue_all"),
    path("prospetti/excel/", views.statements_excel, name="statements_excel"),
    path("prospetti/<int:pk>/", views.statement_detail, name="statement"),
    path("prospetti/<int:pk>/emetti/", views.statement_issue, name="statement_issue"),
    path("prospetti/<int:pk>/annulla/", views.statement_cancel, name="statement_cancel"),
    path("prospetti/<int:pk>/pdf/", views.statement_pdf_view, name="statement_pdf"),
    path("impostazioni/", views.settings_view, name="settings"),
]
