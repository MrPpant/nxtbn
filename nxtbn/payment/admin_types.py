from django.conf import settings
import graphene
from graphene_django import DjangoObjectType
from graphene import relay

from nxtbn.payment.models import Payment

class PaymentType(DjangoObjectType):
    db_id = graphene.Int(source='id')
    
    class Meta:
        model = Payment
        fields = (
            'id',
            'user',
            'order',
            'payment_method',
            'transaction_id',
            'payment_status',
            'is_successful',
            'currency',
            'payment_amount',
            'gateway_response_raw',
            'paid_at',
            'payment_plugin_id',
            'gateway_name',
        )

        interfaces = (relay.Node,)
        filter_fields = (
            'order__alias',
        )
