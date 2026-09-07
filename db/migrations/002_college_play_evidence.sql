ALTER TABLE plays ADD COLUMN IF NOT EXISTS ppa DOUBLE PRECISION;
ALTER TABLE plays ADD COLUMN IF NOT EXISTS source_play_type TEXT;
ALTER TABLE plays ADD COLUMN IF NOT EXISTS play_text TEXT;

CREATE INDEX IF NOT EXISTS idx_plays_cfbd_situation
    ON plays (external_source, offense_team_name, down, distance_bucket, field_zone, play_family)
    WHERE external_source = 'cfbd';
