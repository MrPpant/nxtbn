import json
from django.db import models
from django.core.validators import MinValueValidator
from decimal import Decimal
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from django.db.models import Sum
from babel.numbers import get_currency_precision, format_currency
from django_extensions.db.fields import AutoSlugField


from django.utils.html import escape, format_html


from nxtbn.core import CurrencyTypes, MoneyFieldTypes
from nxtbn.core.mixin import MonetaryMixin
from nxtbn.core.models import AbstractMetadata, AbstractSEOModel, AbstractTranslationModel, AbstractUUIDModel, PublishableModel, AbstractBaseUUIDModel, AbstractBaseModel, NameDescriptionAbstract, no_nested_values
from nxtbn.filemanager.models import Document, Image
from nxtbn.product import DimensionUnits, StockStatus, WeightUnits
from nxtbn.product.utils import json_to_html
from nxtbn.tax.models import TaxClass
from nxtbn.users.admin import User

class Supplier(NameDescriptionAbstract, AbstractSEOModel):
    slug = AutoSlugField(populate_from='name', unique=True)
    pass

class Color(AbstractBaseModel): # TO DO: Remove this model, unnecessary, Decided with critically analyze. Can handle with product.related_to field
    code = models.CharField(max_length=7, unique=True)
    name = models.CharField(max_length=20, unique=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = _("Color")
        verbose_name_plural = _("Colors")

class Category(NameDescriptionAbstract, AbstractSEOModel):
    slug = AutoSlugField(populate_from='name', unique=True)
    parent = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='subcategories'
    )

    def has_sub(self):
        return self.subcategories.exists()

    def get_family_tree(self):
        family_tree = []
        current = self
        depth = 0
        while current is not None:
            family_tree.insert(0, {'depth': depth, 'name': current.name})
            current = current.parent
            depth += 1
        return family_tree

    class Meta:
        verbose_name = _("Category")
        verbose_name_plural = _("Categories")
    
    def __str__(self):
        return self.name

    def clean(self):
        """Validate that category depth does not exceed 2 levels."""
        if self._get_depth() > 2:
            raise ValidationError("Category depth must not exceed 2 levels.")

    def _get_depth(self):
        """Recursively determine the depth of the category."""
        depth = 0
        current = self
        while current.parent:
            depth += 1
            current = current.parent
        return depth

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

class Collection(NameDescriptionAbstract, AbstractSEOModel):
    slug = AutoSlugField(populate_from='name', unique=True)
    created_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL,
        null=True,
        related_name='collections_created'
    )
    last_modified_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='collections_modified'
    )
    is_active = models.BooleanField(default=True)
    image = models.ForeignKey(Image, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        verbose_name = _("Collection")
        verbose_name_plural = _("Collections")

    def __str__(self):
        return self.name

class ProductTag(models.Model):
    name = models.CharField(unique=True, max_length=50)

class ProductType(models.Model):
    name = models.CharField(unique=True, max_length=50)
    taxable = models.BooleanField(default=False)
    physical_product = models.BooleanField(default=False) # weight store in grams
    track_stock = models.BooleanField(default=False)
    has_variant = models.BooleanField(default=False)
   

    def __str__(self):
        fields = [self.name]
        if self.taxable:
            fields.append("Taxable")
        if self.physical_product:
            fields.append("Physical Product")
        if self.track_stock:
            fields.append("Track Stock")
        if self.has_variant:
            fields.append("Has Variant")
        return " | ".join(fields)
    
    # TO DO: class Meta: # Handle unique together with each field except name

class Product(PublishableModel, AbstractMetadata, AbstractSEOModel):
    slug = AutoSlugField(populate_from='name', unique=True)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='products_created')
    last_modified_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='products_modified', null=True, blank=True)
    name = models.CharField(max_length=255, help_text="The name of the product.")
    name_when_in_relation = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text=(
            "The name used for this product when it is related to another product. "
            "For example, if you have a black t-shirt with size variants and a white t-shirt with size variants, "
            "you can refer to them as 'black' and 'white' respectively."
            "This field is only used when the product is related to another product."
        )
    )
    summary = models.TextField(max_length=500, help_text="A brief summary of the product.")
    description = models.TextField(max_length=5000)
    images = models.ManyToManyField(Image, blank=True)
    category = models.ForeignKey(
        'Category',
        on_delete=models.PROTECT, 
        related_name='products'
    )
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name='+', null=True, blank=True)
    brand = models.CharField(max_length=100, blank=True, null=True)
    product_type = models.ForeignKey(ProductType, related_name='product', on_delete=models.PROTECT, help_text="The type of product.")
    default_variant = models.OneToOneField(
        "ProductVariant",
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name='+'
    )
    collections = models.ManyToManyField(Collection, blank=True, related_name='products_in_collection')
    tags = models.ManyToManyField(ProductTag, blank=True)
    tax_class = models.ForeignKey(TaxClass, on_delete=models.PROTECT, related_name='products', null=True, blank=True) # null for tax exempt products
    related_to = models.ManyToManyField(
        "self",
        blank=True,
        help_text=(
            "Related products. For example, if you have a product that is a t-shirt, "
            "each product can have variants by size and color. In this case, you can "
            "relate all the products by color. This field is not intended for "
            "recommendation engines."
        )
    )

    class Meta:
        ordering = ('name',)

    def description_html(self):
        return json_to_html(self.description)

    def get_stock_details(self):
        from nxtbn.warehouse.models import Stock
        
        stock_data = Stock.objects.filter(
            product_variant__product=self
        ).aggregate(
            total_stock=Sum('quantity'),
            total_reserved=Sum('reserved')
        )
        
        # Extract and handle possible None values
        total_stock = stock_data.get('total_stock') or 0
        total_reserved = stock_data.get('total_reserved') or 0
        available_for_sell = total_stock - total_reserved

        # Return as an object
        return {
            'total_stock': total_stock,
            'total_reserved': total_reserved,
            'available_for_sell': available_for_sell
        }

    def product_thumbnail(self, request):
        """
        Returns the URL of the first image associated with the product. 
        If no image is available, returns None.
        """
        first_image = self.images.first()  # Get the first image if it exists
        if first_image and hasattr(first_image, 'image') and first_image.image:
            image_url = first_image.image.url
            full_url = request.build_absolute_uri(image_url)
            return full_url
        return None
    
    def product_thumbnail_xs(self, request):
        """
        Returns the URL of the first image associated with the product. 
        If no image is available, returns None.
        """
        first_image = self.images.first()  # Get the first image if it exists
        if first_image and hasattr(first_image, 'image_xs') and first_image.image_xs:
            image_url = first_image.image_xs.url
            full_url = request.build_absolute_uri(image_url)
            return full_url
        
        if first_image and hasattr(first_image, 'image') and first_image.image:
            image_url = first_image.image.url
            full_url = request.build_absolute_uri(image_url)
            return full_url

        return None


    
    def product_price_range(self):
        """
        Returns the price range of the product variants.
        """
        price_range = self.variants.aggregate(min_price=models.Min('price'), max_price=models.Max('price'))
        return price_range
    
    def product_price_range_humanized(self, locale='en_US'):
        """
        Returns the price range of the product variants in a human-readable format.
        """

        if not self.default_variant:
            return "No variants available."

        if not self.variants.exists():
            return "No variants available."
        

        price_range = self.product_price_range()
        min_price = price_range['min_price']
        max_price = price_range['max_price']
        
        if min_price == max_price:
            min_price = Decimal('0.00')
        
        if locale:
            return f"{format_currency(min_price, self.default_variant.currency, locale=locale)} - {format_currency(max_price, self.default_variant.currency, locale=locale)}"
        return f"{min_price} - {max_price}"
        
    
    def get_absolute_url(self):
        """
        Returns the absolute URL for this Product instance. 
        This URL is intended for use within the application, not for API endpoints.
        It is designed to be used in Jinja templates, and is automatically included in the sitemap.
        """
        return reverse("product_detail", args=[self.slug])
    
        
    
    
    def __str__(self):
        return self.name


class ProductVariant(MonetaryMixin, AbstractUUIDModel, AbstractMetadata, models.Model):
    money_validator_map = {
        "price": {
            "currency_field": "currency",
            "type": MoneyFieldTypes.UNIT,
            "require_base_currency": True,
        },
        "compare_at_price": {
            "currency_field": "currency",
            "type": MoneyFieldTypes.UNIT,
            "require_base_currency": True,
        }
    }

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='variants')
    name = models.CharField(max_length=255, blank=True, null=True)
    image = models.ForeignKey(Image, null=True, blank=True, on_delete=models.SET_NULL)

    compare_at_price = models.DecimalField(max_digits=12, decimal_places=3, validators=[MinValueValidator(Decimal('0.01'))], null=True, blank=True) # TO DO: Handle this field which is still not used in the project.

    currency = models.CharField(
        max_length=3,
        default=CurrencyTypes.USD,
        choices=CurrencyTypes.choices,
    )
    price = models.DecimalField(max_digits=12, decimal_places=3, validators=[MinValueValidator(Decimal('0.01'))])

    cost_per_unit = models.DecimalField(max_digits=12, decimal_places=3, validators=[MinValueValidator(Decimal('0.01'))])

  
    track_inventory = models.BooleanField(default=False)
    allow_backorder = models.BooleanField(default=False, help_text="Allow orders even if out of stock.")

    sku = models.CharField(max_length=50, unique=True, null=True, blank=True)
   
    weight_value = models.DecimalField( # stores weight in grams
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True
    )
    purchase_limit_per_order = models.PositiveIntegerField(null=True, blank=True, help_text="Maximum number of units that can be purchased in a single order.")
    
    def get_stock_details(self):
        stock_data = self.warehouse_stocks.aggregate(
            total_stock=Sum('quantity'),
            total_reserved=Sum('reserved')
        )

        # Extract and handle possible None values
        total_stock = stock_data.get('total_stock') or 0
        total_reserved = stock_data.get('total_reserved') or 0
        available_for_sell = total_stock - total_reserved

        return {
            'total_stock': total_stock,
            'total_reserved': total_reserved,
            'available_for_sell': available_for_sell
        }

    def get_descriptive_name(self):
        parts = [self.product.name]
        
        if self.name:
            parts.append(self.name)
        
        if self.product.brand:
            parts.append(self.product.brand)
        
        if self.weight_value:
            parts.append(f"Weight: {self.weight_value}")
        
        dimensions = []
        if 'height' in self.metadata:
            dimensions.append(f"Height: {self.metadata['height']}")
        if 'width' in self.metadata:
            dimensions.append(f"Width: {self.metadata['width']}")
        if 'depth' in self.metadata:
            dimensions.append(f"Depth: {self.metadata['depth']}")
        if dimensions and 'dimension_type' in self.metadata:
            parts.append(f"Dimensions: {' x '.join(dimensions)} {self.metadata['dimension_type']}")
        
        return " - ".join(parts)
    
    def get_descriptive_name_minimal(self):
        parts = [self.product.name]
        
        if self.name:
            parts.append(self.name)
        
        return " - ".join(parts)
    
    def humanize_total_price(self, locale='en_US'):
        if locale:
            return format_currency(self.price, self.currency, locale=locale)
        return self.price
    
    def variant_thumbnail(self, request):
        """
        Returns the URL of the first image associated with the product variant. 
        If no image is available, returns None.
        """
        if self.image and hasattr(self.image, 'image') and self.image.image:
            image_url = self.image.image.url
            full_url = request.build_absolute_uri(image_url)
            return full_url
        
        if self.product.images.exists():
            first_image = self.product.images.first()
            if first_image and hasattr(first_image, 'image') and first_image.image:
                image_url = first_image.image.url
                full_url = request.build_absolute_uri(image_url)
                return full_url
        return None
    
    def variant_thumbnail_xs(self, request):
        """
        Returns the URL of the first image associated with the product variant. 
        If no image is available, returns None.
        """
        if self.image and hasattr(self.image, 'image_xs') and self.image.image_xs:
            image_url = self.image.image_xs.url
            full_url = request.build_absolute_uri(image_url)
            return full_url
        
        if self.product.images.exists():
            first_image = self.product.images.first()
            if first_image and hasattr(first_image, 'image') and first_image.image:
                image_url = first_image.image.url
                full_url = request.build_absolute_uri(image_url)
                return full_url
        return None
        
        
    def get_valid_stock(self): # stocks that available for sell
        stock_data = self.warehouse_stocks.aggregate(
            total_stock=Sum('quantity'),
            total_reserved=Sum('reserved')
        )

        # Extract and handle possible None values
        total_stock = stock_data.get('total_stock') or 0
        total_reserved = stock_data.get('total_reserved') or 0
        available_for_sell = total_stock - total_reserved
        return available_for_sell
            




    class Meta:
        ordering = ('price',)  # Order by price ascending
    
    def save(self, *args, **kwargs):
        self.validate_amount()
        super(ProductVariant, self).save(*args, **kwargs)

    def __str__(self):
        variant_name = self.name if self.name else 'Default'
        return f"{self.product.name} - {variant_name} (SKU: {self.sku})"
    
    def clean(self):
        if self.attributes:
            if 'height' in self.attributes or 'width' in self.attributes or 'depth' in self.attributes:
                if not 'dimension_type' in self.attributes.keys():
                    raise ValidationError("Dimension type is required if dimensions are provided.")
                if self.attributes['dimension_type'] not in DimensionUnits.choices.keys():
                    raise ValidationError("Invalid dimension type, must be one of: {}".format(DimensionUnits.choices.keys()))
                



# ==================================================================
# Translation Models
# ==================================================================

class CategoryTranslation(AbstractTranslationModel, AbstractSEOModel):
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='translations')
    name = models.CharField(max_length=255)
    description = models.TextField(max_length=5000)

    class Meta:
        unique_together = ('language_code', 'category')

    def __str__(self):
        return self.name
    

class CollectionTranslation(AbstractTranslationModel, AbstractSEOModel):
    collection = models.ForeignKey(Collection, on_delete=models.CASCADE, related_name='translations')
    name = models.CharField(max_length=255)
    description = models.TextField(max_length=5000)

    class Meta:
        unique_together = ('language_code', 'collection')

    def __str__(self):
        return self.name
    

class ProductTranslation(AbstractTranslationModel, AbstractSEOModel):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='translations')
    name = models.CharField(max_length=255)
    name_when_in_relation = models.CharField(max_length=255, blank=True, null=True)
    summary = models.TextField(max_length=500)
    description = models.TextField(max_length=5000)

    class Meta:
        unique_together = ('language_code', 'product')

    def __str__(self):
        return self.name
    

class ProductVariantTranslation(AbstractTranslationModel):
    product_variant = models.ForeignKey(ProductVariant, on_delete=models.CASCADE, related_name='translations')
    name = models.CharField(max_length=255)

    class Meta:
        unique_together = ('language_code', 'product_variant')

    def __str__(self):
        return self.name
    

class SupplierTranslation(AbstractTranslationModel, AbstractSEOModel):
    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE, related_name='translations')
    name = models.CharField(max_length=255)
    description = models.TextField(max_length=5000)

    class Meta:
        unique_together = ('language_code', 'supplier')

    def __str__(self):
        return self.name
    

class ProductTagTranslation(AbstractTranslationModel, AbstractSEOModel):
    product_tag = models.ForeignKey(ProductTag, on_delete=models.CASCADE, related_name='translations')
    name = models.CharField(max_length=255)

    class Meta:
        unique_together = ('language_code', 'product_tag')

    def __str__(self):
        return self.name
    