from django.conf import settings
import graphene

from nxtbn.core import CurrencyTypes
from nxtbn.core.admin_permissions import gql_required_perm
from nxtbn.core.admin_types import CurrencyExchangeType, InvoiceSettingsInput, InvoiceSettingsType
from nxtbn.core.models import CurrencyExchange, InvoiceSettings
from nxtbn.users import UserRole

class CurrencyExchangeInput(graphene.InputObjectType):
    base_currency = graphene.String(required=True)
    target_currency = graphene.String(required=True)
    exchange_rate = graphene.Decimal(required=True)

class CurrencyExchangeUpdateInput(graphene.InputObjectType):
    exchange_rate = graphene.Decimal(required=True)

class CreateCurrencyExchange(graphene.Mutation):
    class Arguments:
        input = CurrencyExchangeInput(required=True)

    currency_exchange = graphene.Field(CurrencyExchangeType)

    @gql_required_perm(CurrencyExchange, 'add_currencyexchange')
    @staticmethod
    def mutate(root, info, input):
        # Validate base_currency
        base_currency = input.base_currency
        if base_currency != settings.BASE_CURRENCY:
            raise Exception("Base currency must match settings.BASE_CURRENCY")

        # Validate target_currency
        allowed_currencies = [choice[0] for choice in CurrencyTypes.choices]
        if input.target_currency not in allowed_currencies:
            raise Exception(f"Target currency '{input.target_currency}' is not allowed.")

        currency_exchange = CurrencyExchange.objects.create(
            base_currency=base_currency,
            target_currency=input.target_currency,
            exchange_rate=input.exchange_rate,
        )
        return CreateCurrencyExchange(currency_exchange=currency_exchange)


class UpdateCurrencyExchange(graphene.Mutation):
    class Arguments:
        id = graphene.ID(required=True)
        input = CurrencyExchangeUpdateInput(required=True)

    currency_exchange = graphene.Field(CurrencyExchangeType)

    @gql_required_perm(CurrencyExchange, 'change_currencyexchange')
    @staticmethod
    def mutate(root, info, id, input):
        try:
            currency_exchange = CurrencyExchange.objects.get(pk=id)
        except CurrencyExchange.DoesNotExist:
            raise Exception("CurrencyExchange not found.")

        currency_exchange.exchange_rate = input.exchange_rate or currency_exchange.exchange_rate
        currency_exchange.save()
        return UpdateCurrencyExchange(currency_exchange=currency_exchange)

class DeleteCurrencyExchange(graphene.Mutation):
    class Arguments:
        id = graphene.ID(required=True)  # ID of the record to be deleted

    success = graphene.Boolean()  # Indicate whether the operation was successful

    @gql_required_perm(CurrencyExchange, 'delete_currencyexchange')
    @staticmethod
    def mutate(root, info, id):
        try:
            currency_exchange = CurrencyExchange.objects.get(pk=id)
        except CurrencyExchange.DoesNotExist:
            raise Exception("CurrencyExchange not found.")

        currency_exchange.delete()  # Delete the record
        return DeleteCurrencyExchange(success=True)  # Return success
    


class CreateInvoiceSettings(graphene.Mutation):
    class Arguments:
        input = InvoiceSettingsInput()

    invoice_settings = graphene.Field(InvoiceSettingsType)

    @gql_required_perm(InvoiceSettings, 'add_invoicesettings')
    @staticmethod
    def mutate(root, info, input):
        invoice_settings = InvoiceSettings.objects.create(
            store_name=input.store_name,
            store_address=input.store_address,
            city=input.city,
            country=input.country,
            postal_code=input.postal_code,
            contact_email=input.contact_email,
            contact_phone=input.contact_phone,
            is_default=input.is_default,
        )
        return CreateInvoiceSettings(invoice_settings=invoice_settings)


class CoreMutation(graphene.ObjectType):
    update_exchange_rate = UpdateCurrencyExchange.Field()
    create_exchange_rate = CreateCurrencyExchange.Field()
    delete_exchange_rate = DeleteCurrencyExchange.Field()
    create_invoice_settings = CreateInvoiceSettings.Field()