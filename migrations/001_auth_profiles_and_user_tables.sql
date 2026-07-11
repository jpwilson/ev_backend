-- ============================================
-- Phase 1: Auth tables for EV Lineup Platform
-- Run this in Supabase SQL Editor (https://supabase.com/dashboard)
-- Project: mesvpswjkqqogdoscyxx
-- ============================================

-- 1. Profiles table (auto-created on signup via trigger)
CREATE TABLE IF NOT EXISTS public.profiles (
  id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  display_name TEXT,
  avatar_url TEXT,
  role TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('user', 'admin')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 2. Auto-create profile on signup trigger
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
  INSERT INTO public.profiles (id, display_name, avatar_url)
  VALUES (
    NEW.id,
    COALESCE(NEW.raw_user_meta_data->>'full_name', NEW.raw_user_meta_data->>'name', NEW.email),
    COALESCE(NEW.raw_user_meta_data->>'avatar_url', NEW.raw_user_meta_data->>'picture')
  );
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- 2b. Backfill profiles for any users who signed up BEFORE this migration ran
-- (makes deploy order irrelevant: the auth UI can ship first, migration later)
INSERT INTO public.profiles (id, display_name, avatar_url)
SELECT u.id,
       COALESCE(u.raw_user_meta_data->>'full_name', u.raw_user_meta_data->>'name', u.email),
       COALESCE(u.raw_user_meta_data->>'avatar_url', u.raw_user_meta_data->>'picture')
FROM auth.users u
LEFT JOIN public.profiles p ON p.id = u.id
WHERE p.id IS NULL;

-- 3. User favorites
CREATE TABLE IF NOT EXISTS public.user_favorites (
  id BIGSERIAL PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  car_id INTEGER NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(user_id, car_id)
);

-- 4. User notes
CREATE TABLE IF NOT EXISTS public.user_notes (
  id BIGSERIAL PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  car_id INTEGER,
  make_model_slug TEXT,
  title TEXT,
  content TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 5. User cars (garage)
CREATE TABLE IF NOT EXISTS public.user_cars (
  id BIGSERIAL PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  car_id INTEGER,
  custom_make TEXT,
  custom_model TEXT,
  year INTEGER,
  purchase_date DATE,
  purchase_price NUMERIC(10,2),
  current_mileage INTEGER,
  ownership_status TEXT DEFAULT 'owned' CHECK (ownership_status IN ('owned', 'sold', 'leased')),
  nickname TEXT,
  battery_health NUMERIC(5,2),
  notes TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 6. RLS policies — defense-in-depth (FastAPI is primary access control)
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can read own profile" ON public.profiles FOR SELECT USING (auth.uid() = id);
CREATE POLICY "Users can update own profile" ON public.profiles FOR UPDATE USING (auth.uid() = id);
CREATE POLICY "Admins can read all profiles" ON public.profiles FOR SELECT USING ((auth.jwt() -> 'app_metadata' ->> 'role') = 'admin');

ALTER TABLE public.user_favorites ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can read own favorites" ON public.user_favorites FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users can insert own favorites" ON public.user_favorites FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Users can delete own favorites" ON public.user_favorites FOR DELETE USING (auth.uid() = user_id);

ALTER TABLE public.user_notes ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can read own notes" ON public.user_notes FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users can insert own notes" ON public.user_notes FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Users can update own notes" ON public.user_notes FOR UPDATE USING (auth.uid() = user_id);
CREATE POLICY "Users can delete own notes" ON public.user_notes FOR DELETE USING (auth.uid() = user_id);

ALTER TABLE public.user_cars ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can read own cars" ON public.user_cars FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users can insert own cars" ON public.user_cars FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Users can update own cars" ON public.user_cars FOR UPDATE USING (auth.uid() = user_id);
CREATE POLICY "Users can delete own cars" ON public.user_cars FOR DELETE USING (auth.uid() = user_id);

-- 7. Indexes
CREATE INDEX IF NOT EXISTS idx_user_favorites_user_id ON public.user_favorites(user_id);
CREATE INDEX IF NOT EXISTS idx_user_notes_user_id ON public.user_notes(user_id);
CREATE INDEX IF NOT EXISTS idx_user_cars_user_id ON public.user_cars(user_id);
