import io
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

SAMPLE_CSV = """order_id,customer_id,order_date,category,amount
1,101,2026-01-15,Electronics,250.00
2,102,2026-02-20,Clothing,80.00
3,101,2026-03-05,Electronics,120.00
4,103,2026-01-28,Home,60.00
5,102,2026-04-10,Clothing,45.00
"""


def upload_sample_table():
    """Uploads a small synthetic CSV and returns the table name it was loaded as."""
    file_bytes = io.BytesIO(SAMPLE_CSV.encode("utf-8"))
    response = client.post(
        "/upload",
        files={"file": ("test_orders.csv", file_bytes, "text/csv")},
    )
    assert response.status_code == 200, response.text
    return response.json()["table_name"]


def test_count_query():
    table_name = upload_sample_table()
    response = client.post("/ask", json={
        "table_name": table_name,
        "question": "How many orders were placed in total?"
    })
    assert response.status_code == 200, response.text
    assert response.json()["sql"] is not None


def test_group_by_query():
    table_name = upload_sample_table()
    response = client.post("/ask", json={
        "table_name": table_name,
        "question": "What is total sales amount by category?"
    })
    assert response.status_code == 200, response.text
    assert response.json()["sql"] is not None


def test_date_range_query():
    table_name = upload_sample_table()
    response = client.post("/ask", json={
        "table_name": table_name,
        "question": "Show orders placed between January and March 2026"
    })
    assert response.status_code == 200, response.text
    assert response.json()["sql"] is not None