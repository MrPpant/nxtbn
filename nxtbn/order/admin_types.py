from django.conf import settings
import graphene
from graphene_django import DjangoObjectType
from graphene import relay
from nxtbn.core.models import SiteSettings
from nxtbn.order.models import Address, Order, OrderDeviceMeta, OrderLineItem

from nxtbn.order.admin_filters import OrderFilter

class AddressGraphType(DjangoObjectType):
    db_id = graphene.Int(source='id')
    class Meta:
        model = Address
        fields = (
            'id',
            'first_name',
            'last_name',
            'street_address',
            'city',
            'postal_code',
            'country',
            'phone_number',
            'email',
            'address_type',
        )


class OrderLineItemsType(DjangoObjectType):
    db_id = graphene.Int(source='id')
    humanize_total_price = graphene.String()
    humanize_price_per_unit = graphene.String()

    def resolve_humanize_total_price(self, info):
        return self.humanize_total_price()
    
    def resolve_humanize_price_per_unit(self, info):
        return self.humanize_price_per_unit()
    class Meta:
        model = OrderLineItem
        fields = (
            'id',
            'quantity',
            'variant',
            'total_price',
            'price_per_unit',
        )

class OrderType(DjangoObjectType):
    db_id = graphene.Int(source='id')
    humanize_total_price = graphene.String()
    line_items  = graphene.List(OrderLineItemsType)
    overcharged_amount = graphene.String()
    is_overdue = graphene.Boolean()
    payment_method = graphene.String()
    humanize_total_price = graphene.String()
    humanize_total_shipping_cost = graphene.String()
    humanize_total_discounted_amount = graphene.String()
    humanize_total_tax = graphene.String()
    humanize_total_paid_amount = graphene.String()
    due = graphene.String()
    total_price_without_symbol = graphene.String()

    def resolve_total_price_without_symbol(self, info):
        return self.humanize_total_price(locale='')

    def resolve_humanize_total_price(self, info):
        return self.humanize_total_price()
    
    def resolve_line_items(self, info):
        return self.line_items.all()
    
    def resolve_overcharged_amount(self, info):
        return self.get_overcharged_amount()
    
    def resolve_is_overdue(self, info):
        return self.is_overdue()
    
    def resolve_payment_method(self, info):
        return self.get_payment_method()
    
    def resolve_humanize_total_price(self, info):
        return self.humanize_total_price()
    
    def resolve_humanize_total_shipping_cost(self, info):
        return self.humanize_total_shipping_cost()
    
    def resolve_humanize_total_discounted_amount(self, info):
        return self.humanize_total_discounted_amount()
    
    def resolve_humanize_total_tax(self, info):
        return self.humanize_total_tax()
    
    def resolve_humanize_total_paid_amount(self, info):
        return self.humanize_total_paid_amount()
    
    def resolve_due(self, info):
        return self.get_due()


    class Meta:
        model = Order
        fields = (
            'alias',
            'id',
            'status',
            'shipping_address',
            'billing_address',
            'created_at',
            'last_modified',
            'total_price',
            'total_price_without_tax',
            'total_shipping_cost',
            'total_discounted_amount',
            'total_tax',
            'customer_currency',
            'currency_conversion_rate',
            'authorize_status',
            'charge_status',
            'promo_code',
            'gift_card',
            'payment_term',
            'due_date',
            'preferred_payment_method',
            'reservation_status',
            'note',
            'comment',
            'user',
            'due'
        )
        interfaces = (relay.Node,)
        filterset_class = OrderFilter



class OrderInvoiceLineItemType(DjangoObjectType):
    total_price = graphene.String()
    price_per_unit = graphene.String()
    name = graphene.String()

    class Meta:
        model = OrderLineItem
        fields = ['id', 'quantity']

    def resolve_total_price(self, info):
        return self.humanize_total_price()

    def resolve_price_per_unit(self, info):
        return self.humanize_price_per_unit()

    def resolve_name(self, info):
        return self.variant.get_descriptive_name_minimal()

class OrderInvoiceType(DjangoObjectType):
    db_id = graphene.Int(source='id')
    humanize_total_price = graphene.String()
    items = graphene.List(OrderInvoiceLineItemType)
    total_price = graphene.String()
    total_tax = graphene.String()
    total_shipping_cost = graphene.String()
    total_price_without_tax = graphene.String()
    total_discounted_amount = graphene.String()

    def resolve_humanize_total_price(self, info):
        return self.humanize_total_price()
    
    def resolve_items(self, info):
        return self.line_items.all()

    def resolve_total_price(self, info):
        return self.humanize_total_price()
    
    def resolve_total_tax(self, info):
        return self.humanize_total_tax()
    
    def resolve_total_shipping_cost(self, info):
        return self.humanize_total_shipping_cost()
    
    def resolve_total_price_without_tax(self, info):
        return self.humanize_total_tax()
    
    def resolve_total_discounted_amount(self, info):
        return self.humanize_total_discounted_amount()
    
    class Meta:
        model = Order
        fields = (
            'alias',
            'id',
            'status',
            'shipping_address',
            'billing_address',
            'created_at',
            'customer_currency',
            'currency_conversion_rate',
            'authorize_status',
            'charge_status',
            'payment_term',
            'due_date',
            'preferred_payment_method',
            'reservation_status',
            'note',
        )


class OrderDeviceMetaType(DjangoObjectType):
    db_id = graphene.Int(source='id')
    class Meta:
        model = OrderDeviceMeta
        fields = (
            'id',
            'order',
            'ip_address',
            'user_agent',
            'browser',
            'browser_version',
            'operating_system',
            'device_type',
        )
        interfaces = (relay.Node,)
        filter_fields = (
            'order__alias',
        )