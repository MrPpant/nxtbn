import graphene
import graphene
from graphql import GraphQLError
from nxtbn.order import OrderStatus
from nxtbn.order.models import OrderLineItem, Order, OrderStockReservationStatus

class DeleteLineItems(graphene.Mutation):
    class Arguments:
        line_item_ids = graphene.List(graphene.ID, required=True)
        order_id = graphene.ID(required=True)

    deleted_count = graphene.Int()

    def mutate(self, info, line_item_ids, order_id):
        order = Order.objects.get(id=order_id)
        if order.status in [OrderStatus.SHIPPED, OrderStatus.DELIVERED, OrderStatus.CANCELLED, OrderStatus.RETURNED, OrderStatus.PENDING_RETURN]:
            raise GraphQLError("Cannot delete line items from a shipped, delivered, cancelled, returned, or pending return order.")

        line_items = OrderLineItem.objects.filter(id__in=line_item_ids)

        if not line_items.exists():
            raise GraphQLError("No matching line items found.")
        
        if order.reservation_status == OrderStockReservationStatus.RESERVED:
            for line_item in line_items:
                line_item.product.stock += line_item.quantity
                line_item.product.save()

        # Get the count before deleting
        count = line_items.count()
        
        # Bulk delete
        line_items.delete()

        return DeleteLineItems(deleted_count=count)




class AdminOrderMutation(graphene.ObjectType):
    delete_line_items = DeleteLineItems.Field()