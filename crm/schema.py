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
from .types import CustomerType, ProductType, OrderType
from .models import Customer, Product, Order

# -------------------
# GraphQL Types
# -------------------
class CustomerType(DjangoObjectType):
    class Meta:
        model = Customer
        fields = ("id", "name", "email", "phone")

class ProductType(DjangoObjectType):
    class Meta:
        model = Product
        fields = ("id", "name", "price", "stock")

class OrderType(DjangoObjectType):
    class Meta:
        model = Order
        fields = ("id", "customer", "products", "total_amount", "order_date")


# -------------------
# Inputs
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
    price = graphene.Float(required=True)  # accept float in GraphQL; convert to Decimal
    stock = graphene.Int(required=False, default_value=0)

class CreateOrderInput(graphene.InputObjectType):
    customer_id = graphene.ID(required=True)
    product_ids = graphene.List(graphene.ID, required=True)
    order_date = graphene.DateTime(required=False)


# -------------------
# Helpers / Validation
# -------------------
PHONE_RE = re.compile(r"^(\+?\d{7,15}|\d{3}-\d{3}-\d{4})$")

def validate_phone(phone: str) -> None:
    if phone and not PHONE_RE.match(phone):
        raise ValidationError("Invalid phone format. Use +1234567890 or 123-456-7890.")

def decimal_from_float(f) -> Decimal:
    return Decimal(str(f))


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

    customers = graphene.List(CustomerType)   # successfully created
    errors = graphene.List(graphene.String)   # error messages per failed record

    @staticmethod
    def mutate(root, info, input):
        valid_payloads = []
        errors = []

        # 1) validate all
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
        # 2) create all valid in a single transaction (partial success supported)
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
        if not input.product_ids or len(input.product_ids) == 0:
            raise graphene.GraphQLError("Select at least one product.")

        products = list(Product.objects.filter(pk__in=input.product_ids))
        if len(products) != len(set(input.product_ids)):
            # some ids invalid
            valid_ids = {str(p.pk) for p in products}
            bad = [pid for pid in input.product_ids if str(pid) not in valid_ids]
            raise graphene.GraphQLError(f"Invalid product ID(s): {', '.join(map(str, bad))}")

        # Create order and compute total
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
# Query (basic)
# -------------------
class Query(graphene.ObjectType):
    hello = graphene.String(default_value="Hello, GraphQL!")
    customers = graphene.List(CustomerType)
    products = graphene.List(ProductType)
    orders = graphene.List(OrderType)

    def resolve_customers(root, info):
        return Customer.objects.all()

    def resolve_products(root, info):
        return Product.objects.all()

    def resolve_orders(root, info):
        return Order.objects.select_related("customer").prefetch_related("products")


# -------------------
# Root Mutation
# -------------------
class Mutation(graphene.ObjectType):
    create_customer = CreateCustomer.Field()
    bulk_create_customers = BulkCreateCustomers.Field()
    create_product = CreateProduct.Field()
    create_order = CreateOrder.Field()


# GraphQL Types
class CustomerType(DjangoObjectType):
    class Meta:
        model = Customer

class ProductType(DjangoObjectType):
    class Meta:
        model = Product

class OrderType(DjangoObjectType):
    class Meta:
        model = Order

# Input Types
class CustomerInput(graphene.InputObjectType):
    name = graphene.String(required=True)
    email = graphene.String(required=True)
    phone = graphene.String(required=False)

class ProductInput(graphene.InputObjectType):
    name = graphene.String(required=True)
    price = graphene.Float(required=True)
    stock = graphene.Int(required=False)

class OrderInput(graphene.InputObjectType):
    customer_id = graphene.ID(required=True)
    product_ids = graphene.List(graphene.ID, required=True)
    order_date = graphene.DateTime(required=False)

class CreateCustomer(graphene.Mutation):
    class Arguments:
        input = CustomerInput(required=True)

    customer = graphene.Field(CustomerType)
    message = graphene.String()

    def mutate(self, info, input):
        # Email validation
        if Customer.objects.filter(email=input.email).exists():
            raise ValidationError("Email already exists")

        # Phone validation
        if input.phone and not re.match(r'^(\+\d{10,15}|\d{3}-\d{3}-\d{4})$', input.phone):
            raise ValidationError("Invalid phone format")

        customer = Customer.objects.create(
            name=input.name,
            email=input.email,
            phone=input.phone
        )

        return CreateCustomer(customer=customer, message="Customer created successfully")

class BulkCreateCustomers(graphene.Mutation):
    class Arguments:
        input = graphene.List(CustomerInput, required=True)

    customers = graphene.List(CustomerType)
    errors = graphene.List(graphene.String)

    @transaction.atomic
    def mutate(self, info, input):
        created_customers = []
        errors = []

        for data in input:
            try:
                if Customer.objects.filter(email=data.email).exists():
                    raise ValidationError(f"Email already exists: {data.email}")
                if data.phone and not re.match(r'^(\+\d{10,15}|\d{3}-\d{3}-\d{4})$', data.phone):
                    raise ValidationError(f"Invalid phone format: {data.phone}")

                customer = Customer.objects.create(
                    name=data.name,
                    email=data.email,
                    phone=data.phone
                )
                created_customers.append(customer)
            except ValidationError as e:
                errors.append(str(e))

        return BulkCreateCustomers(customers=created_customers, errors=errors)

class CreateProduct(graphene.Mutation):
    class Arguments:
        input = ProductInput(required=True)

    product = graphene.Field(ProductType)

    def mutate(self, info, input):
        if input.price <= 0:
            raise ValidationError("Price must be positive")
        if input.stock is not None and input.stock < 0:
            raise ValidationError("Stock cannot be negative")

        product = Product.objects.create(
            name=input.name,
            price=input.price,
            stock=input.stock or 0
        )

        return CreateProduct(product=product)

class CreateOrder(graphene.Mutation):
    class Arguments:
        input = OrderInput(required=True)

    order = graphene.Field(OrderType)

    def mutate(self, info, input):
        try:
            customer = Customer.objects.get(pk=input.customer_id)
        except Customer.DoesNotExist:
            raise ValidationError("Invalid customer ID")

        products = Product.objects.filter(pk__in=input.product_ids)
        if not products.exists():
            raise ValidationError("No valid products found")

        total_amount = sum([p.price for p in products])

        order = Order.objects.create(
            customer=customer,
            total_amount=total_amount,
            order_date=input.order_date or timezone.now()
        )
        order.products.set(products)

        return CreateOrder(order=order)

class Mutation(graphene.ObjectType):
    create_customer = CreateCustomer.Field()
    bulk_create_customers = BulkCreateCustomers.Field()
    create_product = CreateProduct.Field()
    create_order = CreateOrder.Field()


class Query(graphene.ObjectType):
    all_customers = DjangoFilterConnectionField(CustomerType, filterset_class=CustomerFilter, order_by=graphene.List(of_type=graphene.String))
    all_products = DjangoFilterConnectionField(ProductType, filterset_class=ProductFilter, order_by=graphene.List(of_type=graphene.String))
    all_orders = DjangoFilterConnectionField(OrderType, filterset_class=OrderFilter, order_by=graphene.List(of_type=graphene.String))

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