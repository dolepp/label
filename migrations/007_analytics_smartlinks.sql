BEGIN;
CREATE TABLE IF NOT EXISTS website_analytics_settings (
 id INTEGER PRIMARY KEY CHECK(id=1), configuration JSONB NOT NULL,
 updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS website_analytics_events (
 id BIGSERIAL PRIMARY KEY,event_type TEXT NOT NULL,context TEXT NOT NULL DEFAULT '',
 release_id BIGINT,platform TEXT NOT NULL DEFAULT '',created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS website_analytics_events_date_idx ON website_analytics_events(created_at);
CREATE INDEX IF NOT EXISTS website_analytics_events_release_idx ON website_analytics_events(release_id,created_at);
CREATE TABLE IF NOT EXISTS release_smartlinks (
 id BIGSERIAL PRIMARY KEY,release_id BIGINT NOT NULL UNIQUE,user_id BIGINT NOT NULL,
 slug TEXT NOT NULL UNIQUE,platform_links JSONB NOT NULL DEFAULT '{}',published BOOLEAN NOT NULL DEFAULT true,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMIT;
