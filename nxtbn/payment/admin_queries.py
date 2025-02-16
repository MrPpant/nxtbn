from django.conf import settings
import graphene
from graphene_django.filter import DjangoFilterConnectionField

from nxtbn.core.admin_permissions import gql_store_admin_required
from nxtbn.payment.admin_types import PaymentType
from nxtbn.payment.models import Payment


class AdminPaymentQuery(graphene.ObjectType):
    payments = DjangoFilterConnectionField(PaymentType)
    payment = graphene.Field(PaymentType, id=graphene.Int(required=True))

    @gql_store_admin_required
    def resolve_payments(self, info, **kwargs):
        return Payment.objects.all()

    @gql_store_admin_required
    def resolve_payment(self, info, id):
        try:
            payment = Payment.objects.get(id=id)
        except Payment.DoesNotExist:
            raise Exception("Payment not found")

        return payment