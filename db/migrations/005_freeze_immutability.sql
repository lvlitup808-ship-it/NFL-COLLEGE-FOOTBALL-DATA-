-- Thursday freeze is a real snapshot boundary for game-plan inputs.
-- Changed-call outcome logs remain writable after freeze by design.

CREATE OR REPLACE FUNCTION fieldmind_block_frozen_week_mutation()
RETURNS TRIGGER AS $$
DECLARE
    target_week UUID;
    target_status TEXT;
BEGIN
    target_week := COALESCE(NEW.week_plan_id, OLD.week_plan_id);
    SELECT status INTO target_status FROM week_plans WHERE id=target_week;
    IF target_status = 'frozen' THEN
        RAISE EXCEPTION 'week_plan_frozen';
    END IF;
    RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_call_rules_frozen ON call_rules;
CREATE TRIGGER trg_call_rules_frozen
BEFORE INSERT OR UPDATE OR DELETE ON call_rules
FOR EACH ROW EXECUTE FUNCTION fieldmind_block_frozen_week_mutation();

DROP TRIGGER IF EXISTS trg_player_look_frozen ON player_look_evidence;
CREATE TRIGGER trg_player_look_frozen
BEFORE INSERT OR UPDATE OR DELETE ON player_look_evidence
FOR EACH ROW EXECUTE FUNCTION fieldmind_block_frozen_week_mutation();
