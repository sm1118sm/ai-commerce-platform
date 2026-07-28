CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    email VARCHAR(254) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    nickname VARCHAR(30) NOT NULL,
    phone_number VARCHAR(20) NULL,
    role VARCHAR(20) NOT NULL DEFAULT 'USER',
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    created_at VARCHAR(32) NOT NULL,
    last_login_at VARCHAR(32) NULL,
    CONSTRAINT uq_users_phone_number UNIQUE (phone_number)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_users_email_normalized
    ON users (LOWER(BTRIM(email)));
CREATE UNIQUE INDEX IF NOT EXISTS uq_users_nickname_normalized
    ON users (LOWER(BTRIM(nickname)));

CREATE TABLE IF NOT EXISTS products (
    product_id VARCHAR(32) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    category VARCHAR(100) NOT NULL,
    description TEXT NOT NULL,
    price INTEGER NOT NULL CHECK (price >= 0),
    popularity INTEGER NOT NULL DEFAULT 0 CHECK (popularity >= 0),
    rating DOUBLE PRECISION NOT NULL DEFAULT 0 CHECK (rating >= 0),
    emoji VARCHAR(32) NOT NULL,
    stock INTEGER NOT NULL DEFAULT 20 CHECK (stock >= 0),
    tags TEXT NOT NULL,
    brand VARCHAR(100) NOT NULL DEFAULT 'StylePick'
);

CREATE TABLE IF NOT EXISTS user_preferences (
    user_id BIGINT PRIMARY KEY,
    interests_json JSONB NOT NULL,
    budget_min INTEGER NOT NULL DEFAULT 0 CHECK (budget_min >= 0),
    budget_max INTEGER NOT NULL DEFAULT 250000 CHECK (budget_max >= 0),
    updated_at VARCHAR(32) NOT NULL,
    CONSTRAINT fk_preferences_user
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS user_favorites (
    user_id BIGINT NOT NULL,
    product_id VARCHAR(32) NOT NULL,
    created_at VARCHAR(32) NOT NULL,
    PRIMARY KEY (user_id, product_id),
    CONSTRAINT fk_favorites_user
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_favorites_product
        FOREIGN KEY (product_id) REFERENCES products(product_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS user_cart (
    user_id BIGINT NOT NULL,
    product_id VARCHAR(32) NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity BETWEEN 1 AND 10),
    updated_at VARCHAR(32) NOT NULL,
    PRIMARY KEY (user_id, product_id),
    CONSTRAINT fk_cart_user
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_cart_product
        FOREIGN KEY (product_id) REFERENCES products(product_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS behavior_logs (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    session_id VARCHAR(64) NOT NULL,
    product_id VARCHAR(32) NULL,
    action_type VARCHAR(32) NOT NULL,
    search_keyword VARCHAR(255) NULL,
    created_at VARCHAR(32) NOT NULL,
    CONSTRAINT fk_behavior_user
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_behavior_product
        FOREIGN KEY (product_id) REFERENCES products(product_id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_behavior_user_time
    ON behavior_logs (user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_behavior_product_time
    ON behavior_logs (product_id, created_at);

CREATE TABLE IF NOT EXISTS user_orders (
    order_id VARCHAR(32) PRIMARY KEY,
    user_id BIGINT NOT NULL,
    total INTEGER NOT NULL CHECK (total >= 0),
    quantity INTEGER NOT NULL CHECK (quantity >= 0),
    status VARCHAR(32) NOT NULL,
    ordered_at VARCHAR(32) NOT NULL,
    CONSTRAINT fk_orders_user
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_orders_user_time
    ON user_orders (user_id, ordered_at);

CREATE TABLE IF NOT EXISTS order_items (
    id BIGSERIAL PRIMARY KEY,
    order_id VARCHAR(32) NOT NULL,
    product_id VARCHAR(32) NOT NULL,
    product_name VARCHAR(255) NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity >= 0),
    unit_price INTEGER NOT NULL CHECK (unit_price >= 0),
    CONSTRAINT fk_order_items_order
        FOREIGN KEY (order_id) REFERENCES user_orders(order_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_order_items_order
    ON order_items (order_id);

CREATE TABLE IF NOT EXISTS product_reviews (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    product_id VARCHAR(32) NOT NULL,
    order_id VARCHAR(32) NOT NULL,
    rating SMALLINT NOT NULL CHECK (rating BETWEEN 1 AND 5),
    content VARCHAR(500) NOT NULL,
    created_at VARCHAR(32) NOT NULL,
    updated_at VARCHAR(32) NOT NULL,
    CONSTRAINT uq_reviews_user_product UNIQUE (user_id, product_id),
    CONSTRAINT fk_reviews_user
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_reviews_product
        FOREIGN KEY (product_id) REFERENCES products(product_id) ON DELETE CASCADE,
    CONSTRAINT fk_reviews_order
        FOREIGN KEY (order_id) REFERENCES user_orders(order_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_reviews_product_time
    ON product_reviews (product_id, updated_at);

CREATE OR REPLACE VIEW admin_user_overview AS
SELECT
    id,
    email AS login_id,
    nickname,
    CASE
        WHEN phone_number IS NULL THEN NULL
        ELSE LEFT(phone_number, 3) || '-****-' || RIGHT(phone_number, 4)
    END AS masked_phone_number,
    'HASHED'::VARCHAR(6) AS password_status,
    role,
    status,
    created_at,
    last_login_at
FROM users;
