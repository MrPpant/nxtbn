import django_filters as filters
from nxtbn.product.models import Category, CategoryTranslation, Collection, CollectionTranslation, Product, ProductTag, ProductTagTranslation, ProductTranslation, Supplier
from django.db.models import Q


class ProductFilter(filters.FilterSet):
    search = filters.CharFilter(method='filter_search', label='Search Across Multiple Fields')
    name = filters.CharFilter(lookup_expr='icontains')
    summary = filters.CharFilter(lookup_expr='icontains')
    description = filters.CharFilter(lookup_expr='icontains')
    category = filters.ModelChoiceFilter(field_name='category', queryset=Category.objects.all())
    category_name = filters.CharFilter(field_name='category__name', lookup_expr='icontains')
    supplier = filters.ModelChoiceFilter(field_name='supplier', queryset=Supplier.objects.all())
    brand = filters.CharFilter(lookup_expr='icontains')
    related_to = filters.CharFilter(field_name='related_to__name', lookup_expr='icontains')
    collection = filters.ModelChoiceFilter(field_name='collections', queryset=Collection.objects.all())
    variant_id = filters.CharFilter(field_name='variants__id', lookup_expr='exact')
    variant_alias = filters.CharFilter(field_name='variants__alias', lookup_expr='icontains')
    variant_sku = filters.CharFilter(field_name='variants__sku', lookup_expr='icontains')
    variant_name = filters.CharFilter(field_name='variants__name', lookup_expr='icontains')

    class Meta:
        model = Product
        fields = (
            'id',
            'alias',
            'name', 
            'summary', 
            'description', 
            'category', 
            'category_name', 
            'supplier', 
            'brand', 
            'related_to', 
            'search', 
            'collection', 
            'variant_id', 
            'variant_alias', 
            'variant_sku', 
            'variant_name'
        )

    def filter_search(self, queryset, name, value):
        """
        Custom search method to search across multiple fields: name, description, and alias.
        """
        lookup = Q(name__icontains=value) | Q(description__icontains=value) | Q(alias__icontains=value)
        return queryset.filter(lookup)
    
class ProductTranslationFilter(filters.FilterSet):
    name = filters.CharFilter(lookup_expr='icontains')
    summary = filters.CharFilter(lookup_expr='icontains')
    description = filters.CharFilter(lookup_expr='icontains')

    class Meta:
        model = ProductTranslation
        fields = ('name', 'summary', 'description',)

class CategoryTranslationFilter(filters.FilterSet):
    name = filters.CharFilter(lookup_expr='icontains')

    class Meta:
        model = CategoryTranslation
        fields = ('name',)


class CollectionTranslationFilter(filters.FilterSet):
    name = filters.CharFilter(lookup_expr='icontains')

    class Meta:
        model = CollectionTranslation
        fields = ('name',)


class TagsTranslationFilter(filters.FilterSet):
    name = filters.CharFilter(lookup_expr='icontains')

    class Meta:
        model = ProductTagTranslation
        fields = ('name',)

class CategoryFilter(filters.FilterSet):
    name = filters.CharFilter(lookup_expr='icontains')
    parent = filters.ModelChoiceFilter(field_name='parent', queryset=Category.objects.all())
    is_top_level = filters.BooleanFilter(field_name='parent', lookup_expr='isnull')

    class Meta:
        model = Category
        fields = ('name', 'parent', 'is_top_level',)


class CollectionFilter(filters.FilterSet):
    name = filters.CharFilter(lookup_expr='icontains')

    class Meta:
        model = Collection
        fields = ('name',)


class ProductTagsFilter(filters.FilterSet):
    name = filters.CharFilter(lookup_expr='icontains')

    class Meta:
        model = ProductTag
        fields = ('name',)