CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    nickname TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'USER',
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    created_at TEXT NOT NULL,
    last_login_at TEXT
);

CREATE TABLE IF NOT EXISTS products (
    product_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    description TEXT NOT NULL,
    price INTEGER NOT NULL CHECK (price >= 0),
    popularity INTEGER NOT NULL DEFAULT 0,
    rating DOUBLE PRECISION NOT NULL DEFAULT 0,
    emoji TEXT NOT NULL,
    stock INTEGER NOT NULL DEFAULT 20 CHECK (stock >= 0),
    tags TEXT NOT NULL DEFAULT '',
    brand TEXT NOT NULL DEFAULT 'StylePick'
);

CREATE TABLE IF NOT EXISTS user_preferences (
    user_id BIGINT PRIMARY KEY REFERENCES users(id),
    interests_json TEXT NOT NULL DEFAULT '[]',
    budget_min INTEGER NOT NULL DEFAULT 0,
    budget_max INTEGER NOT NULL DEFAULT 250000,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user_favorites (
    user_id BIGINT NOT NULL REFERENCES users(id),
    product_id TEXT NOT NULL REFERENCES products(product_id),
    created_at TEXT NOT NULL,
    PRIMARY KEY (user_id, product_id)
);

CREATE TABLE IF NOT EXISTS user_cart (
    user_id BIGINT NOT NULL REFERENCES users(id),
    product_id TEXT NOT NULL REFERENCES products(product_id),
    quantity INTEGER NOT NULL CHECK (quantity BETWEEN 1 AND 10),
    updated_at TEXT NOT NULL,
    PRIMARY KEY (user_id, product_id)
);

CREATE TABLE IF NOT EXISTS behavior_logs (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    session_id TEXT NOT NULL,
    product_id TEXT REFERENCES products(product_id),
    action_type TEXT NOT NULL,
    search_keyword TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_behavior_user_time
    ON behavior_logs(user_id, created_at);

CREATE INDEX IF NOT EXISTS idx_behavior_product_time
    ON behavior_logs(product_id, created_at);

CREATE TABLE IF NOT EXISTS user_orders (
    order_id TEXT PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    total INTEGER NOT NULL,
    quantity INTEGER NOT NULL,
    status TEXT NOT NULL,
    ordered_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS order_items (
    id BIGSERIAL PRIMARY KEY,
    order_id TEXT NOT NULL REFERENCES user_orders(order_id),
    product_id TEXT NOT NULL,
    product_name TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price INTEGER NOT NULL
);

