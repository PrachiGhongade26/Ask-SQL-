# app/sql_dialects.py

DIALECT_RULES = {
    "duckdb": "Use DuckDB SQL syntax. Use standard functions like DATE_TRUNC(), || for string concat.",
    "postgres": "Use PostgreSQL syntax: double-quoted identifiers if needed, DATE_TRUNC() for date grouping, || for string concatenation, LIMIT n for row limits.",
    "mysql": "Use MySQL syntax: backtick identifiers, DATE_FORMAT() for date formatting, CONCAT() for string concatenation, LIMIT n for row limits.",
    "bigquery": "Use BigQuery Standard SQL syntax: backtick-quoted table references, TIMESTAMP_TRUNC() for date/time grouping, CONCAT() for string concatenation, LIMIT n, no trailing semicolon."
}

SUPPORTED_DIALECTS = list(DIALECT_RULES.keys())


def get_dialect_instruction(dialect: str) -> str:
    """Return the syntax instruction block for a given dialect, defaulting to duckdb."""
    return DIALECT_RULES.get(dialect, DIALECT_RULES["duckdb"])


def validate_dialect(dialect: str) -> str:
    """Validate and normalize the dialect string."""
    d = dialect.lower().strip()
    if d not in SUPPORTED_DIALECTS:
        raise ValueError(f"Unsupported dialect '{dialect}'. Supported: {SUPPORTED_DIALECTS}")
    return d