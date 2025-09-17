-- Mini-Casino-World: baseline schema
-- Safe to run multiple times (if-not-exists everywhere)

-- 1) Helpers: updated_at trigger
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 2) Users
CREATE TABLE IF NOT EXISTS users (
  id              BIGSERIAL PRIMARY KEY,
  username        VARCHAR(50) UNIQUE NOT NULL,
  email           VARCHAR(100) UNIQUE NOT NULL,
  password_hash   TEXT NOT NULL,
  balance         NUMERIC(12,2) NOT NULL DEFAULT 0.00,
  is_active       BOOLEAN NOT NULL DEFAULT TRUE,
  created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMP NOT NULL DEFAULT NOW()
);
DROP TRIGGER IF EXISTS trg_users_updated ON users;
CREATE TRIGGER trg_users_updated
BEFORE UPDATE ON users
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE INDEX IF NOT EXISTS idx_users_email ON users (email);
CREATE INDEX IF NOT EXISTS idx_users_username ON users (username);

-- 3) Games (catalog of game types)
CREATE TABLE IF NOT EXISTS games (
  id          BIGSERIAL PRIMARY KEY,
  name        VARCHAR(100) NOT NULL,      -- e.g., "Red Hearts Slots"
  type        VARCHAR(50)  NOT NULL,      -- e.g., "slots","blackjack"
  house_edge  NUMERIC(5,2),               -- optional % info
  is_active   BOOLEAN NOT NULL DEFAULT TRUE,
  created_at  TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_games_name ON games (name);

-- 4) Bets (each spin/hand/round logged)
CREATE TABLE IF NOT EXISTS bets (
  id          BIGSERIAL PRIMARY KEY,
  user_id     BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  game_id     BIGINT NOT NULL REFERENCES games(id) ON DELETE RESTRICT,
  amount      NUMERIC(12,2) NOT NULL CHECK (amount > 0),
  outcome     VARCHAR(20),                -- "win","lose","push"
  payout      NUMERIC(12,2) DEFAULT 0.00, -- amount returned to player
  result_meta JSONB,                      -- optional: reels/cards, etc.
  created_at  TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_bets_user_time ON bets (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_bets_game_time ON bets (game_id, created_at DESC);

-- 5) Transactions (deposits/withdrawals/bonus)
CREATE TABLE IF NOT EXISTS transactions (
  id          BIGSERIAL PRIMARY KEY,
  user_id     BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  amount      NUMERIC(12,2) NOT NULL,
  type        VARCHAR(20) NOT NULL,        -- "deposit","withdrawal","bonus","adjust"
  status      VARCHAR(20) NOT NULL DEFAULT 'pending', -- "pending","completed","failed"
  ref_code    VARCHAR(64),                 -- optional external reference
  created_at  TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_tx_user_time ON transactions (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_tx_status ON transactions (status);

-- 6) Simple leaderboard materialized view (optional, drop if not needed)
CREATE MATERIALIZED VIEW IF NOT EXISTS leaderboard AS
SELECT
  u.id AS user_id,
  u.username,
  COALESCE(SUM(b.payout - b.amount), 0) AS net_winnings
FROM users u
LEFT JOIN bets b ON b.user_id = u.id
GROUP BY u.id, u.username
ORDER BY net_winnings DESC;

-- Refresh helper (call when you need)
-- REFRESH MATERIALIZED VIEW leaderboard;