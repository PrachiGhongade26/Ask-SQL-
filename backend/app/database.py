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

"""
DuckDB connection, dynamic CSV loading, and schema introspection for AskSQL.
"""
import duckdb
import os
import re

DB_PATH = "data/app.duckdb"
DATA_DIR = "data"


def get_connection():
    """Returns a DuckDB connection."""
    conn = duckdb.connect(DB_PATH)
    return conn


def load_sample_data(conn):
    """Loads the fixed sample CSV files from data/ into DuckDB tables."""
    tables = ["customers", "products", "orders", "order_items"]
    for table in tables:
        csv_path = os.path.join(DATA_DIR, f"{table}.csv")
        conn.execute(f"""
            CREATE OR REPLACE TABLE {table} AS
            SELECT * FROM read_csv_auto('{csv_path}')
        """)
        print(f"Loaded table: {table}")


def sanitize_table_name(filename: str) -> str:
    """
    Converts an uploaded filename into a safe DuckDB table name.
    e.g. "Sales Report (2025).csv" -> "sales_report_2025"
    """
    name = os.path.splitext(filename)[0]
    name = name.lower().strip()
    name = re.sub(r"[^a-z0-9_]+", "_", name)
    name = re.sub(r"_+", "_", name).strip("_")
    if not name or not name[0].isalpha():
        name = f"t_{name}"
    return name


def load_uploaded_csv(conn, file_path: str, table_name: str) -> str:
    """
    Loads a CSV file from disk into a DuckDB table.

    Args:
        conn: an active DuckDB connection.
        file_path: path to the CSV file on disk.
        table_name: sanitized table name to create/replace.

    Returns:
        The table name that was created.
    """
    conn.execute(f"""
        CREATE OR REPLACE TABLE {table_name} AS
        SELECT * FROM read_csv_auto('{file_path}')
    """)
    return table_name


def get_schema_string(conn, table_name: str | None = None) -> str:
    """
    Builds a schema description string for one table or all user tables,
    formatted for the NL-to-SQL prompt.

    Args:
        conn: an active DuckDB connection.
        table_name: if given, only describe this table. Otherwise describe
                    every table currently in the database.

    Returns:
        A string like:
        "TABLE sales(id INTEGER, region VARCHAR, amount DOUBLE, sale_date DATE)"
    """
    if table_name:
        table_names = [table_name]
    else:
        rows = conn.execute("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'main'
        """).fetchall()
        table_names = [r[0] for r in rows]

    schema_parts = []
    for name in table_names:
        columns = conn.execute(f"""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = '{name}'
            ORDER BY ordinal_position
        """).fetchall()
        col_str = ", ".join(f"{col} {dtype}" for col, dtype in columns)
        schema_parts.append(f"TABLE {name}({col_str})")

    return "\n".join(schema_parts)


if __name__ == "__main__":
    conn = get_connection()
    print("Connected to DuckDB successfully.")
    load_sample_data(conn)
    print("All tables loaded.")

    result = conn.execute("SELECT COUNT(*) FROM customers").fetchone()
    print(f"Customers table row count: {result[0]}")

    print("\nSchema for all tables:")
    print(get_schema_string(conn))
