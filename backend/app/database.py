"""
DuckDB connection and sample data loader for NL-to-SQL Assistant.
"""

import duckdb

DB_PATH = "data/app.duckdb"

def get_connection():
    """Returns a DuckDB connection."""
    conn = duckdb.connect(DB_PATH)
    return conn

def load_sample_data(conn):
    """TODO: load sample dataset into DuckDB tables."""
    pass

if __name__ == "__main__":
    conn = get_connection()
    print("Connected to DuckDB successfully.")