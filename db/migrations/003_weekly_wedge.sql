-- FIELDMIND week-of-game wedge: program tenancy, trusted tags, weekly decisions.
-- Applied after 002_college_play_evidence.sql. Do not edit after deployment.

CREATE EXTENSION IF NOT EXISTS citext;

ALTER TABLE plays ADD COLUMN IF NOT EXISTS source_play_class TEXT;

-- Preserve source-only pass/run classification without treating it as a football concept.
UPDATE plays
SET source_play_class = play_family,
    play_family = 'UNKNOWN',
    personnel_offense = 'UNKNOWN',
    formation = 'UNKNOWN',
    motion = NULL,
    concept = NULL,
    coverage = NULL
WHERE external_source IN ('cfbd','nflverse');

-- Hard boundary: public PBP is source evidence only. Even if an adapter later adds a
-- heuristic, these film-only fields stay UNKNOWN/null until a trusted program tag exists.
CREATE OR REPLACE FUNCTION fieldmind_guard_source_pbp()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.external_source IN ('cfbd','nflverse') THEN
        IF NEW.play_family IN ('pass','run') THEN
            NEW.source_play_class := NEW.play_family;
        END IF;
        NEW.play_family := 'UNKNOWN';
        NEW.personnel_offense := 'UNKNOWN';
        NEW.formation := 'UNKNOWN';
        NEW.motion := NULL;
        NEW.concept := NULL;
        NEW.coverage := NULL;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_fieldmind_guard_source_pbp ON plays;
CREATE TRIGGER trg_fieldmind_guard_source_pbp
BEFORE INSERT OR UPDATE ON plays
FOR EACH ROW EXECUTE FUNCTION fieldmind_guard_source_pbp();

CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email CITEXT NOT NULL UNIQUE,
    display_name TEXT,
    active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS program_memberships (
    program_id UUID NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('owner','coach','ga','viewer')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (program_id,user_id)
);

CREATE TABLE IF NOT EXISTS auth_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    last_used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS play_tag_votes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    program_id UUID NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    play_id UUID NOT NULL REFERENCES plays(id) ON DELETE CASCADE,
    field TEXT NOT NULL CHECK (field IN ('play_family','formation','motion','coverage_family','personnel')),
    value TEXT NOT NULL,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (program_id,play_id,field,user_id)
);

CREATE TABLE IF NOT EXISTS program_play_tags (
    program_id UUID NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    play_id UUID NOT NULL REFERENCES plays(id) ON DELETE CASCADE,
    play_family TEXT NOT NULL DEFAULT 'UNKNOWN',
    formation TEXT NOT NULL DEFAULT 'UNKNOWN',
    motion TEXT NOT NULL DEFAULT 'UNKNOWN',
    coverage_family TEXT NOT NULL DEFAULT 'UNKNOWN',
    personnel TEXT NOT NULL DEFAULT 'UNKNOWN',
    agreement JSONB NOT NULL DEFAULT '{}'::jsonb,
    resolved_by UUID REFERENCES users(id),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (program_id,play_id)
);

CREATE TABLE IF NOT EXISTS week_plans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    program_id UUID NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    team_id UUID REFERENCES teams(id),
    team_name TEXT NOT NULL,
    season INTEGER NOT NULL CHECK (season BETWEEN 2000 AND 2100),
    week INTEGER NOT NULL CHECK (week BETWEEN 0 AND 25),
    opponent_name TEXT NOT NULL,
    side TEXT NOT NULL CHECK (side IN ('offense','defense')),
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','frozen','complete')),
    created_by UUID NOT NULL REFERENCES users(id),
    frozen_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (program_id,team_name,season,week,side)
);

ALTER TABLE call_rules ADD COLUMN IF NOT EXISTS program_id UUID REFERENCES programs(id) ON DELETE CASCADE;
ALTER TABLE call_rules ADD COLUMN IF NOT EXISTS week_plan_id UUID REFERENCES week_plans(id) ON DELETE CASCADE;
ALTER TABLE call_rules ADD COLUMN IF NOT EXISTS confidence TEXT;
ALTER TABLE call_rules ADD COLUMN IF NOT EXISTS evidence_play_ids UUID[] NOT NULL DEFAULT ARRAY[]::UUID[];
ALTER TABLE call_rules ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'candidate';
ALTER TABLE call_rules ADD COLUMN IF NOT EXISTS created_by UUID REFERENCES users(id);
ALTER TABLE call_rules ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname='call_rules_confidence_check'
    ) THEN
        ALTER TABLE call_rules ADD CONSTRAINT call_rules_confidence_check
            CHECK (confidence IS NULL OR confidence IN ('insufficient','directional','usable'));
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname='call_rules_status_check'
    ) THEN
        ALTER TABLE call_rules ADD CONSTRAINT call_rules_status_check
            CHECK (status IN ('candidate','approved','rejected'));
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS player_look_evidence (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    program_id UUID NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    week_plan_id UUID NOT NULL REFERENCES week_plans(id) ON DELETE CASCADE,
    player_id UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    source_type TEXT NOT NULL CHECK (source_type IN ('game','practice','meeting')),
    event_date DATE NOT NULL,
    play_id UUID REFERENCES plays(id) ON DELETE SET NULL,
    formation TEXT NOT NULL DEFAULT 'UNKNOWN',
    motion TEXT NOT NULL DEFAULT 'UNKNOWN',
    coverage_family TEXT NOT NULL DEFAULT 'UNKNOWN',
    personnel TEXT NOT NULL DEFAULT 'UNKNOWN',
    call_name TEXT,
    processed_correctly BOOLEAN NOT NULL,
    notes TEXT,
    created_by UUID NOT NULL REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS changed_call_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    week_plan_id UUID NOT NULL REFERENCES week_plans(id) ON DELETE CASCADE,
    call_rule_id UUID REFERENCES call_rules(id) ON DELETE SET NULL,
    changed_call BOOLEAN NOT NULL,
    change_type TEXT NOT NULL CHECK (change_type IN ('added','removed','modified','confirmed')),
    notes TEXT,
    logged_by UUID NOT NULL REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS play_links (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    program_id UUID NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    play_id UUID NOT NULL REFERENCES plays(id) ON DELETE CASCADE,
    provider TEXT NOT NULL CHECK (provider IN ('hudl','other')),
    url TEXT NOT NULL,
    created_by UUID NOT NULL REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_auth_tokens_hash ON auth_tokens(token_hash);
CREATE INDEX IF NOT EXISTS idx_memberships_user ON program_memberships(user_id,program_id);
CREATE INDEX IF NOT EXISTS idx_tag_votes_program_play ON play_tag_votes(program_id,play_id,field);
CREATE INDEX IF NOT EXISTS idx_program_play_tags_filter
    ON program_play_tags(program_id,play_family,formation,motion,coverage_family,personnel);
CREATE INDEX IF NOT EXISTS idx_week_plans_program_week
    ON week_plans(program_id,season,week,status);
CREATE INDEX IF NOT EXISTS idx_call_rules_program_week
    ON call_rules(program_id,week_plan_id,status,priority DESC);
CREATE INDEX IF NOT EXISTS idx_player_look_week
    ON player_look_evidence(program_id,week_plan_id,player_id);
CREATE INDEX IF NOT EXISTS idx_changed_call_week
    ON changed_call_logs(week_plan_id,created_at DESC);
CREATE INDEX IF NOT EXISTS idx_play_links_program_play
    ON play_links(program_id,play_id);
