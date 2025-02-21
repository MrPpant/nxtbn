from django.db import models

from django.db import models
from django.conf import settings
from django.forms import ValidationError
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.core.validators import MinValueValidator
from decimal import Decimal
from nxtbn.core import CurrencyTypes, MoneyFieldTypes
from nxtbn.core.enum_perms import  PermissionsEnum
from nxtbn.core.mixin import MonetaryMixin
from nxtbn.core.models import AbstractAddressModels, AbstractBaseModel, AbstractBaseUUIDModel
from nxtbn.core.utils import build_currency_amount, to_currency_unit
from nxtbn.discount.models import PromoCode
from nxtbn.gift_card.models import GiftCard
from nxtbn.order import AddressType, OrderAuthorizationStatus, OrderChargeStatus, OrderStatus, OrderStockReservationStatus, PaymentTerms, ReturnReason, ReturnReceiveStatus, ReturnStatus
from nxtbn.payment import PaymentMethod
from nxtbn.product.models import ProductVariant
from nxtbn.users import UserRole
from nxtbn.users.models import User
from nxtbn.product.models import Supplier

from money.money import Currency, Money
from babel.numbers import get_currency_precision, format_currency



class Address(AbstractAddressModels):
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, related_name="addresses")
    # Customizable Receiver Information / may redundent with user model. if no user/auth, fill first_name and last_name
    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50)

    phone_number = models.CharField(max_length=15, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    address_type = models.CharField(
        max_length=7,
        choices=AddressType.choices,
        default=AddressType.DSA_DBA
    )

    class Meta:
        ordering = ('last_name', 'first_name')

    def __str__(self):
        return f"{self.first_name} {self.last_name}, {self.street_address}, {self.city}, {self.country}"
    
    def clean(self):
        """ 
        Validates that a user cannot have more than one DSA and DBA.
        If the user has DSA_DBA, they cannot have separate DSA or DBA.
        Unlimited SA and BA are allowed.
        """
        if self.user:
            user_addresses = Address.objects.filter(user=self.user)
            dsa_dba = user_addresses.filter(address_type=AddressType.DSA_DBA).exists()
            dsa_count = user_addresses.filter(address_type=AddressType.DSA).count()
            dba_count = user_addresses.filter(address_type=AddressType.DBA).count()

            if dsa_dba and self.address_type in [AddressType.DSA, AddressType.DBA]:
                raise ValidationError("User already has a DSA_DBA. Cannot create separate DSA or DBA.")

            if self.address_type == AddressType.DSA_DBA and (dsa_count > 0 or dba_count > 0):
                raise ValidationError("User has separate DSA or DBA. Cannot create DSA_DBA.")

            if self.address_type == AddressType.DSA and dsa_count > 0:
                raise ValidationError("User already has a Default Shipping Address (DSA).")

            if self.address_type == AddressType.DBA and dba_count > 0:
                raise ValidationError("User already has a Default Billing Address (DBA).")

    def save(self, *args, **kwargs):
        # Ensure that validation is called before saving
        self.clean()
        super().save(*args, **kwargs)

class Order(MonetaryMixin, AbstractBaseUUIDModel):
    """
    Represents an order placed by a customer.

    An order consists of one or more items purchased by the customer.
    It tracks the status of the order, payment details, and shipping information.

    Attributes:
        order_number (str): A unique identifier for the order.
        customer (ForeignKey): The customer who placed the order.
        total_amount (Decimal): The total amount of the order.
        authorization_status (OrderAuthorizationStatus): The authorization status of the order's funds.
        charge_status (OrderChargeStatus): The charge status of the order's transaction charges.
        status (OrderStatus): The current status of the order's lifecycle.
        created_at (datetime): The date and time when the order was created.
        last_modified (datetime): The date and time when the order was last updated.

    Note:
        - The `authorization_status` field indicates whether funds have been authorized for the order,
          and to what extent they cover the order's total amount.
        - The `charge_status` field indicates whether funds have been charged for the order,
          and to what extent they cover the order's total amount.
        - The `status` field tracks the different stages of the order's lifecycle,
          such as pending, processing, shipped, delivered, cancelled, or returned.
    """

    # https://docs.nxtbn.com/moneyvalidation
    money_validator_map = {
        "total_price": {
            "currency_field": "currency",
            "type": MoneyFieldTypes.SUBUNIT,
            "require_base_currency": True,
        },
        "total_price_without_tax": {
            "currency_field": "currency",
            "type": MoneyFieldTypes.SUBUNIT,
            "require_base_currency": True,
        },
        "total_shipping_cost": {
            "currency_field": "currency",
            "type": MoneyFieldTypes.SUBUNIT,
            "require_base_currency": True,
        },
        "total_discounted_amount": {
            "currency_field": "currency",
            "type": MoneyFieldTypes.SUBUNIT,
            "require_base_currency": True,
        },
        "total_tax": {
            "currency_field": "currency",
            "type": MoneyFieldTypes.SUBUNIT,
            "require_base_currency": True,
        },
    }



    user = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="orders",
        null=True,
        blank=True,
        limit_choices_to={'role': UserRole.CUSTOMER}
    )
    order_source = models.CharField(
        max_length=20,
        null=True,
        blank=True,
    )
    supplier = models.ForeignKey(Supplier, null=True, blank=True, on_delete=models.SET_NULL)
    shipping_address = models.ForeignKey(Address, null=True, blank=True, on_delete=models.SET_NULL, related_name="shipping_orders")
    billing_address = models.ForeignKey(Address, null=True, blank=True, on_delete=models.SET_NULL, related_name="billing_orders")


    currency = models.CharField(
        max_length=3,
        default=CurrencyTypes.USD,
        choices=CurrencyTypes.choices,
        help_text="ISO currency code for the order. This is the base currency in which the total amount will be stored after converting from the customer's currency to the base currency. "
                "For example, 'USD' for US Dollars. The base currency is defined in the settings."
    )

    # total amount that needs to be paid by the customer
    total_price = models.BigIntegerField( # total shipping cost + total discounted amount + total tax + total line items
        null=True, blank=True, validators=[MinValueValidator(1)],
        help_text="Total amount of the order in cents, converted from the original currency (customer's currency) to the base currency. "
                "For example, if the base currency is USD and the customer_currency is different (e.g., AUD), the total amount will be converted to USD. "
                "This converted amount is stored in cents."
    )

    total_price_without_tax = models.BigIntegerField( # total shipping cost + total discounted amount + total line items
        null=True, blank=True, validators=[MinValueValidator(1)],
        help_text="Total amount of the order without tax in cents, stored in the base currency."
    )
    
    total_shipping_cost = models.BigIntegerField(
        null=True, blank=True, validators=[MinValueValidator(0)],
        help_text="Total shipping amount of the order in cents, stored in the base currency.",
        default=0,
    )
    total_discounted_amount = models.BigIntegerField(
        null=True, blank=True, validators=[MinValueValidator(0)],
        default=0,
        help_text="Total amount of the order after applying discounts in cents, stored in the base currency."
    )
    total_tax = models.BigIntegerField(
        null=True, blank=True, validators=[MinValueValidator(0)],
        default=0,
        help_text="Total tax amount of the order in cents, stored in the base currency."
    )

    customer_currency = models.CharField( # if customer_currency is different from base currency
        max_length=3,
        choices=CurrencyTypes.choices,
        help_text="ISO currency code of the original amount paid by the customer. "
                "For example, 'AUD' for Australian Dollars."
    )
    currency_conversion_rate = models.DecimalField( # if customer_currency is different from base currency
        null=True,
        blank=True,
        decimal_places=4,
        max_digits=12,
        help_text="Original amount paid by the customer in the customer's currency, stored in cents. "
    )


    status = models.CharField(
        max_length=20,
        choices=OrderStatus.choices,
        default=OrderStatus.PENDING,
        help_text="Represents the current stage of the order within its lifecycle.",
        verbose_name="Order Status",
    )
    authorize_status = models.CharField(
        max_length=32,
        default=OrderAuthorizationStatus.NONE,
        choices=OrderAuthorizationStatus.choices,
        help_text="Represents the authorization status of the order based on fund coverage.",
        verbose_name="Authorization Status",
    )
    charge_status = models.CharField(
        max_length=32,
        default=OrderChargeStatus.DUE,
        choices=OrderChargeStatus.choices,
        help_text="Represents the charge status of the order based on transaction charges.",
        verbose_name="Charge Status",
    )

    promo_code = models.ForeignKey(PromoCode, on_delete=models.SET_NULL, null=True, blank=True)
    gift_card = models.ForeignKey(GiftCard, on_delete=models.SET_NULL, null=True, blank=True)
    payment_term = models.CharField( # incase charge_status is DUE
        max_length=32,
        default=PaymentTerms.DUE_ON_RECEIPT,
        choices=PaymentTerms.choices,
        help_text="Represents the payment terms for the order."
    )
    due_date = models.DateField(null=True, blank=True) # if payment_term is FIXED_DATE

    preferred_payment_method = models.CharField(
        max_length=32,
        choices=PaymentMethod.choices,
        default=PaymentMethod.CASH_ON_DELIVERY,
        help_text="Preferred payment method for this order. The actual payment method may differ when the order is initiated or paid."
    )
    reservation_status = models.CharField(
        default=OrderStockReservationStatus.NOT_REQUIRED,
        max_length=20,
        choices=OrderStockReservationStatus.choices
    )
    note = models.TextField(blank=True, null=True, max_length=255) # filled by customer
    comment = models.TextField(blank=True, null=True, max_length=500) # filled by admin

    class Meta:
        ordering = ('-created_at',) # Most recent orders first
        permissions = [
            (PermissionsEnum.CAN_APPROVE_ORDER, 'Can approve order'),
            (PermissionsEnum.CAN_CANCEL_ORDER, 'Can cancel order'),
            (PermissionsEnum.CAN_SHIP_ORDER, 'Can ship order'),
            (PermissionsEnum.CAN_PACK_ORDER, 'Can process order'),
            (PermissionsEnum.CAN_DELIVER_ORDER, 'Can deliver order'),
            (PermissionsEnum.CAN_UPDATE_ORDER_PYMENT_TERM, 'Can update order payment term'),
            (PermissionsEnum.CAN_UPDATE_ORDER_PAYMENT_METHOD, 'Can update order payment method'),
            (PermissionsEnum.CAN_FULLFILL_ORDER, 'Can fullfill order'), # Directly fullfill order, will not check order lifecycle
        ]

    def save(self, *args, **kwargs):
        self.validate_amount()
        super(Order, self).save(*args, **kwargs)

    def clean(self):
        if self.payment_term == PaymentTerms.FIXED_DATE and not self.due_date:
            raise ValidationError(_('Due date is required when payment terms are FIXED_DATE.'))
        super().clean()

    

    def get_payment_method(self):
        if self.payments.exists():
            return self.payments.first().payment_method
        return 'AWAITING_SELECTION'
    
    def total_piad_amount(self):
        precision = get_currency_precision(self.currency)
        total_in_subunits = self.payments.filter(is_successful=True).aggregate(models.Sum('payment_amount'))['payment_amount__sum']
        if total_in_subunits is None:
            return 0
        total_in_unit = total_in_subunits / (10 ** precision)
        return total_in_unit
    
    def humanize_total_paid_amount(self, locale='en_US'):
        if locale:
            return format_currency(self.total_piad_amount(), self.currency, locale=locale)
        return self.total_piad_amount()
       

    def total_in_units(self): #subunit -to-unit 
        precision = get_currency_precision(self.currency)
        unit = self.total_price / (10 ** precision)
        return unit
    
    def total_shipping_cost_in_units(self): #subunit -to-unit
        if self.total_shipping_cost is None:
            return 0
        precision = get_currency_precision(self.currency)
        unit = self.total_shipping_cost / (10 ** precision)
        return unit
    
    def total_discounted_amount_in_units(self): #subunit -to-unit
        if self.total_discounted_amount is None:
            return 0
        precision = get_currency_precision(self.currency)
        unit = self.total_discounted_amount / (10 ** precision)
        return unit
    
    def total_tax_in_units(self): #subunit -to-unit
        if self.total_tax is None:
            return 0
        precision = get_currency_precision(self.currency)
        unit = self.total_tax / (10 ** precision)
        return unit
    
    def humanize_total_price(self, locale='en_US'):
        if locale:
            return format_currency(self.total_in_units(), self.currency, locale=locale)
        return self.total_in_units()
    
    def humanize_total_shipping_cost(self):
        return format_currency(self.total_shipping_cost_in_units(), self.currency, locale='en_US')
    
    def humanize_total_discounted_amount(self):
        return format_currency(self.total_discounted_amount_in_units(), self.currency, locale='en_US')
    
    def humanize_total_tax(self):
        return format_currency(self.total_tax_in_units(), self.currency, locale='en_US')
    
    def get_due(self):
        if self.charge_status == OrderChargeStatus.DUE:
            return self.humanize_total_price()
        
        if self.charge_status in [OrderChargeStatus.FULL, OrderChargeStatus.OVERCHARGED]:
            return to_currency_unit(0, self.currency, locale='en_US')
        
        if self.charge_status == OrderChargeStatus.PARTIAL:
            paid_amount = self.payments.filter(is_successful=True,).aggregate(models.Sum('payment_amount'))['payment_amount__sum']
            if paid_amount is None:
                return  to_currency_unit(0, self.currency, locale='en_US')

            due_in_subunits = self.total_price - paid_amount
            return to_currency_unit(due_in_subunits, self.currency, locale='en_US')
        
    def is_overdue(self):
        if self.due_date and self.due_date < timezone.now().date():
            return True
        return False
    
    def get_overcharged_amount(self):
        if self.charge_status == OrderChargeStatus.OVERCHARGED:
            overcharged_amount = self.payments.filter(is_successful=True).aggregate(models.Sum('payment_amount'))['payment_amount__sum'] - self.total_price
            return to_currency_unit(overcharged_amount, self.currency, locale='en_US')
        return to_currency_unit(0, self.currency, locale='en_US')
        

    
    def __str__(self):
        return f"Order {self.id} - {self.status}"


class OrderLineItem(MonetaryMixin, models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="line_items")
    variant = models.ForeignKey(ProductVariant, on_delete=models.PROTECT, related_name="orderlineitems")
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    price_per_unit = models.DecimalField(max_digits=12, decimal_places=3, validators=[MinValueValidator(Decimal("0.01"))])
    

    currency = models.CharField(
        max_length=3,
        default=CurrencyTypes.USD,
        choices=CurrencyTypes.choices,
    )
    total_price = models.IntegerField(
        null=True, blank=True, validators=[MinValueValidator(1)],
    )

    customer_currency = models.CharField(
        max_length=3,
        default=CurrencyTypes.USD,
        choices=CurrencyTypes.choices,
    )
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, help_text=_("Tax rate at the time of the order"))

    def total_in_units(self): #subunit -to-unit 
        precision = get_currency_precision(self.currency)
        unit = self.total_price / (10 ** precision)
        return unit

    def humanize_total_price(self, locale='en_US'):
        """
        Returns the total price of the order formatted with the currency symbol,
        making it more human-readable.

        Returns:
            str: The formatted total price with the currency symbol.
        """
        if locale:
            return format_currency(self.total_in_units(), self.currency, locale='en_US')
        return self.total_in_units()
        
    
    def humanize_price_per_unit(self):
        """
        Returns the price per unit of the order formatted with the currency symbol,
        making it more human-readable.

        Returns:
            str: The formatted price per unit with the currency symbol.
        """
        return format_currency(self.price_per_unit, self.currency, locale='en_US')
    
    def get_descriptive_name(self):
        return self.variant.get_descriptive_name()


    def __str__(self):
        return f"{self.variant.product.name} - {self.variant.name} - Qty: {self.quantity}"



class ReturnRequest(AbstractBaseUUIDModel):
    initiated_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name="returns")
    reviewed_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name="reviewed_returns", null=True, blank=True)
    approved_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name="approved_returns", null=True, blank=True)
    completed_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name="resolved_returns", null=True, blank=True)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="returns")
    status = models.CharField(
        max_length=20,
        choices=ReturnStatus.choices,
        default=ReturnStatus.REQUESTED,
        verbose_name="Return Status",
    )
    reason_details = models.TextField(help_text="Reason for the return")
    reason = models.CharField(
        max_length=100,
        help_text="Reason for the return",
        choices=ReturnReason.choices,
        default=ReturnReason.NO_REASON
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    rejected_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ('-created_at',)

class ReturnLineItem(models.Model):
    return_request = models.ForeignKey(ReturnRequest, on_delete=models.CASCADE, related_name="line_items")
    order_line_item = models.ForeignKey(OrderLineItem, on_delete=models.CASCADE, related_name="return_line_items")
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    refunded_amount = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text="Amount refunded for this line item"
    )
    receiving_status = models.CharField(choices=ReturnReceiveStatus.choices, default=ReturnReceiveStatus.NOT_RECEIVED, max_length=20)
    destination = models.ForeignKey(
        'warehouse.Warehouse',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Warehouse where the return line item will be received."
    )

    def get_descriptive_name(self):
        return self.order_line_item.get_descriptive_name()


class OrderDeviceMeta(models.Model):
    """
    Stores device metadata for an order, capturing the IP address, browser,
    and other device information to enhance security tracking.
    """
    order = models.OneToOneField(
        Order,
        on_delete=models.CASCADE,
        related_name="device_meta",
        help_text="Related order for which this device metadata is recorded."
    )
    ip_address = models.GenericIPAddressField(
        null=True, blank=True,
        help_text="IP address of the user when placing the order."
    )
    user_agent = models.TextField(
        null=True, blank=True,
        help_text="Browser's user-agent string for identifying the browser and device."
    )
    browser = models.CharField(
        max_length=100, blank=True, null=True,
        help_text="Browser name extracted from the user-agent."
    )
    browser_version = models.CharField(
        max_length=50, blank=True, null=True,
        help_text="Browser version extracted from the user-agent."
    )
    operating_system = models.CharField(
        max_length=100, blank=True, null=True,
        help_text="Operating system of the device."
    )
    device_type = models.CharField(
        max_length=50, blank=True, null=True,
        help_text="Device type (e.g., Mobile, Desktop, Tablet)."
    )

    class Meta:
        verbose_name = "Order Device Metadata"
        verbose_name_plural = "Order Device Metadata"

    def __str__(self):
        return f"Device Meta for Order {self.order.id}"