import os
from django.db.models.signals import post_migrate
from django.dispatch import receiver
from nxtbn.core.models import InvoiceSettings, SiteSettings
from django.contrib.sites.models import Site

from nxtbn.plugins.utils import PLUGIN_BASE_DIR
from nxtbn.warehouse.models import Warehouse


@receiver(post_migrate)
def create_default_site_settings(sender, **kwargs):
    if SiteSettings.objects.count() == 0:
        site, created = Site.objects.get_or_create(
            domain="example.com", defaults={"name": "Default Site"}
        )
        
        SiteSettings.objects.create(
            site=site,
            site_name="nxtbn commerce",
            company_name="Default Company Name",
            contact_email="contact@example.com",
            contact_phone="123456789",
            address="Default Address",
        )
        print("SiteSettings instance created.")

    if InvoiceSettings.objects.count() == 0:
        site, created = Site.objects.get_or_create(
            domain="example.com", defaults={"name": "Default Site"}
        )
        
        InvoiceSettings.objects.create(
            store_name="nxtbn commerce",
            store_address="Default Store Address",
            city="Default City",
            country="Default Country",
            postal_code="123456",
            contact_email="invoice@example.com",
            is_default=True,
        )

    if Warehouse.objects.count() == 0:
        Warehouse.objects.create(
            name="Default Warehouse",
            location="Default Location",
            is_default=True,
        )
        print("Warehouse instance created.")

    # inpbuilt plugins
    # check if stripe, sslcommerz, plugins are exists in plugin directory
    if os.path.exists(PLUGIN_BASE_DIR):
        from nxtbn.plugins.models import Plugin
        from nxtbn.plugins import PluginType

        for plugin_name in ['stripe', 'sslcommerz']:
            plugin_dirs = [d for d in os.listdir(PLUGIN_BASE_DIR) if os.path.isdir(os.path.join(PLUGIN_BASE_DIR, d))]
            for plugin_name in plugin_dirs:
                plugin_dir = os.path.join(PLUGIN_BASE_DIR, plugin_name)
                if os.path.isdir(plugin_dir):
                    if not Plugin.objects.filter(name=plugin_name).exists():
                        Plugin.objects.create(
                            name=plugin_name,
                            plugin_type=PluginType.PAYMENT_PROCESSOR,
                        )
                else:
                    print(f"{plugin_name} plugin not found in {PLUGIN_BASE_DIR}.")
            