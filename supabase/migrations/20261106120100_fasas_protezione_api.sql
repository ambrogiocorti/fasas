-- FASAS Digitale: protezione delle tabelle dalle API automatiche di Supabase (Data API / PostgREST).
-- Generato da scripts/genera_migrazioni_supabase.py: non modificare a mano.
--
-- Il FASAS legge e scrive solo attraverso il proprio server (Django), collegato come proprietario delle tabelle.
-- Le API REST di Supabase non servono e non devono dare accesso ai dati:
--   1. Row Level Security attiva su ogni tabella del FASAS, senza alcuna policy: via API nessuna riga;
--   2. nessun privilegio ai ruoli delle API (anon, authenticated, service_role) su tabelle, sequenze e funzioni del
--      FASAS e, se il progetto contiene solo il FASAS, nemmeno sulle tabelle create in futuro.
-- Agisce solo sulle 100 tabelle del FASAS elencate qui sotto: tabelle di altre applicazioni non vengono toccate.
-- Il FASAS ripete gli stessi passi dopo ogni aggiornamento (fasas/core/supabase.py). È sicuro rieseguire il file.

DO $$
DECLARE
    fasas_tables text[] := ARRAY[
        'accounts_accesslog',
        'accounts_recoverycode',
        'accounts_twofactordevice',
        'accounts_user',
        'accounts_user_groups',
        'accounts_user_user_permissions',
        'accounts_userpermissionoverride',
        'appointments_appointment',
        'assessments_assessment',
        'assessments_scalesetting',
        'audit_auditcheckpoint',
        'audit_auditlog',
        'auth_group',
        'auth_group_permissions',
        'auth_permission',
        'authtoken_token',
        'backups_backuprecord',
        'backups_restoretest',
        'billing_attendancecorrection',
        'billing_attendancemonth',
        'billing_attendancemonthrow',
        'billing_billingsettings',
        'billing_feepayment',
        'billing_feestatement',
        'billing_guestfeeline',
        'billing_statementsequence',
        'clinical_clinicalevent',
        'clinical_parameterreading',
        'clinical_parametertype',
        'clinical_restraint',
        'clinical_therapy',
        'clinical_therapyadministration',
        'core_community',
        'core_errorevent',
        'core_jobrun',
        'core_keycanary',
        'core_systemconfig',
        'daily_checklistcheck',
        'daily_checklistitem',
        'daily_checklistitem_required_tags',
        'daily_checklisttemplate',
        'daily_dailyrecord',
        'daily_diaryentry',
        'daily_evacuationrecord',
        'daily_shiftassignment',
        'daily_shiftclosure',
        'django_admin_log',
        'django_content_type',
        'django_migrations',
        'django_session',
        'documents_document',
        'documents_documentversion',
        'feedback_feedback',
        'guests_admissionevent',
        'guests_allergy',
        'guests_clinicaltag',
        'guests_diagnosis',
        'guests_guest',
        'guests_guest_tags',
        'guests_guestcontact',
        'imports_importbatch',
        'notifications_notification',
        'notifications_notificationsetting',
        'notifications_pushsubscription',
        'offline_offlinerecord',
        'pai_pai',
        'pai_paigoal',
        'pharmacy_drug',
        'pharmacy_druginteraction',
        'pharmacy_officiallistimport',
        'pharmacy_officialpackage',
        'pharmacy_stocklot',
        'pharmacy_stockmovement',
        'protocols_protocol',
        'protocols_protocol_guests',
        'protocols_protocol_tags',
        'protocols_protocolactionlog',
        'protocols_protocolactivation',
        'reports_generatedreport',
        'reports_reportschedule',
        'reports_reporttemplate',
        'signatures_cieaccess',
        'signatures_cieenrollment',
        'signatures_devicepairing',
        'signatures_feaacceptance',
        'signatures_signature',
        'signatures_signaturerequest',
        'signatures_signerapprelease',
        'signatures_signerdevice',
        'signatures_signingcredential',
        'staffing_leaverequest',
        'staffing_rotaentry',
        'staffing_rotamonth',
        'staffing_rotasettings',
        'staffing_shiftchange',
        'staffing_staffprofile',
        'wounds_dressing',
        'wounds_dressingplan',
        'wounds_wound',
        'wounds_woundcheck'
    ];
    api_roles text[];
    api_role text;
    item text;
    dedicated boolean;
BEGIN
    SELECT array_agg(rolname) INTO api_roles FROM pg_catalog.pg_roles
     WHERE rolname IN ('anon', 'authenticated', 'service_role');
    SELECT NOT EXISTS (SELECT 1 FROM pg_catalog.pg_tables WHERE schemaname = 'public'
                        AND tablename <> ALL (fasas_tables)) INTO dedicated;
    FOREACH item IN ARRAY fasas_tables LOOP
        IF to_regclass(format('public.%I', item)) IS NOT NULL THEN
            EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', item);
            FOREACH api_role IN ARRAY coalesce(api_roles, ARRAY[]::text[]) LOOP
                EXECUTE format('REVOKE ALL ON TABLE public.%I FROM %I', item, api_role);
            END LOOP;
        END IF;
    END LOOP;
    FOREACH api_role IN ARRAY coalesce(api_roles, ARRAY[]::text[]) LOOP
        -- sequenze delle chiavi primarie e funzioni del FASAS
        FOR item IN SELECT DISTINCT format('public.%I', seq.relname) FROM pg_catalog.pg_class seq
                    JOIN pg_catalog.pg_depend dep ON dep.objid = seq.oid
                    JOIN pg_catalog.pg_class tab ON tab.oid = dep.refobjid
                    JOIN pg_catalog.pg_namespace ns ON ns.oid = seq.relnamespace
                    WHERE seq.relkind = 'S' AND dep.deptype IN ('a', 'i') AND ns.nspname = 'public'
                      AND tab.relname = ANY (fasas_tables) LOOP
            EXECUTE format('REVOKE ALL ON SEQUENCE %s FROM %I', item, api_role);
        END LOOP;
        FOR item IN SELECT p.oid::regprocedure::text FROM pg_catalog.pg_proc p
                    JOIN pg_catalog.pg_namespace ns ON ns.oid = p.pronamespace
                    WHERE ns.nspname = 'public' AND p.proname LIKE 'fasas\_%' LOOP
            EXECUTE format('REVOKE ALL ON FUNCTION %s FROM %I', item, api_role);
        END LOOP;
        IF dedicated THEN
            EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM %I', api_role);
            EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM %I', api_role);
            EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON FUNCTIONS FROM %I', api_role);
        END IF;
    END LOOP;
END
$$;
