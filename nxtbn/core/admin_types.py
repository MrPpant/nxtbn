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
    logo = graphene.String()

    def resolve_logo(self, info):
        if self.logo:
            return info.context.build_absolute_uri(self.logo.url)
        return None
    class Meta:
        model = InvoiceSettings
        fields = "__all__"
        interfaces = (relay.Node,)
        filter_fields = {
            'store_name': ['exact', 'icontains'],
        }


class InvoiceSettingsInput(graphene.InputObjectType):
    store_name = graphene.String()
    store_address = graphene.String()
    city = graphene.String()
    country = graphene.String()
    postal_code = graphene.String()
    contact_email = graphene.String()
    contact_phone = graphene.String()
    is_default = graphene.Boolean()


class AdminCurrencyTypesEnum(graphene.ObjectType):
    value = graphene.String()
    label = graphene.String()
