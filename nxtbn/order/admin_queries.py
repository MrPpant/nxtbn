from django.conf import settings
import graphene
from graphene_django.filter import DjangoFilterConnectionField

from nxtbn.core.admin_permissions import gql_store_admin_required
from nxtbn.core.models import SiteSettings
from nxtbn.order.admin_types import OrderDeviceMetaType, OrderInvoiceType, OrderType
from nxtbn.order.models import Address, Order, OrderDeviceMeta
from nxtbn.users import UserRole


class AdminOrderQuery(graphene.ObjectType):
    orders = DjangoFilterConnectionField(OrderType)
    order = graphene.Field(OrderType, alias=graphene.UUID(required=True))
    order_device_meta = DjangoFilterConnectionField(OrderDeviceMetaType)
    order_device_metas = DjangoFilterConnectionField(OrderDeviceMetaType)

    order_invoice = graphene.Field(OrderInvoiceType, order_id=graphene.Int(required=True))
    order_invoices = graphene.List(OrderInvoiceType, order_ids=graphene.List(graphene.Int))

   

    @gql_store_admin_required
    def resolve_orders(self, info, **kwargs):
        return Order.objects.all()
    
    @gql_store_admin_required
    def resolve_order(self, info, alias):
        try:
            order = Order.objects.get(alias=alias)
        except Order.DoesNotExist:
            raise Exception("Order not found")
        
        return order
    
    @gql_store_admin_required
    def resolve_order_device_meta(self, info, **kwargs):
        return OrderDeviceMeta.objects.all()
    
    @gql_store_admin_required
    def resolve_order_device_metas(self, info, **kwargs):
        return OrderDeviceMeta.objects.all()
    
   
    @gql_store_admin_required
    def resolve_order_invoice(self, info, order_id):
        order = Order.objects.select_related(
            'billing_address', 'shipping_address'
        ).prefetch_related(
            'line_items__variant'
        ).get(id=order_id)

        return order
    
    @gql_store_admin_required
    def resolve_order_invoices(self, info, order_ids, **kwargs):
        if len(order_ids) > 100:
            raise Exception("You can only query 100 orders at a time")
        
        if not order_ids:
            raise Exception("You must provide order ids")

        order = Order.objects.select_related(
            'billing_address', 'shipping_address'
        ).prefetch_related(
            'line_items__variant'
        ).filter(id__in=order_ids)

        return order