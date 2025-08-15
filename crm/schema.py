"""
GraphQL schema for the CRM application.

This module defines all GraphQL queries, mutations, and types
related to customer relationship management functionality.
"""

import re
from datetime import datetime
from decimal import Decimal
import graphene
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from graphene_django import DjangoObjectType
from graphene_django.filter import DjangoFilterConnectionField

from .filters import CustomerFilter, ProductFilter, OrderFilter
from .models import Customer, Product, Order, OrderProduct

# -------------------
# GraphQL Types
# -------------------
class CustomerType(DjangoObjectType):
    """GraphQL type for Customer model."""
    class Meta:
        model = Customer
        interfaces = (graphene.relay.Node,)
        fields = ("id", "name", "email", "phone", "created_at", "updated_at")
        filterset_class = CustomerFilter

class ProductType(DjangoObjectType):
    """GraphQL type for Product model."""
    class Meta:
        model = Product
        interfaces = (graphene.relay.Node,)
        fields = ("id", "name", "price", "stock", "created_at", "updated_at")
        filterset_class = ProductFilter

class OrderType(DjangoObjectType):
    """GraphQL type for Order model."""
    class Meta:
        model = Order
        interfaces = (graphene.relay.Node,)
        fields = (
            "id",
            "customer",
            "products",
            "order_date",
            "total_amount",
            "created_at",
            "updated_at",
        )
        filterset_class = OrderFilter

# -------------------
# Input Types
# -------------------
class CreateCustomerInput(graphene.InputObjectType):
    """Input type for creating a customer."""
    name = graphene.String(required=True)
    email = graphene.String(required=True)
    phone = graphene.String(required=False)

class BulkCustomerInput(graphene.InputObjectType):
    """Input type for bulk customer creation."""
    name = graphene.String(required=True)
    email = graphene.String(required=True)
    phone = graphene.String(required=False)

class CreateProductInput(graphene.InputObjectType):
    """Input type for creating a product."""
    name = graphene.String(required=True)
    price = graphene.Float(required=True)  # accept float in GraphQL; convert to Decimal
    stock = graphene.Int(required=False, default_value=0)

class CreateOrderInput(graphene.InputObjectType):
    """Input type for creating an order."""
    customer_id = graphene.ID(required=True)
    product_ids = graphene.List(graphene.ID, required=True)
    order_date = graphene.DateTime(required=False)

# -------------------
# Filter Input Types
# -------------------
class CustomerFilterInput(graphene.InputObjectType):
    name_icontains = graphene.String()
    email_icontains = graphene.String()
    created_at_gte = graphene.Date()
    created_at_lte = graphene.Date()
    phone_pattern = graphene.String()

class ProductFilterInput(graphene.InputObjectType):
    name_icontains = graphene.String()
    price_gte = graphene.Decimal()
    price_lte = graphene.Decimal()
    stock_gte = graphene.Int()
    stock_lte = graphene.Int()
    low_stock = graphene.Boolean()

class OrderFilterInput(graphene.InputObjectType):
    total_amount_gte = graphene.Decimal()
    total_amount_lte = graphene.Decimal()
    order_date_gte = graphene.Date()
    order_date_lte = graphene.Date()
    customer_name = graphene.String()
    product_name = graphene.String()
    product_id = graphene.ID()

# -------------------
# Helpers / Validation
# -------------------
PHONE_RE = re.compile(r"^(\+?\d{7,15}|\d{3}-\d{3}-\d{4})$")

def validate_phone(phone: str) -> None:
    """Validate phone number format."""
    if phone and not PHONE_RE.match(phone):
        raise ValidationError("Invalid phone format. Use +1234567890 or 123-456-7890.")

def decimal_from_float(f) -> Decimal:
    """Convert float to Decimal for precise monetary calculations."""
    return Decimal(str(f))

# -------------------
# Mutations
# -------------------
class CreateCustomer(graphene.Mutation):
    """Mutation to create a single customer."""
    class Arguments:
        input = CreateCustomerInput(required=True)

    customer = graphene.Field(CustomerType)
    message = graphene.String()
    success = graphene.Boolean()
    errors = graphene.List(graphene.String)

    @staticmethod
    def mutate(root, info, input: CreateCustomerInput):
        """Create a new customer."""
        name = (input.name or "").strip()
        email = (input.email or "").strip().lower()
        phone = (input.phone or "").strip() if input.phone else None
        errors = []

        try:
            # Validate email
            validate_email(email)
            
            # Validate phone
            if phone:
                validate_phone(phone)
            
            # Check for existing email
            if Customer.objects.filter(email=email).exists():
                errors.append("Email already exists.")
            
            if errors:
                return CreateCustomer(
                    customer=None,
                    message="Validation failed",
                    success=False,
                    errors=errors
                )

            customer = Customer.objects.create(name=name, email=email, phone=phone)
            return CreateCustomer(
                customer=customer,
                message="Customer created successfully",
                success=True,
                errors=[]
            )

        except ValidationError as e:
            return CreateCustomer(
                customer=None,
                message="Validation error",
                success=False,
                errors=[str(e)]
            )
        except Exception as e:
            return CreateCustomer(
                customer=None,
                message="Failed to create customer",
                success=False,
                errors=[str(e)]
            )

class BulkCreateCustomers(graphene.Mutation):
    """Mutation to create multiple customers in bulk."""
    class Arguments:
        input = graphene.List(BulkCustomerInput, required=True)

    customers = graphene.List(CustomerType)   # successfully created
    errors = graphene.List(graphene.String)   # error messages per failed record
    success_count = graphene.Int()
    total_count = graphene.Int()

    @staticmethod
    def mutate(root, info, input):
        valid_payloads = []
        errors = []
        emails_seen = set()

        # Validate all inputs first
        for idx, item in enumerate(input):
            name = (item.name or "").strip()
            email = (item.email or "").strip().lower()
            phone = (item.phone or "").strip() if item.phone else None

            try:
                if not name:
                    raise ValidationError("Name is required.")
                
                validate_email(email)
                
                if phone:
                    validate_phone(phone)
                
                if email in emails_seen:
                    raise ValidationError(f"Duplicate email in request: {email}")
                
                if Customer.objects.filter(email=email).exists():
                    raise ValidationError(f"Email already exists: {email}")
                
                emails_seen.add(email)
                valid_payloads.append((name, email, phone))
                
            except ValidationError as e:
                errors.append(f"Item {idx + 1}: {str(e)}")

        created = []
        # Create valid records in a single transaction
        if valid_payloads:
            with transaction.atomic():
                for name, email, phone in valid_payloads:
                    created.append(Customer.objects.create(
                        name=name, 
                        email=email, 
                        phone=phone
                    ))

        return BulkCreateCustomers(
            customers=created,
            errors=errors,
            success_count=len(created),
            total_count=len(input)
        )

class CreateProduct(graphene.Mutation):
    """Mutation to create a product."""
    class Arguments:
        input = CreateProductInput(required=True)

    product = graphene.Field(ProductType)
    message = graphene.String()
    success = graphene.Boolean()
    errors = graphene.List(graphene.String)

    @staticmethod
    def mutate(root, info, input: CreateProductInput):
        """Create a new product."""
        name = (input.name or "").strip()
        errors = []

        try:
            if not name:
                errors.append("Product name is required.")

            price = decimal_from_float(input.price)
            if price <= Decimal("0"):
                errors.append("Price must be positive.")

            stock = input.stock if input.stock is not None else 0
            if stock < 0:
                errors.append("Stock cannot be negative.")

            if errors:
                return CreateProduct(
                    product=None,
                    message="Validation failed",
                    success=False,
                    errors=errors
                )

            product = Product.objects.create(
                name=name, 
                price=price, 
                stock=stock
            )
            return CreateProduct(
                product=product,
                message="Product created successfully",
                success=True,
                errors=[]
            )

        except Exception as e:
            return CreateProduct(
                product=None,
                message="Failed to create product",
                success=False,
                errors=[str(e)]
            )

class CreateOrder(graphene.Mutation):
    """Mutation to create an order with products."""
    class Arguments:
        input = CreateOrderInput(required=True)

    order = graphene.Field(OrderType)
    message = graphene.String()
    success = graphene.Boolean()
    errors = graphene.List(graphene.String)

    @staticmethod
    def mutate(root, info, input: CreateOrderInput):
        """Create a new order with associated products."""
        errors = []

        try:
            # Validate customer
            try:
                customer = Customer.objects.get(pk=input.customer_id)
            except Customer.DoesNotExist:
                errors.append("Invalid customer ID.")

            # Validate products
            if not input.product_ids or len(input.product_ids) == 0:
                errors.append("Select at least one product.")

            products = list(Product.objects.filter(pk__in=input.product_ids))
            if len(products) != len(set(input.product_ids)):
                # some ids invalid
                valid_ids = {str(p.pk) for p in products}
                bad = [pid for pid in input.product_ids if str(pid) not in valid_ids]
                errors.append(f"Invalid product ID(s): {', '.join(map(str, bad))}")

            if errors:
                return CreateOrder(
                    order=None,
                    message="Validation failed",
                    success=False,
                    errors=errors
                )

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

            return CreateOrder(
                order=order,
                message="Order created successfully",
                success=True,
                errors=[]
            )

        except Exception as e:
            return CreateOrder(
                order=None,
                message="Failed to create order",
                success=False,
                errors=[str(e)]
            )

# -------------------
# Query
# -------------------
class Query(graphene.ObjectType):
    """
    CRM GraphQL Query class.
    
    This class contains all query fields available for the CRM application.
    """
    hello = graphene.String(
        description="A simple greeting field that returns 'Hello, GraphQL!'",
        default_value="Hello, GraphQL!"
    )
    
    # Customer queries
    all_customers = DjangoFilterConnectionField(
        CustomerType,
        description="Get all customers with filtering and ordering",
        filter=graphene.Argument(CustomerFilterInput),
        order_by=graphene.String(),
    )
    customer = graphene.Field(
        CustomerType, 
        id=graphene.ID(required=True), 
        description="Get a customer by ID"
    )
    
    # Product queries
    all_products = DjangoFilterConnectionField(
        ProductType,
        description="Get all products with filtering and ordering",
        filter=graphene.Argument(ProductFilterInput),
        order_by=graphene.String(),
    )
    product = graphene.Field(
        ProductType, 
        id=graphene.ID(required=True), 
        description="Get a product by ID"
    )
    
    # Order queries
    all_orders = DjangoFilterConnectionField(
        OrderType,
        description="Get all orders with filtering and ordering",
        filter=graphene.Argument(OrderFilterInput),
        order_by=graphene.String(),
    )
    order = graphene.Field(
        OrderType, 
        id=graphene.ID(required=True), 
        description="Get an order by ID"
    )

    def resolve_all_customers(self, info, filter=None, order_by=None, **kwargs):
        qs = Customer.objects.all()
        if filter:
            f = {}
            if getattr(filter, "name_icontains", None):
                f["name__icontains"] = filter.name_icontains
            if getattr(filter, "email_icontains", None):
                f["email__icontains"] = filter.email_icontains
            if getattr(filter, "created_at_gte", None):
                f["created_at__gte"] = filter.created_at_gte
            if getattr(filter, "created_at_lte", None):
                f["created_at__lte"] = filter.created_at_lte
            if getattr(filter, "phone_pattern", None):
                val = filter.phone_pattern
                if val.startswith("+"):
                    f["phone__startswith"] = val
                else:
                    f["phone__icontains"] = val
            qs = qs.filter(**f)
        if order_by:
            parts = [p.strip() for p in order_by.split(",") if p.strip()]
            qs = qs.order_by(*parts)
        return qs

    def resolve_customer(self, info, id):
        try:
            return Customer.objects.get(id=id)
        except Customer.DoesNotExist:
            return None

    def resolve_all_products(self, info, filter=None, order_by=None, **kwargs):
        qs = Product.objects.all()
        if filter:
            f = {}
            if getattr(filter, "name_icontains", None):
                f["name__icontains"] = filter.name_icontains
            if getattr(filter, "price_gte", None):
                f["price__gte"] = filter.price_gte
            if getattr(filter, "price_lte", None):
                f["price__lte"] = filter.price_lte
            if getattr(filter, "stock_gte", None):
                f["stock__gte"] = filter.stock_gte
            if getattr(filter, "stock_lte", None):
                f["stock__lte"] = filter.stock_lte
            qs = qs.filter(**f)
            if getattr(filter, "low_stock", None):
                qs = qs.filter(stock__lt=10)
        if order_by:
            parts = [p.strip() for p in order_by.split(",") if p.strip()]
            qs = qs.order_by(*parts)
        return qs

    def resolve_product(self, info, id):
        try:
            return Product.objects.get(id=id)
        except Product.DoesNotExist:
            return None

    def resolve_all_orders(self, info, filter=None, order_by=None, **kwargs):
        qs = Order.objects.select_related("customer").prefetch_related("products").all()
        if filter:
            f = {}
            if getattr(filter, "total_amount_gte", None):
                f["total_amount__gte"] = filter.total_amount_gte
            if getattr(filter, "total_amount_lte", None):
                f["total_amount__lte"] = filter.total_amount_lte
            if getattr(filter, "order_date_gte", None):
                f["order_date__gte"] = filter.order_date_gte
            if getattr(filter, "order_date_lte", None):
                f["order_date__lte"] = filter.order_date_lte
            if getattr(filter, "customer_name", None):
                f["customer__name__icontains"] = filter.customer_name
            if getattr(filter, "product_name", None):
                f["products__name__icontains"] = filter.product_name
            if getattr(filter, "product_id", None):
                f["products__id"] = int(filter.product_id)
            qs = qs.filter(**f)
            if any(k in f for k in ("products__name__icontains", "products__id")):
                qs = qs.distinct()
        if order_by:
            parts = [p.strip() for p in order_by.split(",") if p.strip()]
            qs = qs.order_by(*parts)
        return qs

    def resolve_order(self, info, id):
        try:
            return (
                Order.objects.select_related("customer")
                .prefetch_related("products")
                .get(id=id)
            )
        except Order.DoesNotExist:
            return None

# -------------------
# Root Mutation
# -------------------
class Mutation(graphene.ObjectType):
    """
    CRM GraphQL Mutation class.
    
    This class contains all mutation fields available for the CRM application.
    """
    create_customer = CreateCustomer.Field()
    bulk_create_customers = BulkCreateCustomers.Field()
    create_product = CreateProduct.Field()
    create_order = CreateOrder.Field()

# Create the schema
schema = graphene.Schema(query=Query, mutation=Mutation)
