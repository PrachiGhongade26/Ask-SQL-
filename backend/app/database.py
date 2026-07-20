"""
DuckDB connection and sample data loader for NL-to-SQL Assistant.
"""
import duckdb
import os

DB_PATH = "data/app.duckdb"
DATA_DIR = "data"


def get_connection():
    """Returns a DuckDB connection."""
    conn = duckdb.connect(DB_PATH)
    return conn


def load_sample_data(conn):
    """Loads CSV files from data/ into DuckDB tables."""
    tables = ["customers", "products", "orders", "order_items"]

    for table in tables:
        csv_path = os.path.join(DATA_DIR, f"{table}.csv")
        conn.execute(f"""
            CREATE OR REPLACE TABLE {table} AS
            SELECT * FROM read_csv_auto('{csv_path}')
        """)
        print(f"Loaded table: {table}")


if __name__ == "__main__":
    conn = get_connection()
    print("Connected to DuckDB successfully.")
    load_sample_data(conn)
    print("All tables loaded.")

    # Quick test query
    result = conn.execute("SELECT COUNT(*) FROM customers").fetchone()
    print(f"Customers table row count: {result[0]}")