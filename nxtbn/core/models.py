import uuid
from django.conf import settings
from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError

from django_extensions.db.fields import AutoSlugField
from nxtbn.core import CurrencyTypes, MoneyFieldTypes, PublishableStatus
from nxtbn.core.mixin import MonetaryMixin
from nxtbn.users.admin import User
from django.contrib.sites.models import Site


from money.money import Currency, Money
from babel.numbers import get_currency_precision, format_currency


def no_nested_values(value):
    if isinstance(value, dict):
        for k, v in value.items():
            if isinstance(v, dict):
                raise ValidationError(f"Nested values are not allowed: key '{k}' has a nested dictionary.")
    else:
        raise ValidationError("Value must be a dictionary.")

#============================
# Abstract Base Model Start
# ==========================

class AbstractUUIDModel(models.Model):
    alias = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)

    class Meta:
        abstract = True


    
class AbstractBaseUUIDModel(AbstractUUIDModel):
    created_at = models.DateTimeField(auto_now_add=True)
    last_modified = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

class AbstractBaseModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    last_modified = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

class NameDescriptionAbstract(models.Model):
    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True, null=True)

    class Meta:
        abstract = True

    def __str__(self):
        return self.name
class PublishableModel(AbstractBaseUUIDModel):
    published_date = models.DateTimeField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=PublishableStatus.choices, default=PublishableStatus.DRAFT)
    is_live = models.BooleanField(default=False)

    def make_live(self):
        if not self.published_date:
            self.published_date = timezone.now()
        self.is_live = True
        self.save()

    def make_inactive(self):
        self.is_live = False
        self.published_date = None
        self.save()

    def clean(self):

        if self.is_live and not self.published_date:
            raise ValidationError("Published content must have a publication date.")

    class Meta:
        abstract = True



class AbstractSEOModel(models.Model):
    meta_title = models.CharField(
        max_length=800, blank=True, null=True, help_text="Title for search engine optimization."
    )
    meta_description = models.CharField(
        max_length=350, blank=True, null=True, help_text="Description for search engines."
    )
    slug = AutoSlugField(populate_from='name', unique=True)

    class Meta:
        abstract = True
        verbose_name = "SEO Information"
        verbose_name_plural = "SEO Information"

class AbstractAddressModels(AbstractBaseModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, related_name="+")
    street_address = models.CharField(max_length=255)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    postal_code = models.CharField(max_length=20)
    country = models.CharField(max_length=100)

    class Meta:
        abstract = True

    

class AbstractMetadata(models.Model):
    internal_metadata = models.JSONField( # Don't expose it publicly, to store some internal refference
        blank=True, null=True, default=dict, validators=[no_nested_values]
    )
    metadata = models.JSONField(blank=True, null=True, default=dict, validators=[no_nested_values])

    class Meta:
        abstract = True


#============================
# Abstract Base Model end
# ==========================


#===============================
# Non-Abstract Base Model start
# ==============================


class SiteSettings(models.Model):
    site = models.OneToOneField(Site, on_delete=models.CASCADE, null=True, blank=True, help_text="The site this configuration applies to.")
    site_name = models.CharField(max_length=100, blank=True, null=True, help_text="Name of the site.")
    company_name = models.CharField(max_length=100, blank=True, null=True, help_text="Name of the company.")
    contact_email = models.EmailField(blank=True, null=True, help_text="Contact email for site administrators.")
    contact_phone = models.CharField(max_length=20, blank=True, null=True, help_text="Contact phone number for site administrators.")
    address = models.TextField(blank=True, null=True, help_text="Physical address of the site.")
    logo = models.ImageField(upload_to='logos/', blank=True, null=True, help_text="Logo of the site.")

    def clean(self):
        # Check if there is already an instance of SiteSettings
        if SiteSettings.objects.exists() and not self.pk:
            raise ValidationError("Only one instance of SiteSettings is allowed.")
        super().clean()

    def save(self, *args, **kwargs):
        # Ensure full clean method is called
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.site_name or "Site Settings"

    class Meta:
        verbose_name = "Site Setting"
        verbose_name_plural = "Site Settings"



class CurrencyExchange(AbstractBaseModel):
    base_currency = models.CharField(max_length=3, choices=CurrencyTypes.choices) # base currency always should come from settings.BASE_CURRENCY

    target_currency = models.CharField(max_length=3, choices=CurrencyTypes.choices) # TODO: ADD VALIDATOR SO THAT CANT ADD CURRENC THAT IS NOT ALLOWED CURRENCY
    exchange_rate = models.DecimalField(
        decimal_places=4,
        max_digits=12,
    )

    class Meta:
        ordering = ('-last_modified',)
        unique_together = ('base_currency', 'target_currency',)

    

    def clean(self) -> None:
        if self.base_currency != settings.BASE_CURRENCY:
            raise ValidationError(f"In base currency, {settings.BASE_CURRENCY} allowed only as Base currency is {settings.BASE_CURRENCY} in in settings.ALLOWED_CURRENCIES")
        
        if not self.target_currency in settings.ALLOWED_CURRENCIES:
            raise ValidationError(f"{self.target_currency} is not allowed currency in settings.ALLOWED_CURRENCIES")
        return super().clean()
    
    def humanize_rate(self):
        return f'{self.base_currency}1  TO  {self.target_currency}{self.exchange_rate}'

    def __str__(self):
        return f"{self.base_currency} to {self.target_currency}"