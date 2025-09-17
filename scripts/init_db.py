import os, pathlib, psycopg2

SCHEMA_PATH = pathlib.Path(__file__).parent.parent / "db" / "schema.sql"
SEED_PATH   = pathlib.Path(__file__).parent.parent / "db" / "seed.sql"

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise SystemExit("ERROR: DATABASE_URL not set.")

def run_sql(path):
    with open(path, "r", encoding="utf-8") as f:
        sql = f.read()
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            print(f"✓ Ran {path.name}")
    finally:
        conn.close()

if __name__ == "__main__":
    run_sql(SCHEMA_PATH)
    if os.getenv("LOAD_SEED", "0") == "1":
        run_sql(SEED_PATH)