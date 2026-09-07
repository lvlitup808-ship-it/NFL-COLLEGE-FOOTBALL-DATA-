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
CREATE INDEX IF NOT EXISTS idx_movement_player
    ON movement_events (player_id);
CREATE INDEX IF NOT EXISTS idx_movement_play
    ON movement_events (play_id);
CREATE INDEX IF NOT EXISTS idx_movement_source
    ON movement_events (source);

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
