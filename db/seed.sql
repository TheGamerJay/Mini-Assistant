-- Seed a few games and a test user (replace emails/passwords in real use)

INSERT INTO games (name, type, house_edge)
VALUES
  ('MCW Slots – Red Hearts', 'slots', 4.00),
  ('MCW Blackjack', 'blackjack', 0.50),
  ('MCW Roulette', 'roulette', 5.26)
ON CONFLICT DO NOTHING;

-- demo user with zero balance; store a real hash in production
INSERT INTO users (username, email, password_hash, balance)
VALUES ('demo', 'demo@mcw.local', '$2b$12$DEMO_HASH_REPLACE_ME', 100.00)
ON CONFLICT DO NOTHING;