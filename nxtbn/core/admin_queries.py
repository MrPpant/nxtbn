from django.conf import settings
import graphene
from graphql import GraphQLError

from nxtbn.core import CurrencyTypes
from nxtbn.core.admin_permissions import gql_store_admin_required
from nxtbn.core.admin_types import AdminCurrencyTypesEnum, CurrencyExchangeType, InvoiceSettingsType
from nxtbn.core.models import CurrencyExchange, InvoiceSettings
from graphene_django.filter import DjangoFilterConnectionField


class AdminCoreQuery(graphene.ObjectType):
    currency_exchanges = DjangoFilterConnectionField(CurrencyExchangeType)
    currency_exchange = graphene.Field(CurrencyExchangeType, id=graphene.ID(required=True))
    allowed_currency_list = graphene.List(AdminCurrencyTypesEnum)
    default_invoice_settings = graphene.Field(InvoiceSettingsType)

    @gql_store_admin_required
    def resolve_currency_exchanges(self, info, **kwargs):
        return CurrencyExchange.objects.all()
    
    def resolve_currency_exchange(self, info, id):
        try:
            return CurrencyExchange.objects.get(id=id)
        except CurrencyExchange.DoesNotExist:
            return None
        
    @gql_store_admin_required
    def resolve_allowed_currency_list(self, info):
        allowed_currency_list = settings.ALLOWED_CURRENCIES

        if not allowed_currency_list:
            raise GraphQLError("No allowed currencies found in Server settings.")

        return [
            AdminCurrencyTypesEnum(value=currency[0], label=currency[1])
            for currency in CurrencyTypes.choices
            if currency[0] in allowed_currency_list
        ]
    
    @gql_store_admin_required
    def resolve_default_invoice_settings(self, info):
        site_id = getattr(settings, 'SITE_ID', 1)
        return InvoiceSettings.objects.get(site__id=site_id)
