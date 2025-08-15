import re
from decimal import Decimal
import graphene
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from graphene_django import DjangoObjectType
from graphene_django.filter import DjangoFilterConnectionField

from .filters import CustomerFilter, ProductFilter, OrderFilter
from .models import Customer, Product, Order

# -------------------
# Helpers
# -------------------
PHONE_RE = re.compile(r"^(\+?\d{7,15}|\d{3}-\d{3}-\d{4})$")

def validate_phone(phone: str) -> None:
    if phone and not PHONE_RE.match(phone):
        raise ValidationError("Invalid phone format. Use +1234567890 or 123-456-7890.")

def decimal_from_float(f) -> Decimal:
    return Decimal(str(f))


# -------------------
# GraphQL Types
# -------------------
class CustomerType(DjangoObjectType):
    class Meta:
        model = Customer
        fields = ("id", "name", "email", "phone")
        filterset_class = CustomerFilter


class ProductType(DjangoObjectType):
    class Meta:
        model = Product
        fields = ("id", "name", "price", "stock")
        filterset_class = ProductFilter


class OrderType(DjangoObjectType):
    class Meta:
        model = Order
        fields = ("id", "customer", "products", "total_amount", "order_date")
        filterset_class = OrderFilter


# -------------------
# Input Types
# -------------------
class CreateCustomerInput(graphene.InputObjectType):
    name = graphene.String(required=True)
    email = graphene.String(required=True)
    phone = graphene.String(required=False)

class BulkCustomerInput(graphene.InputObjectType):
    name = graphene.String(required=True)
    email = graphene.String(required=True)
    phone = graphene.String(required=False)

class CreateProductInput(graphene.InputObjectType):
    name = graphene.String(required=True)
    price = graphene.Float(required=True)  # GraphQL float, converted to Decimal
    stock = graphene.Int(required=False, default_value=0)

class CreateOrderInput(graphene.InputObjectType):
    customer_id = graphene.ID(required=True)
    product_ids = graphene.List(graphene.ID, required=True)
    order_date = graphene.DateTime(required=False)


# -------------------
# Mutations
# -------------------
class CreateCustomer(graphene.Mutation):
    class Arguments:
        input = CreateCustomerInput(required=True)

    customer = graphene.Field(CustomerType)
    message = graphene.String()

    @staticmethod
    def mutate(root, info, input: CreateCustomerInput):
        name = (input.name or "").strip()
        email = (input.email or "").strip().lower()
        phone = (input.phone or "").strip() if input.phone else None

        # validations
        try:
            if not name:
                raise ValidationError("Name is required.")
            validate_email(email)
            validate_phone(phone)
        except ValidationError as e:
            raise graphene.GraphQLError(str(e))

        if Customer.objects.filter(email=email).exists():
            raise graphene.GraphQLError("Email already exists.")

        customer = Customer.objects.create(name=name, email=email, phone=phone)
        return CreateCustomer(customer=customer, message="Customer created successfully.")


class BulkCreateCustomers(graphene.Mutation):
    class Arguments:
        input = graphene.List(BulkCustomerInput, required=True)

    customers = graphene.List(CustomerType)
    errors = graphene.List(graphene.String)

    @staticmethod
    def mutate(root, info, input):
        valid_payloads = []
        errors = []
        emails_seen = set()

        for idx, item in enumerate(input):
            name = (item.name or "").strip()
            email = (item.email or "").strip().lower()
            phone = (item.phone or "").strip() if item.phone else None

            try:
                if not name:
                    raise ValidationError("Name is required.")
                validate_email(email)
                validate_phone(phone)
                if email in emails_seen:
                    raise ValidationError(f"Duplicate email in request: {email}")
                if Customer.objects.filter(email=email).exists():
                    raise ValidationError(f"Email already exists: {email}")
                emails_seen.add(email)
                valid_payloads.append((name, email, phone))
            except ValidationError as e:
                errors.append(f"Item {idx}: {str(e)}")

        created = []
        if valid_payloads:
            with transaction.atomic():
                for name, email, phone in valid_payloads:
                    created.append(Customer.objects.create(name=name, email=email, phone=phone))

        return BulkCreateCustomers(customers=created, errors=errors)


class CreateProduct(graphene.Mutation):
    class Arguments:
        input = CreateProductInput(required=True)

    product = graphene.Field(ProductType)

    @staticmethod
    def mutate(root, info, input: CreateProductInput):
        name = (input.name or "").strip()
        if not name:
            raise graphene.GraphQLError("Product name is required.")

        price = decimal_from_float(input.price)
        if price <= Decimal("0"):
            raise graphene.GraphQLError("Price must be positive.")

        stock = input.stock if input.stock is not None else 0
        if stock < 0:
            raise graphene.GraphQLError("Stock cannot be negative.")

        product = Product.objects.create(name=name, price=price, stock=stock)
        return CreateProduct(product=product)


class CreateOrder(graphene.Mutation):
    class Arguments:
        input = CreateOrderInput(required=True)

    order = graphene.Field(OrderType)

    @staticmethod
    def mutate(root, info, input: CreateOrderInput):
        # Validate customer
        try:
            customer = Customer.objects.get(pk=input.customer_id)
        except Customer.DoesNotExist:
            raise graphene.GraphQLError("Invalid customer ID.")

        # Validate products
        if not input.product_ids:
            raise graphene.GraphQLError("Select at least one product.")

        products = list(Product.objects.filter(pk__in=input.product_ids))
        if len(products) != len(set(input.product_ids)):
            valid_ids = {str(p.pk) for p in products}
            bad = [pid for pid in input.product_ids if str(pid) not in valid_ids]
            raise graphene.GraphQLError(f"Invalid product ID(s): {', '.join(map(str, bad))}")

        with transaction.atomic():
            order = Order.objects.create(
                customer=customer,
                order_date=input.order_date or timezone.now(),
                total_amount=Decimal("0.00"),
            )
            order.products.set(products)
            total = sum((p.price for p in products), Decimal("0.00"))
            order.total_amount = total
            order.save(update_fields=["total_amount"])

        return CreateOrder(order=order)


# -------------------
# Query (with filtering & ordering)
# -------------------
class Query(graphene.ObjectType):
    hello = graphene.String(default_value="Hello, GraphQL!")
    all_customers = DjangoFilterConnectionField(
        CustomerType, filterset_class=CustomerFilter, order_by=graphene.List(of_type=graphene.String)
    )
    all_products = DjangoFilterConnectionField(
        ProductType, filterset_class=ProductFilter, order_by=graphene.List(of_type=graphene.String)
    )
    all_orders = DjangoFilterConnectionField(
        OrderType, filterset_class=OrderFilter, order_by=graphene.List(of_type=graphene.String)
    )

    def resolve_all_customers(self, info, order_by=None, **kwargs):
        qs = Customer.objects.all()
        if order_by:
            qs = qs.order_by(*order_by)
        return qs

    def resolve_all_products(self, info, order_by=None, **kwargs):
        qs = Product.objects.all()
        if order_by:
            qs = qs.order_by(*order_by)
        return qs

    def resolve_all_orders(self, info, order_by=None, **kwargs):
        qs = Order.objects.all()
        if order_by:
            qs = qs.order_by(*order_by)
        return qs


# -------------------
# Root Mutation
# -------------------
class Mutation(graphene.ObjectType):
    create_customer = CreateCustomer.Field()
    bulk_create_customers = BulkCreateCustomers.Field()
    create_product = CreateProduct.Field()
    create_order = CreateOrder.Field()
