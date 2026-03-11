-- ============================================================
-- init_db.sql
-- Инициализация и расширение БД (без потери данных)
-- PostgreSQL
-- ============================================================

BEGIN;

-- ============================================================
-- Пользователи
-- ============================================================

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    telegram_id BIGINT UNIQUE NOT NULL,
    username TEXT,
    first_name TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- Категории доходов и расходов
-- ============================================================

CREATE TABLE IF NOT EXISTS categories (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    type TEXT CHECK (type IN ('income', 'expense')) NOT NULL
);

-- ============================================================
-- Транзакции
-- ============================================================

CREATE TABLE IF NOT EXISTS transactions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
    amount NUMERIC(10,2) NOT NULL,
    date TIMESTAMP NOT NULL,
    type TEXT CHECK (type IN ('income', 'expense')) NOT NULL,
    note TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- Безопасное расширение transactions
-- ============================================================

ALTER TABLE transactions
    ADD COLUMN IF NOT EXISTS suggested_category_id INTEGER;

ALTER TABLE transactions
    ADD COLUMN IF NOT EXISTS is_category_accepted BOOLEAN NOT NULL DEFAULT TRUE;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.table_constraints
        WHERE constraint_name = 'transactions_suggested_category_fkey'
    ) THEN
        ALTER TABLE transactions
            ADD CONSTRAINT transactions_suggested_category_fkey
            FOREIGN KEY (suggested_category_id)
            REFERENCES categories(id)
            ON DELETE SET NULL;
    END IF;
END$$;

-- ============================================================
-- Бюджеты
-- ============================================================

CREATE TABLE IF NOT EXISTS budgets (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    category_id INTEGER REFERENCES categories(id) ON DELETE CASCADE,
    month DATE NOT NULL,
    limit_amount NUMERIC(10,2) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.table_constraints
        WHERE constraint_name = 'budgets_user_category_month_unique'
    ) THEN
        ALTER TABLE budgets
            ADD CONSTRAINT budgets_user_category_month_unique
            UNIQUE (user_id, category_id, month);
    END IF;
END$$;

-- ============================================================
-- Напоминания
-- Старая структура сохранена и расширена под пользовательские уведомления
-- ============================================================

CREATE TABLE IF NOT EXISTS reminders (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    type TEXT NOT NULL DEFAULT 'daily_transaction_reminder',
    cron TEXT NOT NULL DEFAULT '0 20 * * *',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);

ALTER TABLE reminders
    ADD COLUMN IF NOT EXISTS enabled BOOLEAN NOT NULL DEFAULT TRUE;

ALTER TABLE reminders
    ADD COLUMN IF NOT EXISTS remind_time TIME NOT NULL DEFAULT '20:00:00';

ALTER TABLE reminders
    ADD COLUMN IF NOT EXISTS last_sent_date DATE;

ALTER TABLE reminders
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT NOW();

UPDATE reminders
SET enabled = COALESCE(is_active, TRUE)
WHERE enabled IS DISTINCT FROM COALESCE(is_active, TRUE);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.table_constraints
        WHERE constraint_name = 'reminders_user_unique'
    ) THEN
        ALTER TABLE reminders
            ADD CONSTRAINT reminders_user_unique UNIQUE (user_id);
    END IF;
END$$;

-- ============================================================
-- Прогноз бюджета
-- ============================================================

CREATE TABLE IF NOT EXISTS budget_forecast (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    month DATE NOT NULL,
    predicted_amount NUMERIC(10,2) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (user_id, month)
);

-- ============================================================
-- Импорт банковских выписок
-- ============================================================

CREATE TABLE IF NOT EXISTS statement_imports (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    bank_name TEXT NOT NULL,
    file_name TEXT NOT NULL,
    file_type TEXT NOT NULL,
    period_from DATE,
    period_to DATE,
    total_found INTEGER NOT NULL DEFAULT 0,
    total_imported INTEGER NOT NULL DEFAULT 0,
    total_duplicates INTEGER NOT NULL DEFAULT 0,
    total_skipped INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW()
);

ALTER TABLE transactions
    ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'manual';

ALTER TABLE transactions
    ADD COLUMN IF NOT EXISTS source_bank TEXT;

ALTER TABLE transactions
    ADD COLUMN IF NOT EXISTS source_external_id TEXT;

ALTER TABLE transactions
    ADD COLUMN IF NOT EXISTS source_hash TEXT;

ALTER TABLE transactions
    ADD COLUMN IF NOT EXISTS import_batch_id INTEGER REFERENCES statement_imports(id) ON DELETE SET NULL;

ALTER TABLE transactions
    ADD COLUMN IF NOT EXISTS raw_description TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS ux_transactions_user_bank_external_id
    ON transactions(user_id, source_bank, source_external_id)
    WHERE source_external_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS ux_transactions_user_source_hash
    ON transactions(user_id, source_hash)
    WHERE source_hash IS NOT NULL;

COMMIT;