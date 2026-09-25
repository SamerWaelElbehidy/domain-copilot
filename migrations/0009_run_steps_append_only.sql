-- The audit log is append-only at the database level too (ADR-0006, T4).
-- The application already only inserts, but a second line of defence means an
-- ordinary bug or an injection through some other table cannot rewrite history.
-- A privileged operator can still disable the trigger; that case is what the
-- hash chain detects (docs/SECURITY.md).

CREATE FUNCTION run_steps_reject_change() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'run_steps is an append-only audit log: % is not allowed', TG_OP
        USING ERRCODE = 'restrict_violation';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER run_steps_append_only
    BEFORE UPDATE OR DELETE ON run_steps
    FOR EACH ROW EXECUTE FUNCTION run_steps_reject_change();

CREATE TRIGGER run_steps_no_truncate
    BEFORE TRUNCATE ON run_steps
    FOR EACH STATEMENT EXECUTE FUNCTION run_steps_reject_change();
