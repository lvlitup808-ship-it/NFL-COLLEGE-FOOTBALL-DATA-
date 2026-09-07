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
