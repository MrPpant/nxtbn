import graphene
from graphene import relay
from graphene_django.types import DjangoObjectType

from nxtbn.core import CurrencyTypes
from nxtbn.core.models import CurrencyExchange, InvoiceSettings, SiteSettings

class CurrencyExchangeType(DjangoObjectType):
    db_id = graphene.ID(source='id')
    class Meta:
        model = CurrencyExchange
        fields = "__all__"
        interfaces = (relay.Node,)
        filter_fields = {
            'base_currency': ['exact', 'icontains'],
            'target_currency': ['exact', 'icontains'],
            'exchange_rate': ['exact', 'icontains'],
        }


class InvoiceSettingsType(DjangoObjectType):
    db_id = graphene.ID(source='id')
    class Meta:
        model = InvoiceSettings
        fields = "__all__"

class AdminCurrencyTypesEnum(graphene.ObjectType):
    value = graphene.String()
    label = graphene.String()
