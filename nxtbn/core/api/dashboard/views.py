import importlib
import os
import zipfile
import shutil
import subprocess

from django.conf import settings
import tempfile

from django.forms import ValidationError
import requests
from rest_framework import generics, status
from django.contrib.sites.shortcuts import get_current_site
from rest_framework.response import Response
from django.utils.translation import gettext_lazy as _
from rest_framework.permissions  import AllowAny
from rest_framework.exceptions import APIException, NotFound

from rest_framework.views import APIView
from rest_framework.response import Response

from django.core.files.storage import FileSystemStorage
from rest_framework.parsers import MultiPartParser
from rest_framework.parsers import JSONParser

from rest_framework import serializers

from nxtbn.core import LanguageChoices
from nxtbn.core.admin_permissions import GranularPermission, IsStoreAdmin, IsStoreStaff
from nxtbn.core.api.dashboard.serializers import InvoiceSettingsLogoSerializer, InvoiceSettingsSerializer, SiteSettingsSerializer
from nxtbn.core.models import InvoiceSettings, SiteSettings
from nxtbn.users import UserRole



class SiteSettingsView(generics.RetrieveUpdateAPIView):
    permission_classes = (IsStoreAdmin,)
    queryset = SiteSettings.objects.all()
    serializer_class = SiteSettingsSerializer


    def get_object(self):
        # Get the current site
        current_site = get_current_site(self.request)

        # Find the SiteSettings object for the current site
        try:
            return SiteSettings.objects.get(site=current_site)
        except SiteSettings.DoesNotExist:
            raise NotFound("Site settings for the current site do not exist.")
        

class InvoiceSettingsView(generics.RetrieveUpdateAPIView):
    permission_classes = (IsStoreAdmin,)
    queryset = InvoiceSettings.objects.all()
    serializer_class = InvoiceSettingsSerializer
    lookup_field = 'pk'
        


class InvoiceSettingsLogoUploadAPIView(generics.UpdateAPIView):
    permission_classes = (IsStoreAdmin,)
    queryset = InvoiceSettings.objects.all()
    serializer_class = InvoiceSettingsLogoSerializer
    lookup_field = 'id'

    def partial_update(self, request, *args, **kwargs):
        kwargs['partial'] = True
        return self.update(request, *args, **kwargs)


class LanguageChoicesAPIView(APIView):
    permission_classes = (IsStoreStaff,)
    def get(self, request, *args, **kwargs):
        languages = [
            {"value": lang_value, "label": lang_label}
            for lang_value, lang_label in LanguageChoices.choices
        ]
        return Response(languages, status=status.HTTP_200_OK)