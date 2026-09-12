-- Approved calls must clear the locked n-guard. Candidate rows may remain low-n questions.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname='call_rules_approved_evidence_check'
    ) THEN
        ALTER TABLE call_rules ADD CONSTRAINT call_rules_approved_evidence_check
            CHECK (
                status <> 'approved'
                OR (
                    sample_n >= 8
                    AND confidence IN ('directional','usable')
                )
            );
    END IF;
END $$;
