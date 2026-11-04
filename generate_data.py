"""Regenerate the fictional retail CSV using the standard library."""

import csv
from pathlib import Path
from random import Random

DATA_PATH = Path(__file__).resolve().parent / "data" / "sales.csv"
CATALOG = [
    ("Desk Lamp", "Home", "24.50"),
    ("Throw Pillow", "Home", "18.00"),
    ("Travel Mug", "Kitchen", "15.75"),
    ("Cutting Board", "Kitchen", "22.00"),
    ("Notebook", "Stationery", "6.25"),
    ("Gel Pen Set", "Stationery", "9.50"),
    ("USB Cable", "Electronics", "12.00"),
    ("Wireless Mouse", "Electronics", "32.50"),
]


def generate_sales(path=DATA_PATH):
    """Write 240 orders over six months using a fixed seed."""
    random = Random(42)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow(["date", "order_id", "product", "category", "quantity", "unit_price"])
        for index in range(240):
            month = index // 40 + 1
            day = index % 40 * 28 // 40 + 1
            product, category, price = random.choice(CATALOG)
            quantity = random.randint(1, 5)
            writer.writerow([
                f"2025-{month:02d}-{day:02d}", f"ORD-{index + 1:04d}",
                product, category, quantity, price,
            ])


if __name__ == "__main__":
    generate_sales()
