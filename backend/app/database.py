"""
DuckDB connection, dynamic CSV loading, and schema introspection for AskSQL.
"""
import duckdb
import os
import re

DB_PATH = "data/app.duckdb"
DATA_DIR = "data"

# Max file size for uploads, in bytes (10 MB)
MAX_UPLOAD_SIZE = 10 * 1024 * 1024

# Max rows returned by /ask, to avoid huge payloads from broad questions
MAX_RESULT_ROWS = 1000


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


def is_valid_table_name(name: str) -> bool:
    """
    Validates a table name against the same pattern sanitize_table_name()
    produces. Used to guard against SQL injection when a table name is
    interpolated into a query (DuckDB doesn't support parameterized
    identifiers, only parameterized values).
    """
    return bool(re.fullmatch(r"[a-z][a-z0-9_]*", name))


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
    if not is_valid_table_name(table_name):
        raise ValueError(f"Invalid table name: {table_name}")

    conn.execute(f"""
        CREATE OR REPLACE TABLE {table_name} AS
        SELECT * FROM read_csv_auto('{file_path}')
    """)
    return table_name

def load_uploaded_excel(conn, file_path: str, table_name: str) -> str:
    """
    Loads an Excel file (.xlsx or .xls) from disk into a DuckDB table.
    Only the first sheet is loaded — multi-sheet support can be a
    future enhancement.

    Args:
        conn: an active DuckDB connection.
        file_path: path to the Excel file on disk.
        table_name: sanitized table name to create/replace.

    Returns:
        The table name that was created.
    """
    import pandas as pd

    if not is_valid_table_name(table_name):
        raise ValueError(f"Invalid table name: {table_name}")

    try:
        df = pd.read_excel(file_path, sheet_name=0)
    except Exception as e:
        raise ValueError(f"Failed to read Excel file: {e}")

    if df.empty:
        raise ValueError("Excel sheet is empty.")

    # Clean up column names the same way sanitize_table_name cleans filenames,
    # so generated SQL doesn't choke on spaces/special characters in headers.
    df.columns = [
        re.sub(r"_+", "_", re.sub(r"[^a-z0-9_]+", "_", str(c).lower().strip())).strip("_")
        or f"col_{i}"
        for i, c in enumerate(df.columns)
    ]

    conn.register("temp_excel_df", df)
    conn.execute(f"""
        CREATE OR REPLACE TABLE {table_name} AS
        SELECT * FROM temp_excel_df
    """)
    conn.unregister("temp_excel_df")
    return table_name


def list_tables(conn) -> list[str]:
    """Returns all user table names currently in the database."""
    rows = conn.execute("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'main'
        ORDER BY table_name
    """).fetchall()
    return [r[0] for r in rows]


def drop_table(conn, table_name: str) -> None:
    """Drops a table by name, after validating it's a safe identifier."""
    if not is_valid_table_name(table_name):
        raise ValueError(f"Invalid table name: {table_name}")
    conn.execute(f"DROP TABLE IF EXISTS {table_name}")


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
        if not is_valid_table_name(table_name):
            raise ValueError(f"Invalid table name: {table_name}")
        table_names = [table_name]
    else:
        table_names = list_tables(conn)

    schema_parts = []
    for name in table_names:
        columns = conn.execute("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = ?
            ORDER BY ordinal_position
        """, [name]).fetchall()
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


def init_feedback_table(conn):
    """Creates the feedback table and its id sequence if they don't exist yet."""
    conn.execute("CREATE SEQUENCE IF NOT EXISTS feedback_id_seq START 1")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS feedback (
            id BIGINT PRIMARY KEY DEFAULT nextval('feedback_id_seq'),
            question VARCHAR,
            sql VARCHAR,
            table_name VARCHAR,
            rating VARCHAR,
            created_at TIMESTAMP DEFAULT current_timestamp
        )
    """)


def insert_feedback(conn, question: str, sql: str, table_name: str, rating: str) -> None:
    """Inserts one feedback row (rating is 'up' or 'down')."""
    conn.execute("""
        INSERT INTO feedback (question, sql, table_name, rating)
        VALUES (?, ?, ?, ?)
    """, [question, sql, table_name, rating])


def get_feedback_stats(conn) -> dict:
    """Returns up/down counts and total from the feedback table."""
    rows = conn.execute("""
        SELECT rating, COUNT(*) FROM feedback GROUP BY rating
    """).fetchall()

    stats = {"up": 0, "down": 0}
    for rating, count in rows:
        if rating in stats:
            stats[rating] = count
    stats["total"] = stats["up"] + stats["down"]
    return stats
