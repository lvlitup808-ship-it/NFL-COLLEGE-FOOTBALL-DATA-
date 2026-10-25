-- Program-scoped synthetic scenario persistence. Run once after existing pilot migrations.
CREATE TABLE IF NOT EXISTS synthetic_scenarios (
    id uuid PRIMARY KEY,
    program_id uuid NOT NULL REFERENCES programs(id),
    created_by uuid NOT NULL REFERENCES users(id),
    body jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT synthetic_scenario_object CHECK (jsonb_typeof(body) = 'object'),
    CONSTRAINT synthetic_scenario_version CHECK (body->>'version' = 'fieldmind-synthetic-v1'),
    CONSTRAINT synthetic_scenario_flag CHECK (body->'synthetic' = 'true'::jsonb)
);
CREATE INDEX IF NOT EXISTS idx_synthetic_scenarios_program_created ON synthetic_scenarios(program_id,created_at DESC);
