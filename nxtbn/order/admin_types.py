from django.conf import settings
import graphene
from graphene_django import DjangoObjectType
from graphene import relay
from nxtbn.core.models import SiteSettings
from nxtbn.order.models import Address, Order, OrderLineItem

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


class OrderType(DjangoObjectType):
    db_id = graphene.Int(source='id')
    humanize_total_price = graphene.String()

    def resolve_humanize_total_price(self, info):
        return self.humanize_total_price()
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

    def resolve_humanize_total_price(self, info):
        return self.humanize_total_price()
    
    def resolve_items(self, info):
        return self.line_items.all()

    def resolve_total_price(self, info):
        return self.humanize_total_price()
    
    class Meta:
        model = Order
        fields = (
            'alias',
            'id',
            'status',
            'shipping_address',
            'billing_address',
            'created_at',
            'total_price_without_tax',
            'total_shipping_cost',
            'total_discounted_amount',
            'total_tax',
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