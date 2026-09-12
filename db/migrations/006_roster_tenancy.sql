-- Enforce that weekly plans and player-look evidence reference the customer's own roster.

CREATE OR REPLACE FUNCTION fieldmind_validate_week_plan_team()
RETURNS TRIGGER AS $$
DECLARE
    team_program UUID;
BEGIN
    IF NEW.team_id IS NULL THEN
        RETURN NEW;
    END IF;
    SELECT program_id INTO team_program FROM teams WHERE id=NEW.team_id;
    IF team_program IS NULL OR team_program <> NEW.program_id THEN
        RAISE EXCEPTION 'week_plan_team_must_belong_to_program';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_week_plan_team_tenant ON week_plans;
CREATE TRIGGER trg_week_plan_team_tenant
BEFORE INSERT OR UPDATE OF team_id,program_id ON week_plans
FOR EACH ROW EXECUTE FUNCTION fieldmind_validate_week_plan_team();

CREATE OR REPLACE FUNCTION fieldmind_validate_player_look_tenant()
RETURNS TRIGGER AS $$
DECLARE
    plan_program UUID;
    plan_team UUID;
    player_team UUID;
BEGIN
    SELECT program_id,team_id INTO plan_program,plan_team
    FROM week_plans WHERE id=NEW.week_plan_id;

    IF plan_program IS NULL OR plan_program <> NEW.program_id THEN
        RAISE EXCEPTION 'player_evidence_program_mismatch';
    END IF;
    IF plan_team IS NULL THEN
        RAISE EXCEPTION 'week_plan_roster_required';
    END IF;

    SELECT team_id INTO player_team FROM players WHERE id=NEW.player_id;
    IF player_team IS NULL OR player_team <> plan_team THEN
        RAISE EXCEPTION 'player_must_belong_to_week_plan_roster';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_player_look_tenant ON player_look_evidence;
CREATE TRIGGER trg_player_look_tenant
BEFORE INSERT OR UPDATE OF program_id,week_plan_id,player_id ON player_look_evidence
FOR EACH ROW EXECUTE FUNCTION fieldmind_validate_player_look_tenant();
