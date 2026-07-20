"""
Generates synthetic e-commerce data for AskSQL project.
Creates 4 CSV files: customers, products, orders, order_items.
"""
import csv
import random
from datetime import datetime, timedelta
from faker import Faker

fake = Faker("en_IN")  # Indian names, cities
random.seed(42)

NUM_CUSTOMERS = 200
NUM_PRODUCTS = 50
NUM_ORDERS = 800

CATEGORIES = ["Electronics", "Clothing", "Home & Kitchen", "Books", "Sports", "Beauty"]
STATUSES = ["delivered", "shipped", "cancelled", "returned"]

# ---------- Customers ----------
customers = []
for i in range(1, NUM_CUSTOMERS + 1):
    signup_date = fake.date_between(start_date="-2y", end_date="-30d")
    customers.append({
        "customer_id": i,
        "name": fake.name(),
        "city": fake.city(),
        "state": fake.state(),
        "signup_date": signup_date
    })

# ---------- Products ----------
products = []
for i in range(1, NUM_PRODUCTS + 1):
    products.append({
        "product_id": i,
        "product_name": fake.word().capitalize() + " " + random.choice(["Pro", "Max", "Lite", "Plus", ""]).strip(),
        "category": random.choice(CATEGORIES),
        "price": round(random.uniform(150, 15000), 2)
    })

# ---------- Orders + Order Items ----------
orders = []
order_items = []
order_item_id = 1

for order_id in range(1, NUM_ORDERS + 1):
    customer_id = random.randint(1, NUM_CUSTOMERS)
    order_date = fake.date_between(start_date="-1y", end_date="today")
    status = random.choices(STATUSES, weights=[70, 15, 10, 5])[0]

    orders.append({
        "order_id": order_id,
        "customer_id": customer_id,
        "order_date": order_date,
        "status": status
    })

    # Each order has 1-4 items
    num_items = random.randint(1, 4)
    chosen_products = random.sample(range(1, NUM_PRODUCTS + 1), num_items)
    for product_id in chosen_products:
        product_price = products[product_id - 1]["price"]
        order_items.append({
            "order_item_id": order_item_id,
            "order_id": order_id,
            "product_id": product_id,
            "quantity": random.randint(1, 3),
            "unit_price": product_price
        })
        order_item_id += 1

# ---------- Write CSVs ----------
def write_csv(filename, rows, fieldnames):
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

write_csv("data/customers.csv", customers, ["customer_id", "name", "city", "state", "signup_date"])
write_csv("data/products.csv", products, ["product_id", "product_name", "category", "price"])
write_csv("data/orders.csv", orders, ["order_id", "customer_id", "order_date", "status"])
write_csv("data/order_items.csv", order_items, ["order_item_id", "order_id", "product_id", "quantity", "unit_price"])

print("Done! Generated:")
print(f"  {len(customers)} customers")
print(f"  {len(products)} products")
print(f"  {len(orders)} orders")
print(f"  {len(order_items)} order items")