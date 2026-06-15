-- Таблица заявок в поддержку
CREATE TABLE IF NOT EXISTS support_requests (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    template_id TEXT,
    title TEXT,
    fields JSONB DEFAULT '{}',
    status TEXT DEFAULT 'принят',
    admin_comment TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Таблица дизайн-брифов
CREATE TABLE IF NOT EXISTS design_brief_requests (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    service_type TEXT,
    title TEXT,
    fields JSONB DEFAULT '{}',
    status TEXT DEFAULT 'в обработке',
    payment_id TEXT,
    admin_comment TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_support_requests_user ON support_requests(user_id);
CREATE INDEX IF NOT EXISTS idx_support_requests_status ON support_requests(status);
CREATE INDEX IF NOT EXISTS idx_design_brief_user ON design_brief_requests(user_id);
CREATE INDEX IF NOT EXISTS idx_design_brief_status ON design_brief_requests(status);
