from django.conf import settings
from rest_framework import generics

from rest_framework.response import Response
from rest_framework import status
from django.db import transaction

from nxtbn.core import CurrencyTypes
from nxtbn.core.utils import apply_exchange_rate, build_currency_amount
from nxtbn.discount import PromoCodeType
from nxtbn.discount.models import PromoCode
from nxtbn.order import AddressType, OrderAuthorizationStatus, OrderChargeStatus, OrderStatus
from nxtbn.order.proccesor.serializers import OrderEstimateSerializer
from nxtbn.order.models import Address, Order, OrderDeviceMeta, OrderLineItem
from nxtbn.product.models import Product, ProductVariant
from decimal import Decimal, InvalidOperation

from nxtbn.shipping.models import ShippingRate
from nxtbn.tax.models import TaxRate

from django.db.models import Q
from rest_framework import serializers
from nxtbn.core.currency.backend import currency_Backend

from nxtbn.core.signal_initiators import order_created
from nxtbn.users import UserRole

from nxtbn.order.utils import parse_user_agent, validate_variant_with_stocks
from nxtbn.warehouse.tasks import handle_stock_reserve

def get_shipping_rate_instance(shipping_method_id, address, total_weight):
        if not shipping_method_id:
            return None

        if not address:
            raise ValueError("Address is required when a shipping method ID is provided.")
        
        if not total_weight:
            raise ValueError("Total weight is required to calculate shipping rate.")

        shipping_rate_qs = ShippingRate.objects.filter(
            shipping_method__id=shipping_method_id,
            weight_min__lte=total_weight,
            weight_max__gte=total_weight
        )

        # Check for a rate defined at the city level
        if address.get('city'):
            rate = shipping_rate_qs.filter(
                city=address['city'],
                country=address['country'],
                region=address['state'] if address.get('state') else None,
            ).first()
            if rate:
                return rate

        # Check for a rate defined at the state level
        if address.get('state'):
            rate = shipping_rate_qs.filter(
                region=address['state'],
                country=address['country'],
            ).first()
            if rate:
                return rate

        # Check for a rate at the country level if no state rate is found, nationwide
        if address.get('country'):
            rate = shipping_rate_qs.filter(country=address['country']).first()
            if rate:
                rate = shipping_rate_qs.filter(
                    country=address['country'],
                    region__isnull=True,
                    city__isnull=True
                ).first()
                return rate
            
        # Global
        if not address.get('country'):
            rate = shipping_rate_qs.filter(country=address['country']).first()
            if rate:
                rate = shipping_rate_qs.filter(
                    country__isnull=True,
                    region__isnull=True,
                    city__isnull=True
                ).first()
                return rate
        else:
            raise serializers.ValidationError({"details": "We don't ship to this location."})

        # If no rate is found for the address, raise an exception
        raise ValueError("No shipping rate available for the provided location.")
class ShippingFeeCalculator:
    

    def get_shipping_fee_by_rate(self, shipping_method_id, address, total_weight):
        rate_instance = get_shipping_rate_instance(shipping_method_id, address, total_weight)
        if not rate_instance:
            custom_shipping_amount = self.validated_data.get('custom_shipping_amount', {})
            if custom_shipping_amount:
                return Decimal(custom_shipping_amount['price']), custom_shipping_amount.get('name', '-')
            else:
                return Decimal('0.00'), '-'

        # Calculate shipping fee based on weight
        max_weight = rate_instance.weight_max
        base_rate = rate_instance.rate
        incremental_rate = rate_instance.incremental_rate  # Assume ShippingRate has incremental_rate field

        if total_weight <= max_weight: # If total weight is less than or equal to max weight
            shipping_fee = base_rate
        else:
            extra_weight = total_weight - max_weight
            shipping_fee = base_rate + (extra_weight * incremental_rate)

        shipping_name = rate_instance.name if hasattr(rate_instance, 'name') else 'Standard Shipping'
        return shipping_fee, shipping_name

    def get_total_shipping_fee(self, variants, shipping_method_id, address):
        total_weight = self.get_total_weight(variants)
        shipping_fee, shipping_name = self.get_shipping_fee_by_rate(shipping_method_id, address, total_weight)
        return shipping_fee, shipping_name
    
    def get_total_weight(self, variants):
        return sum(variant['quantity'] * variant['weight'] for variant in variants) / 1000  # Convert to kg



class TaxCalculator:
    def calculate_tax(self, variants, discount, shipping_address):
        """
        Calculate tax based on each product's tax_class and the applicable TaxRate.
        Hierarchy for TaxRate: State > Country
        """
        from collections import defaultdict

        # Group subtotal by tax_class
        tax_class_subtotals = defaultdict(Decimal)
        for variant in variants:
            tax_class = variant['tax_class']
            variant_subtotal = variant['quantity'] * variant['price']
            tax_class_subtotals[tax_class] += variant_subtotal

        # Calculate total subtotal for proportional discount allocation
        total_subtotal = sum(tax_class_subtotals.values())
        if total_subtotal > 0 and discount > 0:
            for tax_class in tax_class_subtotals:
                # Allocate discount proportionally based on subtotal
                tax_class_subtotals[tax_class] -= (tax_class_subtotals[tax_class] / total_subtotal) * discount

        estimated_tax = Decimal('0.00')
        tax_details = []

        for tax_class, class_subtotal in tax_class_subtotals.items():
            tax_rate_instance = self.get_tax_rate(tax_class, shipping_address)
            if tax_rate_instance:
                tax_rate = tax_rate_instance.rate / Decimal('100')  # Assuming rate is percentage
                tax_type = tax_rate_instance.tax_class.name  # Assuming you want the tax class name
            else:
                tax_rate = Decimal('0.00')
                tax_type = 'No Tax'

            # TODO: wrong tax calculation when currency is KWD, the precisison is 3
            class_tax = (class_subtotal * tax_rate)
            estimated_tax += class_tax

            tax_details.append({
                'tax_class': tax_type,
                'tax_percentage': str(tax_rate * 100),
                'tax_amount': str(class_tax),
            })

        return estimated_tax, tax_details

    def get_tax_rate(self, tax_class, shipping_address):
        """
        Retrieve the applicable TaxRate for a given tax_class and shipping_address.
        Hierarchy: State > Country
        """
        tax_rate_instance = None

        if 'state' in shipping_address and shipping_address['state']:
            tax_rate_instance = TaxRate.objects.filter(
                tax_class=tax_class,
                state=shipping_address['state'],
                is_active=True
            ).first()

        if not tax_rate_instance and 'country' in shipping_address and shipping_address['country']:
            tax_rate_instance = TaxRate.objects.filter(
                tax_class=tax_class,
                country=shipping_address['country'],
                is_active=True
            ).first()

        return tax_rate_instance


class DiscountCalculator:
    def calculate_discount(self, subtotal, custom_discount_amount, promocode):
        """
        Calculate discount based on custom discount amount and/or promo code.
        Priority can be given to promo code over custom discount or vice versa based on business logic.
        """
        discount = Decimal('0.00')
        discount_name = 'No Discount'

        # Apply Promo Code Discount if available
        if promocode:
            if promocode.code_type == PromoCodeType.FIXED_AMOUNT:
                discount = promocode.value
                discount_name = f"Promo Code {promocode.code}"
            elif promocode.code_type == PromoCodeType.PERCENTAGE:
                discount = (subtotal * promocode.value) / Decimal('100')
                discount_name = f"Promo Code {promocode.code} ({promocode.value}%)"
            # Ensure discount does not exceed subtotal
            discount = min(discount, subtotal)

        # Apply Custom Discount if available and no Promo Code is used
        elif custom_discount_amount:
            try:
                discount = Decimal(custom_discount_amount['price'])
                discount_name = custom_discount_amount.get('name', 'Custom Discount')
                discount = min(discount, subtotal)
            except (KeyError, InvalidOperation):
                raise serializers.ValidationError({"custom_discount_amount": "Invalid discount amount."})

        return discount, discount_name
    
    def validated_promocode(self):
        promocode = self.validated_data.get('promocode')
        if promocode:
            try:
                promocode = PromoCode.objects.get(code=promocode)
            except PromoCode.DoesNotExist:
                raise serializers.ValidationError({"promocode": "Promo code not found."})
        return promocode
    
    def get_promocode_instance(self, promocode):
        if promocode:
            variant_aliases = [v['alias'] for v in self.validated_data['variants']]
            try:
                promocode = PromoCode.objects.get(code=promocode.upper())
                if not promocode.is_active:
                    raise serializers.ValidationError("Promo code is not active.")
                if not promocode.is_valid_customer(self.customer):
                    raise serializers.ValidationError("This promo code is restricted to specific customers and is not valid for you.")
                if not promocode.is_valid_product(variant_aliases):
                    raise serializers.ValidationError("Promo code is not valid for one or more of the products in your cart.")
                if not promocode.is_valid_min_purchase(self.customer):
                    raise serializers.ValidationError("Promo code is not valid for your purchase amount.")
                if not promocode.is_valid_redemption_limit(self.customer):
                    raise serializers.ValidationError("Promo code has reached its redemption limit.")
                if not promocode.is_valid_usage_limit_per_customer(self.customer):
                    raise serializers.ValidationError("Promo code has reached its usage limit for you.")
                if not promocode.is_valid_new_customer(self.customer):
                    raise serializers.ValidationError("Promo code is only valid for new customers.")
                
                
                return promocode
            except PromoCode.DoesNotExist:
                raise serializers.ValidationError("Promo code does not exist.")
        return None


class OrderCreator:
    def create_order_instance(self):
        """
        Creates and saves an Order instance based on the pre-calculated data.
        Also creates corresponding OrderLineItems.
        """

        if settings.VALIDATE_STOCK_ON_ORDER:
            validate_variant_with_stocks(self.variants)

        with transaction.atomic():
            shipping_address = self.validated_data.get('shipping_address', {})
            billing_address = self.validated_data.get('billing_address', {})
            
        
            custom_discount_amount = self.validated_data.get('custom_discount_amount')
            promocode = self.get_promocode_instance(self.validated_data.get('promocode'))
            shipping_method_id = self.validated_data.get('shipping_method_id', '')

            shipping_address_id = self.validated_data.get('shipping_address_id', None)
            billing_address_id = self.validated_data.get('billing_address_id', None)

            if self.request.user.role == UserRole.CUSTOMER:
                if shipping_address:
                    shipping_address['user_id'] = self.request.user.id
                if billing_address:
                    billing_address['user_id'] = self.request.user.id

            if not shipping_address_id:
                if shipping_address:
                    shipping_address_id = self.get_or_create_address(shipping_address).id
            if not billing_address_id:
                if billing_address:
                    billing_address_id = self.get_or_create_address(billing_address).id
                else:
                    billing_address_id = shipping_address_id


            # Prepare Order data
            customer_currency = self.validated_data.get('customer_currency') or self.request.currency
            order_data = {
                "user_id": self.customer,
                "supplier": self.validated_data.get('supplier'),

                "shipping_address_id": shipping_address_id,
                "billing_address_id": billing_address_id,

                "currency": settings.BASE_CURRENCY,
                "total_price": int(self.total * 100),  #  total is in units, convert to cents/subunits
                "total_price_without_tax":  int(self.total_without_tax * 100),
                "customer_currency": customer_currency,
                # "total_price_in_customer_currency": build_currency_amount(self.total, customer_currency),
                "status": OrderStatus.PENDING,
                "authorize_status": OrderAuthorizationStatus.NONE,
                "charge_status": OrderChargeStatus.DUE,
                "promo_code": promocode,
                "total_shipping_cost": int(self.shipping_fee * 100),  # Convert to cents
                "total_discounted_amount": int(self.discount * 100),  # Convert to cents
                "total_tax": int(self.estimated_tax * 100),  # Convert to cents
                'order_source': self.order_source,
                'note': self.validated_data.get('note', ''),
            }

            # Create Order instance
            order = Order.objects.create(**order_data)

            # Create OrderLineItems
            for variant in self.variants:
                OrderLineItem.objects.create(
                    order=order,
                    variant=variant['variant'],
                    quantity=variant['quantity'],
                    price_per_unit=variant['price'],
                    currency=order.currency,
                    total_price=int(variant['quantity'] * variant['price'] * 100),  # Convert to cents
                    customer_currency=order.customer_currency,
                    # total_price_in_customer_currency=variant['quantity'] * variant['price'],
                    tax_rate=self.get_tax_rate(variant['tax_class'], shipping_address).rate if self.get_tax_rate(variant['tax_class'], shipping_address) else Decimal('0.00'),
                )


            if self.collect_user_agent:
                try:
                    user_agent_data = parse_user_agent(self.request)
                    OrderDeviceMeta.objects.create(order=order, **user_agent_data)
                except Exception as e:
                    pass
            
            if self.reserve_stock:
                handle_stock_reserve.delay(order.id)
                
            return order

    def get_or_create_address(self, address_data):
        """
        Retrieves an existing Address or creates a new one based on the provided data.
        """
        if not address_data:
            return None

        # Assuming address_data contains enough information to uniquely identify an address
        address = Address.objects.create(
            user_id=self.customer,
            first_name=address_data.get('first_name', ''),
            last_name=address_data.get('last_name', ''),
            phone_number=address_data.get('phone_number', ''),
            email=address_data.get('email', ''),
            address_type=address_data.get('address_type', AddressType.DSA_DBA),
            street_address=address_data.get('street_address', ''),
            city=address_data.get('city', ''),
            state=address_data.get('state', ''),
            country=address_data.get('country', ''),
        )
        return address

class OrderCalculation(ShippingFeeCalculator, TaxCalculator, DiscountCalculator, OrderCreator):
    def __init__(self, validated_data, order_source, create_order=False, collect_user_agent=False, request=None):
        self.validated_data = validated_data
        self.create_order = create_order
        self.reserve_stock = settings.RESERVE_STOCK_ON_ORDER
        self.order_source = order_source
        self.collect_user_agent = collect_user_agent
        self.request = request
        self.customer = self.validated_data.get('customer_id', None)
        self.variants = self.get_variants()
        self.total_subtotal = self.get_subtotal(self.variants)
        self.total_items = self.get_total_items(self.variants)
        self.discount, self.discount_name = self.calculate_discount(
            self.total_subtotal,
            self.validated_data.get('custom_discount_amount'),
            self.get_promocode_instance(self.validated_data.get('promocode'))
        )
        self.discount_percentage = (self.discount / self.total_subtotal * 100) if self.total_subtotal > 0 else 0
        self.shipping_fee, self.shipping_name = self.get_total_shipping_fee(
            self.variants,
            self.validated_data.get('shipping_method_id', ''),
            self.validated_data.get('shipping_address', {})
        )
        self.estimated_tax, self.tax_details = self.calculate_tax(
            self.variants,
            self.discount,
            self.validated_data.get('shipping_address', {})
        )
        self.total = self.total_subtotal - self.discount + self.shipping_fee + self.estimated_tax
        self.total_without_tax = self.total_subtotal - self.discount + self.shipping_fee

    def get_response(self):
        exchange_rate = currency_Backend().get_exchange_rate(self.request.currency)
        response_data = {
            "subtotal":  apply_exchange_rate(self.total_subtotal, exchange_rate, self.request.currency, 'en_US'),
            "total_items": self.total_items,
            "discount": apply_exchange_rate(self.discount, exchange_rate, self.request.currency, 'en_US'),
            "discount_percentage": self.discount_percentage,
            "discount_name": self.discount_name,
            "shipping_fee": apply_exchange_rate(self.shipping_fee, exchange_rate, self.request.currency, 'en_US'),
            "shipping_name": self.shipping_name,
            "estimated_tax": apply_exchange_rate(self.estimated_tax, exchange_rate, self.request.currency, 'en_US'),
            "tax_details": self.tax_details,
            "total": apply_exchange_rate(self.total, exchange_rate, self.request.currency, 'en_US'), # total amount that will be charged
            "total_without_tax": apply_exchange_rate(self.total_without_tax, exchange_rate, self.request.currency, 'en_US'),
        }
        return response_data


    def get_variants(self):
        variants_data = self.validated_data.get('variants')
        variants = []

        for variant_data in variants_data:
            try:
                variant = ProductVariant.objects.get(alias=variant_data['alias'])
                quantity = variant_data['quantity']
                weight = variant.weight_value if variant.weight_value is not None else Decimal('0.00')

                variants.append({
                    'variant': variant,
                    'quantity': quantity,
                    'weight': weight,
                    'price': variant.price,
                    'tax_class': variant.product.tax_class,
                })

            except ProductVariant.DoesNotExist:
                raise serializers.ValidationError({
                    "variants": f"Variant with alias '{variant_data['alias']}' not found."
                })

        return variants

    def get_subtotal(self, variants):
        return sum(variant['quantity'] * variant['price'] for variant in variants)

    def get_total_items(self, variants):
        return sum(variant['quantity'] for variant in variants)
    

class OrderProccessorAPIView(generics.GenericAPIView):
    """
        View to estimate and create an order.
        The base class for order eastimation and creation. works for both admin and customer.
        If you test the order creation, you must comply with the following docs: https://github.com/nxtbn-com/testing-ordering 
    """
    create_order = False
    broadcast_on_order_create = False
    order_source = 'admin' # options: 'admin', 'storefront', 'mobile
    collect_user_agent = False

    serializer_class = OrderEstimateSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)


        try:
            order_calculation = OrderCalculation(
                serializer.validated_data,
                order_source=self.order_source,
                create_order=self.create_order,
                collect_user_agent=self.collect_user_agent,
                request=request
            )
            response = order_calculation.get_response()

            if self.create_order:
                order = order_calculation.create_order_instance()
                response['order_id'] = str(order.id)  # Include order ID in the response
                response['order_alias'] = order.alias
                if self.broadcast_on_order_create:
                    order_created.send(sender=self.__class__, order=order, request=request)

            return Response(response, status=status.HTTP_200_OK)
        except serializers.ValidationError as e:
            return Response({"error": e.detail}, status=status.HTTP_400_BAD_REQUEST)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)