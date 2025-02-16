import graphene
import graphene
from graphql import GraphQLError
from nxtbn.core.admin_permissions import gql_store_admin_required
from nxtbn.order import OrderStatus
from nxtbn.order.models import OrderLineItem, Order, OrderStockReservationStatus


class UpdateOrderComment(graphene.Mutation):
    class Arguments:
        id = graphene.ID(required=True)
        comment = graphene.String(required=True)

    success = graphene.Boolean()

    @gql_store_admin_required
    def mutate(root, info, id, comment):
        try:
            order = Order.objects.get(pk=id)
            order.comment = comment
            order.save()
            return UpdateOrderComment(success=True)
        except Order.DoesNotExist:
            raise Exception("Order not found")

class AdminOrderMutation(graphene.ObjectType):
    update_order_comment = UpdateOrderComment.Field()