-- Keep existing release/payment ownership IDs stable. New web accounts use negative IDs.
BEGIN;
LOCK TABLE label IN SHARE ROW EXCLUSIVE MODE;
-- Imported users may have IDs ahead of the SERIAL sequence.
DO $$
DECLARE sequence_name TEXT; sequence_value BIGINT; max_id BIGINT;
BEGIN
    SELECT pg_get_serial_sequence('label', 'id') INTO sequence_name;
    IF sequence_name IS NOT NULL THEN
        EXECUTE format('SELECT last_value FROM %s', sequence_name) INTO sequence_value;
        SELECT COALESCE(MAX(id), 0) INTO max_id FROM label;
        PERFORM setval(sequence_name, GREATEST(sequence_value, max_id, 1), TRUE);
    END IF;
END $$;
CREATE SEQUENCE IF NOT EXISTS web_account_ids;
CREATE UNIQUE INDEX IF NOT EXISTS label_telegram_account_unique ON label(telegram_id);
ALTER TABLE label ADD COLUMN IF NOT EXISTS notification_telegram_id BIGINT;
ALTER TABLE label ADD COLUMN IF NOT EXISTS telegram_notifications BOOLEAN NOT NULL DEFAULT TRUE;
CREATE UNIQUE INDEX IF NOT EXISTS label_notification_telegram_unique ON label(notification_telegram_id) WHERE notification_telegram_id IS NOT NULL;
CREATE TABLE IF NOT EXISTS web_auth_identities (
    provider TEXT NOT NULL CHECK (provider IN ('email', 'google', 'yandex')),
    subject TEXT NOT NULL,
    account_id BIGINT NOT NULL REFERENCES label(telegram_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY(provider, subject),
    UNIQUE(account_id, provider)
);
CREATE TABLE IF NOT EXISTS web_email_challenges (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL,
    code_hash TEXT NOT NULL,
    display_name TEXT NOT NULL DEFAULT '',
    link_account_id BIGINT REFERENCES label(telegram_id),
    attempts INTEGER NOT NULL DEFAULT 0,
    delivered BOOLEAN NOT NULL DEFAULT FALSE,
    used BOOLEAN NOT NULL DEFAULT FALSE,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS web_email_challenges_email ON web_email_challenges(email, created_at);
CREATE TABLE IF NOT EXISTS web_oauth_states (
    state_hash TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    verifier TEXT NOT NULL,
    link_account_id BIGINT REFERENCES label(telegram_id),
    expires_at TIMESTAMPTZ NOT NULL,
    used BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE TABLE IF NOT EXISTS web_telegram_link_tokens (
    token_hash TEXT PRIMARY KEY,
    account_id BIGINT NOT NULL REFERENCES label(telegram_id),
    expires_at TIMESTAMPTZ NOT NULL,
    used BOOLEAN NOT NULL DEFAULT FALSE
);
COMMIT;
