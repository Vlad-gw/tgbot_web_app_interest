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
-- 🔁 БЕЗОПАСНОЕ РАСШИРЕНИЕ transactions (если БД уже есть)
-- ============================================================

ALTER TABLE transactions
    ADD COLUMN IF NOT EXISTS suggested_category_id INTEGER;

ALTER TABLE transactions
    ADD COLUMN IF NOT EXISTS is_category_accepted BOOLEAN NOT NULL DEFAULT TRUE;

-- Внешний ключ для suggested_category_id
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

-- Защита от дублей бюджета
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
-- Напоминания (scheduler, APScheduler)
-- ============================================================

CREATE TABLE IF NOT EXISTS reminders (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    type TEXT NOT NULL,
    cron TEXT NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- Прогноз бюджета (ML)
-- ============================================================

CREATE TABLE IF NOT EXISTS budget_forecast (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    month DATE NOT NULL,
    predicted_amount NUMERIC(10,2) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (user_id, month)
);

COMMIT;