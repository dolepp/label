BEGIN;
CREATE TABLE IF NOT EXISTS release_contract_profiles (
 user_id BIGINT PRIMARY KEY,
 encrypted_data TEXT NOT NULL,
 consent_version TEXT NOT NULL,
 updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS generated_release_contracts (
 release_id BIGINT PRIMARY KEY,
 user_id BIGINT NOT NULL,
 contract_number TEXT NOT NULL UNIQUE,
 template_version TEXT NOT NULL,
 relative_path TEXT NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS generated_release_contracts_user_idx ON generated_release_contracts(user_id);
COMMIT;
CREATE TABLE IF NOT EXISTS web_legal_consents (
 id BIGSERIAL PRIMARY KEY,
 user_id BIGINT,
 document_version TEXT NOT NULL,
 form_scope TEXT NOT NULL,
 personal_data BOOLEAN NOT NULL,
 terms_accepted BOOLEAN NOT NULL DEFAULT false,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
