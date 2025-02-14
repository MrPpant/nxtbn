from django.conf import settings
import os

from django.utils.translation import gettext_lazy as _
from rest_framework import serializers
from django.db import transaction

from nxtbn.core.models import InvoiceSettings, SiteSettings

class SiteSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = SiteSettings
        fields = '__all__'


class InvoiceSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = InvoiceSettings
        fields = [
            'store_name',
            'store_address',
            'city',
            'country',
            'postal_code',
            'contact_email',
            'is_default',
        ]

    

class InvoiceSettingsLogoSerializer(serializers.ModelSerializer):
    class Meta:
        model = InvoiceSettings
        fields = ['id', 'logo']
        read_only_fields = ['id']