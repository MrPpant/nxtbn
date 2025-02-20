import graphene
from graphene_django.types import DjangoObjectType
from nxtbn.product.models import Category, CategoryTranslation, Collection, CollectionTranslation, ProductTag, ProductTagTranslation, ProductTranslation, Product, ProductVariant, ProductVariantTranslation, Supplier, SupplierTranslation
from graphene_django.filter import DjangoFilterConnectionField
from graphene import relay

from nxtbn.product.admin_filters import CategoryFilter, CategoryTranslationFilter, CollectionFilter, CollectionTranslationFilter, ProductFilter, ProductTagsFilter, ProductTranslationFilter, TagsTranslationFilter


class ProductVariantNonPaginatedType(DjangoObjectType):
    db_id = graphene.Int(source="id")
    display_name = graphene.String()
    humanize_price = graphene.String()
    variant_thumbnail = graphene.String()
    variant_thumbnail_xs = graphene.String()

    def resolve_humanize_price(self, info):
        return self.humanize_total_price()
    
    def resolve_variant_thumbnail(self, info):
        return self.variant_thumbnail(info.context)
    
    def resolve_variant_thumbnail_xs(self, info):
        return self.variant_thumbnail_xs(info.context)
    class Meta:
        model = ProductVariant
        fields = (
            'name',
            'sku',
            'track_inventory',
            'product',
            'price',
            'variant_thumbnail',
            'alias',
        )

    def resolve_display_name(self, info):
        if self.name:
            return self.name
        
        if self.sku:
            return self.product.name + " - " + self.sku
        
        return self.product.name + " - " + self.sku



class ProductGraphType(DjangoObjectType):
    description_html = graphene.String()
    db_id = graphene.Int(source="id")
    all_variants = graphene.List(ProductVariantNonPaginatedType)
    product_thumbnail = graphene.String()
    product_thumbnail_xs = graphene.String()

    def resolve_all_variants(self, info):
        return self.variants.all()
    
    def resolve_product_thumbnail(self, info):
        return self.product_thumbnail(info.context)
    
    def resolve_product_thumbnail_xs(self, info):
        return self.product_thumbnail_xs(info.context)
    class Meta:
        model = Product
        fields = (
            'id',
            'slug',
            'name',
            'name_when_in_relation',
            'summary',
            'description',
            'images',
            'category',
            'supplier',
            'brand',
            'product_type',
            'default_variant',
            'collections',
            'tags',
            'tax_class',
            'related_to',
            'variants',
            'meta_title',
            'meta_description',
            'all_variants',
            'product_thumbnail',
        )

        interfaces = (relay.Node,)
        filterset_class = ProductFilter

    def resolve_description_html(self, info):
        return self.description_html()
    

class CollectionType(DjangoObjectType):
    db_id = graphene.Int(source="id")
    class Meta:
        model = Collection
        fields = (
            'name',
            'slug',
            'description',
            'meta_title',
            'meta_description',
            'image',
        )
        interfaces = (relay.Node,)
        filterset_class = CollectionFilter


class CategoryChildInfoType(graphene.ObjectType):
    has_child = graphene.Boolean()

class CategoryType(DjangoObjectType):
    db_id = graphene.Int(source="id")
    child_info = graphene.Field(CategoryChildInfoType)
    class Meta:
        model = Category
        fields = (
            'name',
            'slug',
            'description',
            'meta_title',
            'meta_description',
            'parent',
        )
        interfaces = (relay.Node,)
        filterset_class = CategoryFilter

    def resolve_child_info(self, info):
        has_child = self.subcategories.exists()
        return CategoryChildInfoType(has_child=has_child)
    




class ProductTagType(DjangoObjectType):
    db_id = graphene.Int(source="id")
    class Meta:
        model = ProductTag
        fields = (
            'name',
        )
        interfaces = (relay.Node,)
        filterset_class = ProductTagsFilter


class SupplierType(DjangoObjectType):
    db_id = graphene.Int(source="id")
    class Meta:
        model = Supplier
        fields = (
            'name',
        )
        interfaces = (relay.Node,)
        filter_fields = ('name',)



class ProductVariantAdminType(DjangoObjectType):
    db_id = graphene.Int(source="id")
    display_name = graphene.String()
    humanize_price = graphene.String()
    variant_thumbnail = graphene.String()

    def resolve_humanize_price(self, info):
        return self.humanize_total_price()
    
    def resolve_variant_thumbnail(self, info):
        return self.variant_thumbnail()
    class Meta:
        model = ProductVariant
        fields = (
            'name',
            'sku',
            'track_inventory',
            'product',
            'price',
            'variant_thumbnail',
        )
        interfaces = (relay.Node,)
        filter_fields = ('name', 'sku', 'track_inventory', 'product', 'price')

    def resolve_display_name(self, info):
        if self.name:
            return self.name
        
        if self.sku:
            return self.product.name + " - " + self.sku
        
        return self.product.name + " - " + self.sku




class CategoryHierarchicalType(DjangoObjectType):
    db_id = graphene.Int(source="id")
    name = graphene.String()
    description = graphene.String()
    meta_title = graphene.String()
    meta_description = graphene.String()

    # Recursive field for subcategories
    children = graphene.List(lambda: CategoryHierarchicalType)
    
    def resolve_children(self, info):
        return self.subcategories.all()
    
    class Meta:
        model = Category
        fields = (
            'id',
            'name',
            'description',
            'meta_title',
            'meta_description',
            'children',
        )
        interfaces = (relay.Node,)
        filterset_class = CategoryFilter


# =====================================
# All translation types
# =====================================

class ProductTranslationType(DjangoObjectType):
    description_html = graphene.String()
    base_product_id = graphene.Int()
    class Meta:
        model = ProductTranslation
        fields = (
            'name',
            'summary',
            'description',
            'language_code',
            'meta_title',
            'meta_description',
        )
        interfaces = (relay.Node,)
        filterset_class = ProductTranslationFilter

    def resolve_description_html(self, info):
        return self.description_html()
    
    def resolve_base_product_id(self, info):
        return self.product_id
    

class CategoryTranslationType(DjangoObjectType):
    db_id = graphene.Int(source="id")
    class Meta:
        model = CategoryTranslation
        fields = (
            'name',
            'description',
            'meta_title',
            'meta_description',
        )
        interfaces = (relay.Node,)
        filterset_class = CategoryTranslationFilter

class SupplierTranslationType(DjangoObjectType):
    db_id = graphene.Int(source="id")
    class Meta:
        model = SupplierTranslation
        fields = (
            'name',
            'description',
            'meta_title',
            'meta_description',
        )


class ProductVariantTranslationType(DjangoObjectType):
    db_id = graphene.Int(source="id")
    class Meta:
        model = ProductVariantTranslation
        fields = (
            'name',
        )


class ProductTagTranslationType(DjangoObjectType):
    db_id = graphene.Int(source="id")
    class Meta:
        model = ProductTagTranslation
        fields = (
            'name',
        )

        interfaces = (relay.Node,)
        filterset_class = TagsTranslationFilter


class CollectionTranslationType(DjangoObjectType):
    db_id = graphene.Int(source="id")
    class Meta:
        model = CollectionTranslation
        fields = (
            'name',
            'description',
            'meta_title',
            'meta_description',
        )
        interfaces = (relay.Node,)
        filterset_class = CollectionTranslationFilter