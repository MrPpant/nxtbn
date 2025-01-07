from django.conf import settings
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers
from django.db import transaction

from nxtbn.core.models import CurrencyExchange
from nxtbn.core.utils import apply_exchange_rate, get_in_user_currency
from nxtbn.product.api.dashboard.serializers import RecursiveCategorySerializer
from nxtbn.filemanager.api.dashboard.serializers import ImageSerializer
from nxtbn.product.models import Product, Collection, Category, ProductVariant

from nxtbn.core.currency.backend import currency_Backend

class CategorySerializer(RecursiveCategorySerializer):
    pass

class CollectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Collection
        fields = ('id', 'name', 'description', 'is_active', 'image',)


class ProductVariantSerializer(serializers.ModelSerializer):
    price = serializers.SerializerMethodField()
    class Meta:
        model = ProductVariant
        fields = [
            'id',
            'alias',
            'name',
            'price',
        ]
 
    def get_price(self, obj):
        target_currency = self.context['request'].currency
        converted_price = apply_exchange_rate(obj.price, self.context['exchange_rate'], target_currency, 'en_US')
        return converted_price

class ProductWithVariantSerializer(serializers.ModelSerializer):
    variants = ProductVariantSerializer(many=True)
    product_thumbnail = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = (
            'id',
            'name',
            'summary',
            'category',
            'brand',
            'slug',
            'variants',
            'product_thumbnail'
        )

    def get_product_thumbnail(self, obj):
        return obj.product_thumbnail(self.context['request'])
    

class ProductWithDefaultVariantSerializer(serializers.ModelSerializer):
    product_thumbnail = serializers.SerializerMethodField()
    default_variant = ProductVariantSerializer(read_only=True)
    texts = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = (
            'id',
            'texts',
            'slug',
            'default_variant',
            'product_thumbnail'
        )

    def get_product_thumbnail(self, obj):
        return obj.product_thumbnail(self.context['request'])
    
    def get_texts(self, obj):
        request = self.context.get('request')
        if settings.USE_I18N:
            if settings.LANGUAGE_CODE != request.LANGUAGE_CODE:
                # Try fetching translation for the requested language
                translation_obj = obj.translations.filter(language_code=request.LANGUAGE_CODE).first()
                if translation_obj:
                    return {
                        'name': translation_obj.name,
                        'summary': translation_obj.summary,
                    }
                # If no translation exists, fallback to default # TODO (could be logged for debugging)
                return {
                    'name': obj.name,
                    'summary': obj.summary,
                }

            # If the language code matches, return translated texts
            try:
                return obj.translated_texts()
            except AttributeError:
                # Fallback in case translated_texts method is missing or not implemented
                return {
                    'name': obj.name,
                    'summary': obj.summary,
                }

        # If internationalization is not enabled, return default texts
        return {
            'name': obj.name,
            'summary': obj.summary,
        }
    
class ProductWithDefaultVariantImageListSerializer(serializers.ModelSerializer):
    images = ImageSerializer(many=True)

    class Meta:
        model = Product
        fields = (
            'id',
            'name',
            'summary',
            'slug',
            'default_variant',
            'images',
        )
    
class ProductSlugSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = ('id', 'slug', 'name', 'product_thumbnail',)


class ProductDetailSerializer(serializers.ModelSerializer):
    variants = ProductVariantSerializer(many=True)
    description_html = serializers.CharField(read_only=True)
    product_thumbnail = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = (
            'id',
            'name',
            'summary',
            'description_html',
            'brand',
            'category',
            'collections',
            'created_by',
            'variants',
            'meta_title',
            'meta_description',
            'slug',
            'product_thumbnail',
        )

    def get_product_thumbnail(self, obj):
        return obj.product_thumbnail(self.context['request'])
    

class ProductDetailImageListSerializer(serializers.ModelSerializer):
    variants = ProductVariantSerializer(many=True)
    description_html = serializers.CharField(read_only=True)
    images = ImageSerializer(many=True)

    class Meta:
        model = Product
        fields = (
            'id',
            'name',
            'summary',
            'description_html',
            'brand',
            'category',
            'collections',
            'created_by',
            'variants',
            'meta_title',
            'meta_description',
            'slug',
            'images',
        )


class ProductSlugRelatedNameSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = ('id', 'slug', 'name_when_in_relation',)

class ProductDetailWithRelatedLinkMinimalSerializer(serializers.ModelSerializer):
    variants = ProductVariantSerializer(many=True)
    related_links = ProductSlugRelatedNameSerializer(many=True, source='related_to')
    product_thumbnail = serializers.SerializerMethodField()
    description_html = serializers.CharField(read_only=True)
    class Meta:
        model = Product
        fields = (
            'id',
            'name',
            'summary',
            'description',
            'brand',
            'category',
            'collections',
            'created_by',
            'variants',
            'related_links',
            'meta_title',
            'meta_description',
            'slug',
            'product_thumbnail',
            'description_html',
        )

    def get_product_thumbnail(self, obj):
        return obj.product_thumbnail(self.context['request'])


class ProductDetailWithRelatedLinkImageListMinimalSerializer(serializers.ModelSerializer):
    variants = ProductVariantSerializer(many=True)
    related_links = ProductSlugRelatedNameSerializer(many=True, source='related_to')
    images = ImageSerializer(many=True)
    class Meta:
        model = Product
        fields = (
            'id',
            'name',
            'summary',
            'description',
            'brand',
            'category',
            'collections',
            'images',
            'created_by',
            'variants',
            'related_links',
            'meta_title',
            'meta_description',
            'slug',
            'description_html',
        )

    def get_product_thumbnail(self, obj):
        return obj.product_thumbnail(self.context['request'])
