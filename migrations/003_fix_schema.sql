ALTER TABLE label ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;

CREATE OR REPLACE FUNCTION update_modified_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger WHERE tgname = 'update_label_modtime'
    ) THEN
        CREATE TRIGGER update_label_modtime
            BEFORE UPDATE ON label
            FOR EACH ROW
            EXECUTE FUNCTION update_modified_column();
    END IF;
END;
$$;
