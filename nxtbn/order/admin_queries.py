from django.conf import settings
import graphene
from graphene_django.filter import DjangoFilterConnectionField

from nxtbn.core.admin_permissions import gql_store_admin_required
from nxtbn.core.models import SiteSettings
from nxtbn.order.admin_types import OrderInvoiceType, OrderType
from nxtbn.order.models import Address, Order
from nxtbn.users import UserRole


class AdminOrderQuery(graphene.ObjectType):
    orders = DjangoFilterConnectionField(OrderType)
    order = graphene.Field(OrderType, id=graphene.Int(required=True))
    order_invoice = graphene.Field(OrderInvoiceType, order_id=graphene.Int(required=True))
    order_invoices = DjangoFilterConnectionField(OrderInvoiceType)

   

    @gql_store_admin_required
    def resolve_orders(self, info, **kwargs):
        return Order.objects.all()
    
    @gql_store_admin_required
    def resolve_order(self, info, id):
        try:
            order = Order.objects.get(id=id)
        except Order.DoesNotExist:
            raise Exception("Order not found")
        
        return order
    
   
    @gql_store_admin_required
    def resolve_order_invoice(self, info, order_id):
        order = Order.objects.select_related(
            'billing_address', 'shipping_address'
        ).prefetch_related(
            'line_items__variant'
        ).get(id=order_id)

        return order
    
    @gql_store_admin_required
    def resolve_order_invoices(self, info, **kwargs):
        order = Order.objects.select_related(
            'billing_address', 'shipping_address'
        ).prefetch_related(
            'line_items__variant'
        ).all()

        return order