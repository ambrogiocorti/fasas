# Architettura

## Principi

- **Monolite modulare Django**: un'app per ogni area funzionale, con confini netti (modelli, servizi, viste, URL).
  Le regole di dominio stanno nei moduli `services.py` / `engine.py`, non nelle viste: web, API e job usano la stessa logica.
- **Mai cancellare dati clinici**: le registrazioni si *annullano* con motivazione (`voided_at`, `void_reason`),
  restano nel database, nello storico e nei report di audit. Il manager predefinito le esclude, `all_objects` le include.
- **Ogni registrazione appartiene a un turno**: `ShiftRecordModel` calcola giornata e turno dall'ora dell'evento
  (la notte appartiene al giorno in cui inizia). Su questo si basano checklist, chiusura turni e blocco modifiche.
- **Audit by design**: ogni modello sensibile è registrato con `fasas.audit.services.register()`; i segnali salvano
  automaticamente utente, IP, motivazione, valore precedente e nuovo. Consultazioni, download, esportazioni e firme
  sono tracciati esplicitamente con `log_event()`.
- **Pronto per più comunità**: il modello `Community` esiste già ed è collegato a ospiti, utenti e configurazione.

## Flusso di una richiesta

```
Browser / app ──► SecurityMiddleware ──► AllowedNetworks (reti della comunità) ──► Sessione/Autenticazione
     ──► Community (configurazione) ──► Timeout inattività ──► AuditContext (utente, IP) ──► LoginRequired
     ──► Vista (permessi + regole di blocco) ──► Servizi di dominio ──► ORM ──► PostgreSQL (Supabase)
                                                     │
                                                     └─► segnali: audit log, protocolli, notifiche
```

Ogni richiesta è una transazione (`ATOMIC_REQUESTS`): una modifica e la sua voce di audit si salvano insieme o per niente.

## Job pianificati

Definiti in `fasas/core/jobs.py`, eseguiti da Celery beat (`config/celery.py`) oppure da cron con `manage.py fasas_jobs <nome>`.

| Job | Frequenza | Funzione |
|---|---|---|
| `close_shifts` | ogni 15 min | chiude i turni terminati da oltre la tolleranza configurata |
| `protocols` | ogni 30 min | regole basate sul tempo (giorni senza evacuazione) |
| `appointments` | ogni ora | promemoria visita domani / oggi |
| `stock` | 2 volte al giorno | farmaci sotto soglia, in scadenza, scaduti |
| `documents` | giornaliero | documenti in scadenza |
| `pai_reviews` | giornaliero | revisioni PAI e verifiche degli obiettivi |
| `reports` | giornaliero | report programmati del periodo concluso |
| `report_retention` | giornaliero | elimina i report oltre la conservazione (1–5 anni) |
| `backup` | giornaliero 02:30 | backup cifrato, verifica, pulizia secondo conservazione |
| `audit_verify` | giornaliero | verifica la catena di hash dell'audit log |

## Corrispondenza con la specifica

| # | Requisito | Implementazione |
|---|---|---|
| 1 | Architettura web, ruoli, archivio, protocolli, audit, export, firma, cifratura, notifiche, magazzino, backup, log accessi | intero progetto; vedi righe seguenti |
| 2 | Ruoli Amministratore, Coordinatore, Operatore, Medico | `accounts.models.Role`, permessi predefiniti in `accounts/roles.py` (gruppi Django) |
| 3 | Gestione ospiti, dati anagrafici e sanitari, tag clinici, documenti | `guests` (`Guest`, `GuestContact`, `Diagnosis`, `Allergy`, `ClinicalTag` con avviso ed escalation), `documents` |
| 4 | Terapie, somministrazioni, SOS con validazione, controllo duplicati/interazioni, parametri e grafici, eventi, contenzioni | `clinical` (`Therapy`, `TherapyAdministration`, `ParameterType`, `ParameterReading`, `ClinicalEvent`, `Restraint`); `clinical/services.py` `check_therapy_conflicts`; grafici SVG in `static/js/fasas.js` |
| 5 | Registro giornaliero, modalità evacuazione A/B, giorni dall'ultima evacuazione | `daily` (`DailyRecord`, `EvacuationRecord`), `SystemConfig.evacuation_mode`, `daily/services.py` `days_since_last_evacuation` |
| 6 | Diario assistenziale | `daily.DiaryEntry` |
| 7 | Checklist per turno ✔/⚠ | `daily` (`ChecklistTemplate`, `ChecklistItem` con verifiche automatiche, `ChecklistCheck`), `checklist_status()` |
| 8 | Protocolli automatici (evacuazione 3 giorni → farmaco + lavanda; febbre, glicemia, crisi, agitazione, SOS) | `protocols` (`Protocol`, `ProtocolActivation`, `ProtocolActionLog`), `protocols/engine.py` |
| 9 | Magazzino: lotto, quantità, scadenza, soglia, scarico automatico, avvisi | `pharmacy` (`Drug`, `StockLot`, `StockMovement`), `unload_for_administration` (FEFO), `stock_alerts` |
| 10 | Appuntamenti con notifiche domani/oggi | `appointments`, `send_reminders` |
| 11 | Turni mattina/pomeriggio/notte, eventi collegati al turno | `core/shifts.py`, `ShiftRecordModel`, `daily.ShiftAssignment` |
| 12 | Dashboard clinica ospite | `guests/dashboard.py` `clinical_dashboard`, `templates/guests/detail.html` |
| 13 | Storico completo | `guests/dashboard.py` `timeline` |
| 14 | PAI per aree, revisioni, storico versioni | `pai` (`PAI`, `PAIGoal`), `create_revision`, `activate`, PDF archiviato |
| 15 | Sistema documentale | `documents` (`Document`, `DocumentVersion`), `core/encryption.py` |
| 16 | Audit log obbligatorio | `audit` (`AuditLog` append-only, catena SHA-256, trigger PostgreSQL) |
| 17 | Blocco modifiche dati sanitari (24 h / motivazione / solo coordinatore) | `SystemConfig.edit_lock_policy`, `core/locking.py`, `LockedUpdateMixin` |
| 18 | Blocco giornata a fine turno | `daily.ShiftClosure`, `close_shift`, `auto_close_shifts` |
| 19 | Backup automatici cifrati, ripristino, verifica integrità | `backups` (AES-256-GCM a blocchi, manifest con SHA-256, `pg_dump`) |
| 20 | Log accessi (utente, IP, ora, dispositivo) | `accounts.AccessLog` append-only, blocco dopo tentativi falliti |
| 21 | Report PDF/Excel programmati, conservazione 1–5 anni | `reports` (`ReportSchedule`, `GeneratedReport`), ReportLab e openpyxl |
| 22 | Esportazione cartella completa in PDF | `reports/guest_export.py` (allegati PDF e immagini accodati) |
| 23 | Ricerca avanzata con filtri | `search` |
| 24 | Modalità emergenza | pulsante «Evento critico» nella barra superiore, `clinical.views.emergency` |
| 25 | Archiviazione ospiti dimessi | `guests/services.py` `discharge_and_archive`, stato `archived`, `retention_until` |
| 26 | Permessi granulari | `accounts.UserPermissionOverride` + `FasasPermissionBackend` (concede o nega rispetto al ruolo) |
| 27 | Modalità scura | `static/css/fasas.css` (`[data-theme=dark]`), automatica nel turno di notte |
| 28 | Stack Python/Django/DRF/PostgreSQL Supabase, storage cifrato o S3 | `requirements.txt`, `config/settings.py` (`DATABASE_URL`, `FASAS_S3_BUCKET`) |
| 29 | 10–100 ospiti, accessi simultanei, archiviazione a lungo termine | PostgreSQL, indici su turno/data, file cifrati su filesystem o S3 |
| 30 | Architettura futura: più comunità, integrazioni regionali, app mobile | modello `Community`, API REST `/api/v1/` con token, servizi di dominio riusabili; app installabile (PWA) |

### Moduli aggiunti oltre la specifica

| Modulo | Implementazione |
|---|---|
| Importazione dal cartaceo | `imports` (`ImportBatch`, `spec.py` colonne del modello, `services.run_workbook_import`, `documents.py` scansioni) |
| Firma remota qualificata | `signatures/csc.py` (API CSC v1 con pyHanko), livelli PAdES in `signatures/providers.py` |
| Notifiche push | `notifications/push.py` (Web Push VAPID), `PushSubscription`, service worker `templates/pwa/sw.js` |
| Lavoro senza rete | `offline` (`pack.py` pacchetto del turno, `sync.py` sincronizzazione idempotente, `OfflineRecord`, `emergency.py`), `static/js/offline.js` (cifratura AES-GCM nel browser) |
| Presenze e rette | `billing` (`AttendanceMonth`/`AttendanceMonthRow`, `GuestFeeLine`, `FeeStatement`, `FeePayment`, `services.guest_days`) |
| Turni del personale | `staffing` (`RotaEntry`, `RotaMonth`, `LeaveRequest`, `ShiftChange`, `services.month_grid` con copertura e riposi) |

## Schema del database

59 tabelle in totale (comprese quelle di Django per sessioni, permessi e token API).
Le tabelle dei dati clinici hanno inoltre: `created_at`, `created_by`, `updated_at`, `updated_by`
e, per le registrazioni di turno, `shift_date`, `shift`, `voided_at`, `voided_by`, `void_reason`.

### Sistema (`core`)

| Tabella | Contenuto | Campi principali |
|---|---|---|
| `core_community` | Comunità | name, code, address, phone, email, asl_code, active |
| `core_systemconfig` | Configurazione di sistema | community, evacuation_mode, edit_lock_policy, edit_window_hours, morning_start, afternoon_start, night_start, auto_close_shifts, auto_close_grace_minutes |

### Utenti e accessi (`accounts`)

| Tabella | Contenuto | Campi principali |
|---|---|---|
| `accounts_user` | Utenti | username, first_name, last_name, email, role, community, fiscal_code, qualification, professional_register, theme |
| `accounts_userpermissionoverride` | Permessi personalizzati | user, permission, allow |
| `accounts_accesslog` | Log accessi | timestamp, user, username, event, ip_address, user_agent, device |

### Audit log (`audit`)

| Tabella | Contenuto | Campi principali |
|---|---|---|
| `audit_auditlog` | Audit log | timestamp, user, username, action, content_type, object_id, object_repr, guest_id, changes |

### Ospiti (`guests`)

| Tabella | Contenuto | Campi principali |
|---|---|---|
| `guests_clinicaltag` | Tag clinici | name, color, description, alert_message, escalate_event_types, order |
| `guests_guest` | Ospiti | community, first_name, last_name, sex, birth_date, birth_place, fiscal_code, health_card_number, residence_address |
| `guests_guestcontact` | Contatti | guest, kind, name, relationship, phone, email, address, legal_reference, is_emergency_contact |
| `guests_diagnosis` | Diagnosi e patologie | guest, kind, description, icd_code, diagnosed_on, is_primary, active, notes |
| `guests_allergy` | Allergie e intolleranze | guest, kind, category, substance, reaction, severity, notes |
| `guests_admissionevent` | Movimenti ospite | guest, kind, date, notes |

### Documenti (`documents`)

| Tabella | Contenuto | Campi principali |
|---|---|---|
| `documents_document` | Documenti | guest, category, title, description, document_date, expires_on |
| `documents_documentversion` | Versioni documento | document, number, storage_name, original_name, content_type, size, sha256, note, uploaded_at |

### Firma digitale (`signatures`)

| Tabella | Contenuto | Campi principali |
|---|---|---|
| `signatures_signingcredential` | Credenziali di firma | user, kind, storage_name, remote_user_id, certificate_subject, certificate_issuer, certificate_serial, valid_from, valid_to |
| `signatures_signature` | Firme digitali | source_version, signed_version, signer, signed_at, signature_format, provider, certificate_subject, certificate_issuer, certificate_serial |

### Farmaci e magazzino (`pharmacy`)

| Tabella | Contenuto | Campi principali |
|---|---|---|
| `pharmacy_drug` | Farmaci | name, active_ingredient, atc_code, aic_code, form, strength, stock_unit, min_stock, is_controlled |
| `pharmacy_druginteraction` | Interazioni farmacologiche | ingredient_a, ingredient_b, severity, description, source |
| `pharmacy_stocklot` | Magazzino farmaci | drug, guest, lot_number, expiry_date, quantity, received_on, supplier, notes |
| `pharmacy_stockmovement` | Movimenti di magazzino | lot, kind, quantity, balance_after, administration, notes |

### Cartella sanitaria (`clinical`)

| Tabella | Contenuto | Campi principali |
|---|---|---|
| `clinical_therapy` | Terapie | guest, drug, dose, dose_unit, stock_units_per_dose, route, schedule_times, every_n_days, start_date |
| `clinical_therapyadministration` | Somministrazioni | guest, occurred_at, therapy, scheduled_date, scheduled_time, status, dose_given, notes, is_sos |
| `clinical_parametertype` | Tipi di parametro | code, name, unit, kind, min_normal, max_normal, min_normal_2, max_normal_2, decimals |
| `clinical_parameterreading` | Parametri sanitari | guest, occurred_at, parameter_type, value, value_2, notes |
| `clinical_clinicalevent` | Eventi sanitari | guest, occurred_at, event_type, severity, duration_minutes, location, description, actions_taken, injuries |
| `clinical_restraint` | Contenzioni | guest, occurred_at, restraint_type, reason, alternatives_tried, ended_at, authorized_by, authorizing_doctor_name, authorization_date |

### Registro giornaliero e turni (`daily`)

| Tabella | Contenuto | Campi principali |
|---|---|---|
| `daily_shiftassignment` | Registro turni | date, user, is_shift_lead, checked_in_at, checked_out_at, notes |
| `daily_shiftclosure` | Chiusure turno | date, closed_at, closed_by, automatic, summary, handover_notes, reopened_at, reopened_by, reopen_reason |
| `daily_dailyrecord` | Registro giornaliero | guest, occurred_at, category, meal, intake, description |
| `daily_evacuationrecord` | Evacuazioni | guest, occurred_at, outcome, consistency, amount, assisted, notes |
| `daily_diaryentry` | Diario assistenziale | guest, occurred_at, text, is_relevant |
| `daily_checklisttemplate` | Checklist di turno | name, active |
| `daily_checklistitem` | Voci di checklist | template, label, check_type, meal, parameter_type, per_guest, order |
| `daily_checklistcheck` | Spunte checklist | date, item, guest, not_applicable, notes, done_by, done_at |

### Protocolli automatici (`protocols`)

| Tabella | Contenuto | Campi principali |
|---|---|---|
| `protocols_protocol` | Protocolli | name, kind, description, params, actions, severity, applies_to_all, notify_roles, validated_by |
| `protocols_protocolactivation` | Attivazioni protocolli | protocol, guest, triggered_at, trigger_summary, trigger_data, status, resolved_at, resolved_by, resolution_notes |
| `protocols_protocolactionlog` | Azioni eseguite | activation, action_label, done_by, done_at, notes |

### Appuntamenti sanitari (`appointments`)

| Tabella | Contenuto | Campi principali |
|---|---|---|
| `appointments_appointment` | Appuntamenti sanitari | guest, kind, title, scheduled_at, location, doctor, companion, companion_name, transport |

### Piano Assistenziale Individuale (`pai`)

| Tabella | Contenuto | Campi principali |
|---|---|---|
| `pai_pai` | Pai | guest, version, status, valid_from, review_due, summary, participants, previous, approved_by |
| `pai_paigoal` | Obiettivi pai | pai, area, objective, intervention, responsible, responsible_name, verification_date, indicators, outcome |

### Notifiche (`notifications`)

| Tabella | Contenuto | Campi principali |
|---|---|---|
| `notifications_notificationsetting` | Impostazioni notifiche | kind, enabled, roles, send_email |
| `notifications_notification` | Notifiche | recipient, kind, level, title, message, link, guest, dedup_key, read_at |

### Report ed esportazioni (`reports`)

| Tabella | Contenuto | Campi principali |
|---|---|---|
| `reports_reportschedule` | Report programmati | name, report_type, format, frequency, guest, retention_years, active, last_run_at |
| `reports_generatedreport` | Report generati | schedule, report_type, format, title, period_start, period_end, guest, storage_name, filename |

### Backup (`backups`)

| Tabella | Contenuto | Campi principali |
|---|---|---|
| `backups_backuprecord` | Backup | finished_at, kind, status, filename, size, sha256, db_format, includes_media, verified_at |
## API REST

Autenticazione con sessione o token (`POST /api/v1/token/` con `username` e `password`; stesso blocco
anti-forzatura del login). Stessi permessi e regole di blocco dell'interfaccia web.

| Endpoint | Metodi |
|---|---|
| `/api/v1/ospiti/` | GET |
| `/api/v1/terapie/?guest=ID` | GET |
| `/api/v1/turno-corrente/` | GET – dosi programmate del turno con stato |
| `/api/v1/somministrazioni/` | GET, POST (scarico magazzino e regole SOS come da web) |
| `/api/v1/parametri/`, `/eventi/`, `/diario/`, `/evacuazioni/` | GET, POST |
| `/api/v1/notifiche/`, `/api/v1/notifiche/{id}/read/` | GET, POST |
