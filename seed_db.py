import os
import django
from django.utils import timezone
from random import choice, randint

# Setup Django environment
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "alx_backend_graphql_crm.settings")
django.setup()

from crm.models import Customer, Product, Order

def seed_customers():
    customers_data = [
        {"name": "Alice Johnson", "email": "alice@example.com", "phone": "+1234567890"},
        {"name": "Bob Smith", "email": "bob@example.com", "phone": "123-456-7890"},
        {"name": "Carol White", "email": "carol@example.com", "phone": None},
        {"name": "David Brown", "email": "david@example.com", "phone": "+1987654321"},
    ]

    created = []
    for data in customers_data:
        customer, _ = Customer.objects.get_or_create(**data)
        created.append(customer)
    print(f"✅ Seeded {len(created)} customers.")
    return created


def seed_products():
    products_data = [
        {"name": "Laptop", "price": 999.99, "stock": 10},
        {"name": "Smartphone", "price": 699.99, "stock": 15},
        {"name": "Tablet", "price": 399.99, "stock": 8},
        {"name": "Monitor", "price": 199.99, "stock": 5},
        {"name": "Headphones", "price": 89.99, "stock": 20},
    ]

    created = []
    for data in products_data:
        product, _ = Product.objects.get_or_create(**data)
        created.append(product)
    print(f"✅ Seeded {len(created)} products.")
    return created


def seed_orders(customers, products):
    orders_data = [
        {
            "customer": choice(customers),
            "products": [choice(products) for _ in range(randint(1, 3))],
            "order_date": timezone.now()
        }
        for _ in range(5)
    ]

    for data in orders_data:
        total_amount = sum([p.price for p in data["products"]])
        order = Order.objects.create(
            customer=data["customer"],
            total_amount=total_amount,
            order_date=data["order_date"]
        )
        order.products.set(data["products"])
    print(f"✅ Seeded {len(orders_data)} orders.")


if __name__ == "__main__":
    print("📦 Starting database seeding...")
    customers = seed_customers()
    products = seed_products()
    seed_orders(customers, products)
    print("🎉 Seeding complete!")
