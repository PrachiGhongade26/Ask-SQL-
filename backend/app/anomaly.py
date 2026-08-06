"""
Anomaly detection for AskSQL query results.

Runs a simple IQR (interquartile range) check on numeric columns
in a result set and flags rows/values that fall outside the
expected range. No ML model needed -- just basic stats.
"""

from typing import Any


def _is_numeric(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def detect_anomalies(results: list[dict], label_column: str | None = None) -> list[dict]:
    """
    Given a list of row dicts (as returned by /ask), check each numeric
    column for IQR-based outliers.

    Args:
        results: list of row dicts, e.g. [{"month": "March", "revenue": 50000}, ...]
        label_column: optional column name to use when describing an anomaly
                       (e.g. "month" or "product_name"). If not given, the
                       function tries to guess a non-numeric column.

    Returns:
        A list of anomaly notes, e.g.:
        [{"column": "revenue", "row_label": "March", "value": 50000,
          "message": "revenue for March (50000) is unusually high compared to other rows."}]
    """
    if not results or len(results) < 4:
        # Not enough data points for IQR to be meaningful
        return []

    columns = list(results[0].keys())
    numeric_columns = [
        col for col in columns
        if all(_is_numeric(row.get(col)) for row in results)
    ]

    if not numeric_columns:
        return []

    # Guess a label column if not provided: first non-numeric column
    if label_column is None:
        non_numeric = [c for c in columns if c not in numeric_columns]
        label_column = non_numeric[0] if non_numeric else None

    anomalies = []

    for col in numeric_columns:
        values = sorted(row[col] for row in results)
        n = len(values)

        q1 = values[n // 4]
        q3 = values[(3 * n) // 4]
        iqr = q3 - q1

        if iqr == 0:
            continue  # no spread, nothing to flag

        lower_bound = q1 - 1.5 * iqr
        upper_bound = q3 + 1.5 * iqr

        for row in results:
            val = row[col]
            if val < lower_bound or val > upper_bound:
                direction = "high" if val > upper_bound else "low"
                label = row.get(label_column, "") if label_column else ""
                label_part = f" for {label}" if label else ""

                anomalies.append({
                    "column": col,
                    "row_label": label,
                    "value": val,
                    "message": f"{col}{label_part} ({val}) is unusually {direction} compared to other rows."
                })

    return anomalies