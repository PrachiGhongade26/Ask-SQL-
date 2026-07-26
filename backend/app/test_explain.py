"""
Manual/documented tests for the /explain endpoint.
Run the server separately (uvicorn app.main:app --reload), then run this file.
"""
import requests

BASE_URL = "http://127.0.0.1:8000"


def test_explain_clear_question():
    """A clear, unambiguous question should return sql, plan, and commentary."""
    resp = requests.post(f"{BASE_URL}/explain", json={
        "table_name": "sales_sample",
        "question": "What is the total sales amount by region?"
    })
    data = resp.json()
    assert resp.status_code == 200
    assert data["sql"] is not None
    assert "GROUP BY" in data["sql"].upper()
    assert data["plan"] is not None
    assert data["commentary"] is not None
    print("PASS: clear question returns sql, plan, commentary")


def test_explain_ambiguous_question():
    """An ambiguous question should return a clarifying_question, not SQL."""
    resp = requests.post(f"{BASE_URL}/explain", json={
        "table_name": "sales_sample",
        "question": "show me the best region"
    })
    data = resp.json()
    assert resp.status_code == 200
    assert data["sql"] is None
    assert data["plan"] is None
    assert data["commentary"] is None
    assert data["clarifying_question"] is not None
    print("PASS: ambiguous question returns clarifying_question, no SQL")


def test_explain_invalid_table():
    """A nonexistent table should return 404."""
    resp = requests.post(f"{BASE_URL}/explain", json={
        "table_name": "not_a_real_table",
        "question": "count everything"
    })
    assert resp.status_code == 404
    print("PASS: invalid table returns 404")


if __name__ == "__main__":
    test_explain_clear_question()
    test_explain_ambiguous_question()
    test_explain_invalid_table()
    print("\nAll /explain tests passed.")