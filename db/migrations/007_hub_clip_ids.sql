-- FIELDMIND hub: source identity map, personal clip overlays, and saved Play Finder searches.
-- Applied after 006_roster_tenancy.sql. Additive only.

CREATE TABLE IF NOT EXISTS entity_ids (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    program_id UUID REFERENCES programs(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('team','player','game','play')),
    canonical_id UUID NOT NULL,
    source TEXT NOT NULL CHECK (source IN (
        'cfbd','nflverse','espn','pfr','gsis','hudl','fieldmind','other'
    )),
    external_id TEXT NOT NULL,
    label TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_entity_ids_source_identity
    ON entity_ids (
        kind, source, external_id,
        COALESCE(program_id, '00000000-0000-0000-0000-000000000000'::uuid)
    );
CREATE INDEX IF NOT EXISTS idx_entity_ids_canonical
    ON entity_ids (kind, canonical_id);
CREATE INDEX IF NOT EXISTS idx_entity_ids_program_source
    ON entity_ids (program_id, kind, source);

CREATE TABLE IF NOT EXISTS play_telestrates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    program_id UUID NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    play_id UUID NOT NULL REFERENCES plays(id) ON DELETE CASCADE,
    created_by UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    strokes JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (program_id, play_id, created_by)
);

CREATE INDEX IF NOT EXISTS idx_play_telestrates_program_play
    ON play_telestrates (program_id, play_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS play_searches (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    program_id UUID NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    query JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (program_id, user_id, name)
);

CREATE INDEX IF NOT EXISTS idx_play_searches_owner
    ON play_searches (program_id, user_id, name);
CREATE INDEX IF NOT EXISTS idx_plays_offense_finder
    ON plays (offense_team_name, down, distance_bucket, field_zone);
CREATE INDEX IF NOT EXISTS idx_plays_defense_finder
    ON plays (defense_team_name, down, distance_bucket, field_zone);
CREATE INDEX IF NOT EXISTS idx_plays_game_sequence_finder
    ON plays (game_id, play_sequence);
CREATE INDEX IF NOT EXISTS idx_plays_text_search
    ON plays USING GIN (to_tsvector('simple', COALESCE(play_text, '')));

-- Global rows record source identities observed by ingest. Tenant rows are never
-- targeted by this backfill, so program overrides cannot be overwritten.
INSERT INTO entity_ids (program_id, kind, canonical_id, source, external_id, label)
SELECT NULL, 'team', id, external_source, external_id, name
FROM teams
WHERE external_source IN ('cfbd','nflverse') AND external_id IS NOT NULL
ON CONFLICT DO NOTHING;

INSERT INTO entity_ids (program_id, kind, canonical_id, source, external_id)
SELECT NULL, 'game', id, external_source, external_id
FROM games
WHERE external_source IN ('cfbd','nflverse') AND external_id IS NOT NULL
ON CONFLICT DO NOTHING;

INSERT INTO entity_ids (program_id, kind, canonical_id, source, external_id)
SELECT NULL, 'play', id, external_source, external_id
FROM plays
WHERE external_source IN ('cfbd','nflverse') AND external_id IS NOT NULL
ON CONFLICT DO NOTHING;
