from django.conf import settings
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers
from django.db import IntegrityError, transaction
from rest_framework.exceptions import ValidationError


from nxtbn.core import PublishableStatus
from nxtbn.core.utils import normalize_amount_currencywise
from nxtbn.filemanager.api.dashboard.serializers import ImageSerializer
from nxtbn.product.models import CategoryTranslation, CollectionTranslation, Color, Product, Category, Collection, ProductTag, ProductTagTranslation, ProductTranslation, ProductType, ProductVariant, Supplier, SupplierTranslation
from nxtbn.tax.models import TaxClass
from nxtbn.filemanager.models import Image

class TaxClassSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaxClass
        fields = '__all__'


class ProductTagSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductTag
        fields = '__all__'

        

class ProductTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductType
        fields = '__all__'

    def create(self, validated_data):
        # Create the ProductType instance
        return super().create(validated_data)
    
class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ('id', 'name', 'description', 'parent', 'subcategories',)
        read_only_fields = ('subcategories',)
        ref_name = 'category_dashboard_get'

class NameIDCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ('id', 'name',)

class BasicCategorySerializer(serializers.ModelSerializer):
    parent = NameIDCategorySerializer(read_only=True)
    class Meta:
        model = Category
        fields = ('id', 'name', 'description', 'parent', 'has_sub')
        read_only_fields = ('subcategories',)
        ref_name = 'category_dashboard_basic'

class RecursiveCategorySerializer(serializers.ModelSerializer):
    children = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = ('id', 'name', 'description', 'children')

    def get_children(self, obj):
        children = obj.subcategories.all()
        return RecursiveCategorySerializer(children, many=True).data

class CollectionSerializer(serializers.ModelSerializer):
    images_details = ImageSerializer(read_only=True, source='image')
    class Meta:
        model = Collection
        fields = (
            'id',
            'name',
            'description',
            'is_active',
            'image',
            'images_details',
        )
        ref_name = 'collection_dashboard_get'
        write_only_fields = ('image',)

class ProductVariantSerializer(serializers.ModelSerializer):
    is_default_variant = serializers.SerializerMethodField()
    product_name = serializers.SerializerMethodField()
    price = serializers.SerializerMethodField()
    image_details = ImageSerializer(read_only=True, source='image')

    class Meta:
        model = ProductVariant
        ref_name = 'product_variant_dashboard_get'
        fields = (
            'id',
            'alias',
            'product',
            'product_name',
            'name',
            'compare_at_price',
            'price',
            'cost_per_unit',
            'sku',
            'weight_value',
            # 'stock',
            # 'color_code',
            'track_inventory',
            'is_default_variant',
            'allow_backorder',
            'image_details',
        )

    def get_is_default_variant(self, obj):
        return obj.product.default_variant_id == obj.id
    
    def get_product_name(self, obj):
        return obj.product.name
    
    def get_price(self, obj):
        return normalize_amount_currencywise(obj.price, settings.BASE_CURRENCY)

class ProductSerializer(serializers.ModelSerializer):
    product_thumbnail = serializers.SerializerMethodField()
    category = serializers.StringRelatedField()
    product_price_range = serializers.SerializerMethodField()
    total_variant = serializers.SerializerMethodField()
    product_type = serializers.StringRelatedField()

    class Meta:
        model = Product 
        ref_name = 'product_dashboard_get'
        fields =  (
            'id',
            'name',
            'category',
            'status',
            'product_thumbnail',
            'product_price_range',
            'total_variant',
            'product_type',
        )

    def get_product_price_range(self, obj):
        return obj.product_price_range_humanized()
    
    def get_product_thumbnail(self, obj):
        return obj.product_thumbnail(self.context['request'])
    
    def get_total_variant(self, obj):
        return obj.variants.count()
    



class VariantCreatePayloadSerializer(serializers.Serializer):
    id = serializers.IntegerField(required=False)
    name = serializers.CharField(max_length=255, required=False, allow_null=True)
    # compare_at_price = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, allow_null=True)
    price = serializers.DecimalField(max_digits=10, decimal_places=3)
    cost_per_unit = serializers.DecimalField(max_digits=10, decimal_places=3)
    sku = serializers.CharField(max_length=255, required=False, allow_null=True)
    # stock = serializers.IntegerField(required=False)
    # weight_unit = serializers.CharField(max_length=10, required=False, allow_null=True)
    weight_value = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, allow_null=True)
    # color_code = serializers.CharField(max_length=7, required=False, allow_null=True)
    is_default_variant = serializers.BooleanField(default=False)
    track_inventory = serializers.BooleanField(default=False)
    allow_backorder = serializers.BooleanField(default=False)
    image = serializers.PrimaryKeyRelatedField(queryset=Image.objects.all(), required=False, allow_null=True)
    # def validate_sku(self, value):
    #     if ProductVariant.objects.filter(sku=value).exists():
    #         raise serializers.ValidationError("SKU already exists.")
    #     return value

    def validate_price(self, value):
        return normalize_amount_currencywise(value, settings.BASE_CURRENCY)


class ProductMutationSerializer(serializers.ModelSerializer):
    default_variant = ProductVariantSerializer(read_only=True)
    variants = ProductVariantSerializer(many=True, read_only=True)
    images_details = ImageSerializer(many=True, read_only=True, source='images')
    category_details = CategorySerializer(read_only=True, source='category')
    product_type_details = ProductTypeSerializer(read_only=True, source='product_type')
    variants_payload = VariantCreatePayloadSerializer(many=True, write_only=True)
    variant_to_delete = serializers.ListField(child=serializers.IntegerField(), write_only=True)
    tags = ProductTagSerializer(many=True, read_only=True)
    tags_payload = serializers.ListField(
        child=serializers.DictField(child=serializers.CharField(max_length=255)),
        write_only=True,
        required=False
    )

    class Meta:
        model = Product 
        ref_name = 'product_dashboard_get'
        fields =  (
            'id',
            'slug',
            'name',
            'summary',
            'description',
            'images',
            'images_details',
            'category',
            'supplier',
            'brand',
            'product_type',
            'related_to',
            'default_variant',
            'collections',
            # 'colors',
            'tax_class',
            'meta_title',
            'meta_description',
            'category_details',
            'product_type_details',
            'variants',
            'variants_payload',
            'variant_to_delete',
            'tags',
            'tags_payload',
            'status',
            'is_live',
        )
    
    def update(self, instance, validated_data):
        collection = validated_data.pop('collections', [])
        images = validated_data.pop('images', [])
        variants_payload = validated_data.pop('variants_payload', [])
        currency = validated_data.pop('currency', 'USD')
        category = validated_data.pop('category', None)
        product_type = validated_data.pop('product_type', None)
        related_to = validated_data.pop('related_to', None)
        supplier = validated_data.pop('supplier', None)
        variant_to_delete = validated_data.pop('variant_to_delete', [])
        tags_payload = validated_data.pop('tags_payload', [])
        tax_class = validated_data.pop('tax_class', None)

        with transaction.atomic():
            instance.collections.set(collection)
            instance.images.set(images)
            if category:
                instance.category = category
            if product_type:
                instance.product_type = product_type
            if related_to:
                instance.related_to = related_to
            if supplier:    
                instance.supplier = supplier
            if tax_class:
                instance.tax_class = tax_class

            for pattr, pvalue in validated_data.items():
                setattr(instance, pattr, pvalue)


        
            # Delete variants
            for variant_id in variant_to_delete:
                variant = ProductVariant.objects.get(id=variant_id)
                if instance.default_variant == variant:
                    raise serializers.ValidationError({'variant_to_delete': _('The default variant cannot be deleted.')})
                variant.delete()

            default_variant = None

            for variant_data in variants_payload:
                is_default_variant = variant_data.pop('is_default_variant', False)
                variant_id = variant_data.pop('id', None)
                if variant_id:
                    # Update existing variant
                    variant = ProductVariant.objects.get(id=variant_id, product=instance)
                    for attr, value in variant_data.items():
                        setattr(variant, attr, value)
                    variant.save()
                else:
                    # Create new variant
                    ProductVariant.objects.create(product=instance, **variant_data)

                if is_default_variant:
                    default_variant = variant

            # Ensure a default variant is set
            if default_variant:
                instance.default_variant = default_variant
            elif not instance.default_variant:
                raise serializers.ValidationError({'default_variant': _('A default variant must be set.')})
            
            if tags_payload:
                instance.tags.clear()
                for tag_payload in tags_payload:
                    tag, _ = ProductTag.objects.get_or_create(name=tag_payload['value'])
                    instance.tags.add(tag)

            if instance.status == PublishableStatus.PUBLISHED:
                instance.is_live = True
            else:
                instance.is_live = False
            
            if tax_class:
                tax_class_instance = TaxClass.objects.get(id=tax_class.id)
                if tax_class_instance:
                    instance.tax_class = tax_class_instance

        instance.save()
        return instance
    



class ProductCreateSerializer(serializers.ModelSerializer):
    variants = ProductVariantSerializer(many=True, read_only=True)
    variants_payload = VariantCreatePayloadSerializer(many=True, write_only=True)
    # currency = serializers.CharField(max_length=3, required=False, write_only=True)
    tags = ProductTagSerializer(many=True, read_only=True)
    tags_payload = serializers.ListField(child=serializers.CharField(max_length=255), write_only=True, required=False)
    class Meta:
        model = Product
        ref_name = 'product_dashboard_create'
        fields =  (
            'id',
            'slug',
            'name',
            'summary',
            'description',
            'images',
            'category',
            'supplier',
            'brand',
            'product_type',
            'related_to',
            'default_variant',
            'variants',
            'collections',
            'tax_class',

            # write only fields
            'variants_payload',
            # 'currency',
            'meta_title',
            'meta_description',
            'tags',
            'tags_payload',
            'status',
            'is_live',
        )


    def create(self, validated_data):
        collection = validated_data.pop('collections', [])
        images = validated_data.pop('images', [])
        variants_payload = validated_data.pop('variants_payload', [])
        tags_payload = validated_data.pop('tags_payload', [])
        currency = settings.BASE_CURRENCY
        tax_class = validated_data.pop('tax_class', None)

        if not variants_payload:
            raise ValidationError("At least one variant must be provided.")


        with transaction.atomic():
            instance = Product.objects.create(
                **validated_data,
                **{'created_by': self.context['request'].user}
            )

            instance.collections.set(collection)
            instance.images.set(images)

            # Create variants and set the first one as the default variant
            
            default_variant = None
            for i, variant_payload in enumerate(variants_payload):
                is_default_variant = variant_payload.pop('is_default_variant', False)
                variant = ProductVariant.objects.create(
                    product=instance,
                    currency=currency,
                    **variant_payload
                )
                if is_default_variant:
                    default_variant = variant

            if default_variant:
                instance.default_variant = default_variant

            if tags_payload:
                for tag_payload in tags_payload:
                    tag, _ = ProductTag.objects.get_or_create(name=tag_payload)
                    instance.tags.add(tag)

            if instance.status == PublishableStatus.PUBLISHED:
                instance.is_live = True
            else:
                instance.is_live = False

            if tax_class:
                instance.tax_class = TaxClass.objects.get(id=tax_class.id)

            instance.save()
            
        return instance
    
    def validate(self, attrs):
        variants_data = attrs.get('variants_payload', [])
        variant_skus = [variant.get('sku') for variant in variants_data if variant.get('sku')]

        # Check for duplicates within the provided SKUs
        if len(variant_skus) != len(set(variant_skus)):
            raise serializers.ValidationError("Duplicate SKUs found in variants. Each SKU must be unique.")

        # Validate each variant using VariantCreatePayloadSerializer
        for variant_data in variants_data:
            variant_serializer = VariantCreatePayloadSerializer(data=variant_data)
            if not variant_serializer.is_valid():
                raise serializers.ValidationError(variant_serializer.errors)
            
            sku = variant_data.get('sku')
            if variant_data.get('price') < 0:
                raise serializers.ValidationError(f"This variant({sku}) price is invalid !")

            # Check for existing SKUs in the database\
            if sku and ProductVariant.objects.filter(sku=sku).exists():
                raise serializers.ValidationError(f"SKU '{sku}' already exists. Please use a different SKU.")

        return super().validate(attrs)
    

class ColorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Color
        fields = '__all__'

    

class ProductWithVariantSerializer(serializers.ModelSerializer):
    variants = ProductVariantSerializer(many=True, read_only=True)
    default_variant = ProductVariantSerializer(read_only=True)
    product_thumbnail = serializers.SerializerMethodField()
    # stock = serializers.IntegerField(read_only=True, source='get_stock')
    class Meta:
        model = Product 
        ref_name = 'product_dashboard_variant_get'
        fields =  (
            'id',
            'alias',
            'slug',
            'name',
            'summary',
            'description',
            'images',
            'variants',
            'default_variant',
            'status',
            'is_live',
            'product_thumbnail',
            # 'stock',
        )

    def get_product_thumbnail(self, obj):
        # Access the request from the context, if available
        request = self.context.get('request')
        return obj.product_thumbnail(request) if request else None
    


class ProductStatusUpdateBulkSerializer(serializers.Serializer):
    product_ids = serializers.ListField(child=serializers.IntegerField(), required=True)
    status = serializers.ChoiceField(choices=PublishableStatus.choices, required=True)




class ProductVariantShortSerializer(serializers.ModelSerializer):

    class Meta:
        model = ProductVariant
        ref_name = 'product_variant_dashboard_short_get'
        fields = (
            'id',
            'alias',
            'name',
            'sku'
        )


class InventoryVariants(serializers.ModelSerializer):
    stock = serializers.SerializerMethodField()
    class Meta:
        model = ProductVariant
        ref_name = 'inventory_dashboard_variants_get'
        fields =  (
            'id',
            'name',
            'stock',
        )
    def get_stock(self, obj):
        return obj.get_stock_details()

class InventorySerializer(serializers.ModelSerializer):
    variants = InventoryVariants(many=True, read_only=True)

    class Meta:
        model = Product 
        ref_name = 'inventory_dashboard_get'
        fields =  (
            'id',
            'name',
            'status',
            'variants',
        )


class SupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = (
            'id',
            'name',
            'description',
            'meta_title',
            'meta_description',
            'slug'
        )

# =================================================
# Name id serializer start
# =================================================

class ProductMinimalSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product 
        ref_name = 'product_dashboard_minimal_get'
        fields =  (
            'id',
            'name',
        )
    

class CategoryNameSerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = (
            'id',
            'name',
        )

class CollectionNameSerializer(serializers.ModelSerializer):
    class Meta:
        model = Collection
        fields = (
            'id',
            'name',
        )

class ProductTagNameSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductTag
        fields = (
            'id',
            'name',
        )


class SupplierNameSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = (
            'id',
            'name',
        )



