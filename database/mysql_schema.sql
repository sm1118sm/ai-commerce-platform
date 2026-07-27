CREATE TABLE IF NOT EXISTS users (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    email VARCHAR(254) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    nickname VARCHAR(30) NOT NULL,
    phone_number VARCHAR(20) NULL,
    role VARCHAR(20) NOT NULL DEFAULT 'USER',
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    created_at VARCHAR(32) NOT NULL,
    last_login_at VARCHAR(32) NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_users_email (email),
    UNIQUE KEY uq_users_nickname (nickname),
    UNIQUE KEY uq_users_phone_number (phone_number)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS products (
    product_id VARCHAR(32) NOT NULL,
    name VARCHAR(255) NOT NULL,
    category VARCHAR(100) NOT NULL,
    description TEXT NOT NULL,
    price INT UNSIGNED NOT NULL,
    popularity INT UNSIGNED NOT NULL DEFAULT 0,
    rating DOUBLE NOT NULL DEFAULT 0,
    emoji VARCHAR(32) NOT NULL,
    stock INT UNSIGNED NOT NULL DEFAULT 20,
    tags TEXT NOT NULL,
    brand VARCHAR(100) NOT NULL DEFAULT 'StylePick',
    PRIMARY KEY (product_id),
    CONSTRAINT chk_products_rating CHECK (rating >= 0),
    CONSTRAINT chk_products_stock CHECK (stock >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS user_preferences (
    user_id BIGINT UNSIGNED NOT NULL,
    interests_json JSON NOT NULL,
    budget_min INT UNSIGNED NOT NULL DEFAULT 0,
    budget_max INT UNSIGNED NOT NULL DEFAULT 250000,
    updated_at VARCHAR(32) NOT NULL,
    PRIMARY KEY (user_id),
    CONSTRAINT fk_preferences_user
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS user_favorites (
    user_id BIGINT UNSIGNED NOT NULL,
    product_id VARCHAR(32) NOT NULL,
    created_at VARCHAR(32) NOT NULL,
    PRIMARY KEY (user_id, product_id),
    CONSTRAINT fk_favorites_user
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_favorites_product
        FOREIGN KEY (product_id) REFERENCES products(product_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS user_cart (
    user_id BIGINT UNSIGNED NOT NULL,
    product_id VARCHAR(32) NOT NULL,
    quantity INT UNSIGNED NOT NULL,
    updated_at VARCHAR(32) NOT NULL,
    PRIMARY KEY (user_id, product_id),
    CONSTRAINT chk_cart_quantity CHECK (quantity BETWEEN 1 AND 10),
    CONSTRAINT fk_cart_user
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_cart_product
        FOREIGN KEY (product_id) REFERENCES products(product_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS behavior_logs (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id BIGINT UNSIGNED NOT NULL,
    session_id VARCHAR(64) NOT NULL,
    product_id VARCHAR(32) NULL,
    action_type VARCHAR(32) NOT NULL,
    search_keyword VARCHAR(255) NULL,
    created_at VARCHAR(32) NOT NULL,
    PRIMARY KEY (id),
    KEY idx_behavior_user_time (user_id, created_at),
    KEY idx_behavior_product_time (product_id, created_at),
    CONSTRAINT fk_behavior_user
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_behavior_product
        FOREIGN KEY (product_id) REFERENCES products(product_id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS user_orders (
    order_id VARCHAR(32) NOT NULL,
    user_id BIGINT UNSIGNED NOT NULL,
    total INT UNSIGNED NOT NULL,
    quantity INT UNSIGNED NOT NULL,
    status VARCHAR(32) NOT NULL,
    ordered_at VARCHAR(32) NOT NULL,
    PRIMARY KEY (order_id),
    KEY idx_orders_user_time (user_id, ordered_at),
    CONSTRAINT fk_orders_user
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS order_items (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    order_id VARCHAR(32) NOT NULL,
    product_id VARCHAR(32) NOT NULL,
    product_name VARCHAR(255) NOT NULL,
    quantity INT UNSIGNED NOT NULL,
    unit_price INT UNSIGNED NOT NULL,
    PRIMARY KEY (id),
    KEY idx_order_items_order (order_id),
    CONSTRAINT fk_order_items_order
        FOREIGN KEY (order_id) REFERENCES user_orders(order_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE OR REPLACE VIEW admin_user_overview AS
SELECT
    id,
    email AS login_id,
    nickname,
    CASE
        WHEN phone_number IS NULL THEN NULL
        ELSE CONCAT(
            LEFT(phone_number, 3),
            '-****-',
            RIGHT(phone_number, 4)
        )
    END AS masked_phone_number,
    'HASHED' AS password_status,
    role,
    status,
    created_at,
    last_login_at
FROM users;
