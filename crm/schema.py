import graphene
from graphene_django import DjangoObjectType
from django.db import transaction
from django.core.exceptions import ValidationError
from .models import Customer, Product, Order
from decimal import Decimal

# -------------------
# Helper functions
# -------------------

def validate_phone(phone):
    """Ensure phone is digits only and 7–15 characters."""
    if not phone.isdigit():
        raise ValidationError("Phone number must contain only digits.")
    if not (7 <= len(phone) <= 15):
        raise ValidationError("Phone number must be between 7 and 15 digits.")

def decimal_from_float(value):
    """Convert float to Decimal safely."""
    try:
        return Decimal(str(value))
    except (ValueError, TypeError):
        raise ValidationError("Invalid decimal value.")

# -------------------
# GraphQL Types
# -------------------

class CustomerType(DjangoObjectType):
    class Meta:
        model = Customer
        fields = ("id", "name", "email", "phone", "address", "created_at")

class ProductType(DjangoObjectType):
    class Meta:
        model = Product
        fields = ("id", "name", "description", "price", "stock", "created_at")

class OrderType(DjangoObjectType):
    class Meta:
        model = Order
        fields = ("id", "customer", "product", "quantity", "total_price", "created_at")

# -------------------
# Mutations
# -------------------

class CreateCustomer(graphene.Mutation):
    customer = graphene.Field(CustomerType)

    class Arguments:
        name = graphene.String(required=True)
        email = graphene.String(required=True)
        phone = graphene.String(required=True)
        address = graphene.String(required=True)

    @transaction.atomic
    def mutate(self, info, name, email, phone, address):
        validate_phone(phone)
        if Customer.objects.filter(email=email).exists():
            raise ValidationError("Email is already registered.")

        customer = Customer.objects.create(
            name=name,
            email=email,
            phone=phone,
            address=address
        )
        return CreateCustomer(customer=customer)

class CreateProduct(graphene.Mutation):
    product = graphene.Field(ProductType)

    class Arguments:
        name = graphene.String(required=True)
        description = graphene.String()
        price = graphene.Float(required=True)
        stock = graphene.Int(required=True)

    @transaction.atomic
    def mutate(self, info, name, description, price, stock):
        if price <= 0:
            raise ValidationError("Price must be greater than zero.")
        if stock < 0:
            raise ValidationError("Stock cannot be negative.")

        product = Product.objects.create(
            name=name,
            description=description or "",
            price=decimal_from_float(price),
            stock=stock
        )
        return CreateProduct(product=product)

class CreateOrder(graphene.Mutation):
    order = graphene.Field(OrderType)

    class Arguments:
        customer_id = graphene.Int(required=True)
        product_id = graphene.Int(required=True)
        quantity = graphene.Int(required=True)

    @transaction.atomic
    def mutate(self, info, customer_id, product_id, quantity):
        if quantity <= 0:
            raise ValidationError("Quantity must be greater than zero.")

        try:
            customer = Customer.objects.get(id=customer_id)
        except Customer.DoesNotExist:
            raise ValidationError("Customer not found.")

        try:
            product = Product.objects.get(id=product_id)
        except Product.DoesNotExist:
            raise ValidationError("Product not found.")

        if product.stock < quantity:
            raise ValidationError("Not enough stock available.")

        total_price = product.price * quantity

        order = Order.objects.create(
            customer=customer,
            product=product,
            quantity=quantity,
            total_price=total_price
        )

        product.stock -= quantity
        product.save()

        return CreateOrder(order=order)

# -------------------
# Queries
# -------------------

class Query(graphene.ObjectType):
    customers = graphene.List(
        CustomerType,
        search=graphene.String(),
        order_by=graphene.String()
    )
    products = graphene.List(
        ProductType,
        search=graphene.String(),
        order_by=graphene.String()
    )
    orders = graphene.List(
        OrderType,
        customer_id=graphene.Int(),
        product_id=graphene.Int(),
        order_by=graphene.String()
    )

    def resolve_customers(self, info, search=None, order_by=None):
        qs = Customer.objects.all()
        if search:
            qs = qs.filter(name__icontains=search)
        if order_by:
            qs = qs.order_by(order_by)
        return qs

    def resolve_products(self, info, search=None, order_by=None):
        qs = Product.objects.all()
        if search:
            qs = qs.filter(name__icontains=search)
        if order_by:
            qs = qs.order_by(order_by)
        return qs

    def resolve_orders(self, info, customer_id=None, product_id=None, order_by=None):
        qs = Order.objects.all()
        if customer_id:
            qs = qs.filter(customer__id=customer_id)
        if product_id:
            qs = qs.filter(product__id=product_id)
        if order_by:
            qs = qs.order_by(order_by)
        return qs

# -------------------
# Root Schema
# -------------------

class Mutation(graphene.ObjectType):
    create_customer = CreateCustomer.Field()
    create_product = CreateProduct.Field()
    create_order = CreateOrder.Field()

schema = graphene.Schema(query=Query, mutation=Mutation)
