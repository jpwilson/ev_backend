-- ============================================
-- 005: Row Level Security on the legacy tables + trigger function hardening
-- For the Supabase SQL editor. NOT applied automatically (not an Alembic revision).
-- Safe to run more than once.
--
-- The API (FastAPI over SQLAlchemy) connects as the table owner, which bypasses RLS,
-- so the site keeps working. The browser uses supabase-js only for Auth and Storage.
-- Defense in depth, matching the catalog tables added in 002/003/004.
-- Before running: confirm no other app reads these tables through
-- https://<project>.supabase.co/rest/v1/ (Supabase dashboard > Logs > API).
-- ============================================

BEGIN;

DO $$
DECLARE
  t text;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'cars',
    'makes',
    'people',
    'newsletter_subscribers',
    'make_person_association',
    'make_founders_association',
    'make_ceo_association',
    'alembic_version'
  ] LOOP
    IF to_regclass('public.' || t) IS NOT NULL THEN
      EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t);
    END IF;
  END LOOP;
END $$;

-- SECURITY DEFINER functions should pin search_path (Supabase linter 0011).
-- The body already schema-qualifies public.profiles, so an empty path is safe.
ALTER FUNCTION public.handle_new_user() SET search_path = '';

-- Users may edit their own display name and avatar through the Data API, not role.
REVOKE UPDATE ON public.profiles FROM anon, authenticated;
GRANT UPDATE (display_name, avatar_url, updated_at) ON public.profiles TO authenticated;

COMMIT;

-- Check afterwards: every public table should show rowsecurity = true.
-- SELECT tablename, rowsecurity FROM pg_tables WHERE schemaname = 'public' ORDER BY 1;
