CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS programs (
    id UUID PRIMARY KEY,
    name TEXT NOT NULL,
    level TEXT NOT NULL CHECK (level IN ('high_school','college','nfl','other')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS teams (
    id UUID PRIMARY KEY,
    program_id UUID REFERENCES programs(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    season INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (program_id, name, season)
);

CREATE TABLE IF NOT EXISTS players (
    id UUID PRIMARY KEY,
    team_id UUID NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    position TEXT NOT NULL,
    class_year TEXT,
    jersey INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS games (
    id UUID PRIMARY KEY,
    season INTEGER NOT NULL,
    week INTEGER,
    game_date DATE,
    home_team_id UUID REFERENCES teams(id),
    away_team_id UUID REFERENCES teams(id),
    venue TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS plays (
    id UUID PRIMARY KEY,
    game_id UUID NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    play_sequence INTEGER NOT NULL,
    quarter INTEGER NOT NULL CHECK (quarter BETWEEN 1 AND 5),
    clock TEXT NOT NULL,
    down INTEGER NOT NULL CHECK (down BETWEEN 1 AND 4),
    distance INTEGER NOT NULL CHECK (distance >= 0),
    yard_line INTEGER NOT NULL CHECK (yard_line BETWEEN 0 AND 100),
    distance_bucket TEXT NOT NULL CHECK (distance_bucket IN ('short','medium','long')),
    field_zone TEXT NOT NULL CHECK (field_zone IN ('backed_up','open_field','plus','red_zone')),
    score_diff INTEGER NOT NULL DEFAULT 0,
    offense_team_id UUID REFERENCES teams(id),
    defense_team_id UUID REFERENCES teams(id),
    offense_team_name TEXT NOT NULL,
    defense_team_name TEXT NOT NULL,
    personnel_offense TEXT NOT NULL,
    formation TEXT NOT NULL,
    motion TEXT,
    play_family TEXT NOT NULL,
    concept TEXT,
    coverage TEXT,
    pressure TEXT,
    result_yards INTEGER NOT NULL DEFAULT 0,
    epa DOUBLE PRECISION,
    success BOOLEAN NOT NULL DEFAULT false,
    explosive BOOLEAN NOT NULL DEFAULT false,
    turnover BOOLEAN NOT NULL DEFAULT false,
    qb_player_id UUID REFERENCES players(id),
    cognition_events JSONB NOT NULL DEFAULT '{}'::jsonb,
    tags TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (game_id, play_sequence)
);

CREATE TABLE IF NOT EXISTS clips (
    id UUID PRIMARY KEY,
    play_id UUID NOT NULL REFERENCES plays(id) ON DELETE CASCADE,
    provider TEXT NOT NULL CHECK (provider IN ('s3','r2','railway_bucket')),
    object_key TEXT NOT NULL,
    start_ms INTEGER NOT NULL CHECK (start_ms >= 0),
    end_ms INTEGER NOT NULL CHECK (end_ms > start_ms),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS cognition_trait_scores (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    player_id UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    position TEXT NOT NULL,
    trait TEXT NOT NULL CHECK (trait IN (
        'perceptual_search',
        'decision_complexity',
        'working_memory_in_play',
        'processing_under_time',
        'composure_tilt',
        'learning_rate',
        'pre_post_snap_delta',
        'communication_load'
    )),
    score DOUBLE PRECISION NOT NULL CHECK (score BETWEEN 0 AND 100),
    sample_n INTEGER NOT NULL CHECK (sample_n >= 0),
    evidence_count INTEGER NOT NULL CHECK (evidence_count >= 0),
    confidence TEXT NOT NULL CHECK (confidence IN ('insufficient','directional','usable','strong')),
    as_of TIMESTAMPTZ NOT NULL DEFAULT now(),
    evidence JSONB NOT NULL DEFAULT '[]'::jsonb,
    UNIQUE (player_id, trait, as_of)
);

CREATE TABLE IF NOT EXISTS practice_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    player_id UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    event_date DATE NOT NULL,
    look_family TEXT NOT NULL,
    rep_number INTEGER NOT NULL,
    recognition_ms INTEGER,
    decision_correct BOOLEAN,
    communication_correct BOOLEAN,
    pressure_proxy BOOLEAN NOT NULL DEFAULT false,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS call_rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    opponent_name TEXT NOT NULL,
    rule_type TEXT NOT NULL CHECK (rule_type IN ('call','do_not_call','if_then')),
    situation TEXT NOT NULL,
    call_name TEXT NOT NULL,
    reason TEXT NOT NULL,
    sample_n INTEGER NOT NULL DEFAULT 0,
    priority INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS model_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    model_name TEXT NOT NULL,
    model_version TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id UUID,
    input_snapshot JSONB NOT NULL,
    output_snapshot JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Production provenance. ADD COLUMN keeps this file safe against V1 databases.
ALTER TABLE programs ADD COLUMN IF NOT EXISTS external_source TEXT;
ALTER TABLE programs ADD COLUMN IF NOT EXISTS external_id TEXT;
ALTER TABLE teams ADD COLUMN IF NOT EXISTS external_source TEXT;
ALTER TABLE teams ADD COLUMN IF NOT EXISTS external_id TEXT;
ALTER TABLE games ADD COLUMN IF NOT EXISTS external_source TEXT;
ALTER TABLE games ADD COLUMN IF NOT EXISTS external_id TEXT;
ALTER TABLE games ADD COLUMN IF NOT EXISTS season_type TEXT;
ALTER TABLE plays ADD COLUMN IF NOT EXISTS external_source TEXT;
ALTER TABLE plays ADD COLUMN IF NOT EXISTS external_id TEXT;

CREATE TABLE IF NOT EXISTS ingest_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source TEXT NOT NULL,
    season INTEGER,
    source_uri TEXT,
    status TEXT NOT NULL CHECK (status IN ('running','succeeded','failed')),
    rows_seen INTEGER NOT NULL DEFAULT 0,
    rows_inserted INTEGER NOT NULL DEFAULT 0,
    rows_updated INTEGER NOT NULL DEFAULT 0,
    rows_skipped INTEGER NOT NULL DEFAULT 0,
    error_count INTEGER NOT NULL DEFAULT 0,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS benchmark_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    query_name TEXT NOT NULL,
    parameters JSONB NOT NULL DEFAULT '{}'::jsonb,
    sample_count INTEGER NOT NULL,
    p50_ms DOUBLE PRECISION NOT NULL,
    p95_ms DOUBLE PRECISION NOT NULL,
    max_ms DOUBLE PRECISION NOT NULL,
    pass_threshold_ms DOUBLE PRECISION NOT NULL,
    passed BOOLEAN NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- V1 play-finder indexes: common filters must not require full-table scans.
CREATE INDEX IF NOT EXISTS idx_plays_offense_situation
    ON plays (offense_team_name, down, distance_bucket, field_zone, play_family);
CREATE INDEX IF NOT EXISTS idx_plays_defense_situation
    ON plays (defense_team_name, down, distance_bucket, field_zone, play_family);
CREATE INDEX IF NOT EXISTS idx_plays_personnel_formation
    ON plays (offense_team_name, personnel_offense, formation);
CREATE INDEX IF NOT EXISTS idx_plays_qb
    ON plays (qb_player_id);
CREATE INDEX IF NOT EXISTS idx_plays_game_sequence
    ON plays (game_id, play_sequence);
CREATE INDEX IF NOT EXISTS idx_cognition_player_trait
    ON cognition_trait_scores (player_id, trait, as_of DESC);
CREATE INDEX IF NOT EXISTS idx_call_rules_opponent
    ON call_rules (opponent_name, rule_type, priority DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_plays_external_identity
    ON plays (external_source, external_id)
    WHERE external_source IS NOT NULL AND external_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_games_external_identity
    ON games (external_source, external_id)
    WHERE external_source IS NOT NULL AND external_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_plays_source_situation
    ON plays (external_source, offense_team_name, down, distance_bucket, field_zone);
CREATE INDEX IF NOT EXISTS idx_ingest_runs_source_started
    ON ingest_runs (source, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_benchmark_runs_query_created
    ON benchmark_runs (query_name, created_at DESC);

-- College evidence added in V1.2.
ALTER TABLE plays ADD COLUMN IF NOT EXISTS ppa DOUBLE PRECISION;
ALTER TABLE plays ADD COLUMN IF NOT EXISTS source_play_type TEXT;
ALTER TABLE plays ADD COLUMN IF NOT EXISTS play_text TEXT;

-- Lieutenant v1.5: additive only.
ALTER TABLE players
    ADD COLUMN IF NOT EXISTS league_level TEXT NOT NULL DEFAULT 'OTHER'
    CHECK (league_level IN ('NFL','FBS','FCS','OTHER'));
ALTER TABLE players
    ADD COLUMN IF NOT EXISTS scout_visit_flag BOOLEAN NOT NULL DEFAULT false;

CREATE TABLE IF NOT EXISTS movement_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    play_id UUID NOT NULL REFERENCES plays(id) ON DELETE CASCADE,
    player_id UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    source TEXT NOT NULL,
    max_speed_mph DOUBLE PRECISION,
    accel DOUBLE PRECISION,
    cod DOUBLE PRECISION,
    sep_yards DOUBLE PRECISION,
    getoff_ms INTEGER,
    extra JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_movement_identity
    ON movement_events (play_id, player_id, source);
CREATE INDEX IF NOT EXISTS idx_movement_player ON movement_events (player_id);
CREATE INDEX IF NOT EXISTS idx_movement_play ON movement_events (play_id);
CREATE INDEX IF NOT EXISTS idx_movement_source ON movement_events (source);

CREATE TABLE IF NOT EXISTS lieutenant_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    question TEXT NOT NULL,
    filters JSONB NOT NULL DEFAULT '{}'::jsonb,
    answer JSONB NOT NULL,
    play_ids TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    model TEXT NOT NULL,
    latency_ms INTEGER NOT NULL CHECK (latency_ms >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS combine_results (
    player_id UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    event TEXT NOT NULL,
    value DOUBLE PRECISION NOT NULL,
    year INTEGER NOT NULL,
    source TEXT NOT NULL,
    PRIMARY KEY (player_id, event, year, source)
);

CREATE INDEX IF NOT EXISTS idx_combine_event_year_value
    ON combine_results (event, year, value);
