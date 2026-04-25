import psycopg2

DB_KWARGS = dict(
    host="postgres",
    port=5432,
    user="testuser",
    password="testpass",
    dbname="testdb",
    options="-c statement_timeout=8000 -c lock_timeout=2000",
)


def get_conn():
    return psycopg2.connect(**DB_KWARGS)
