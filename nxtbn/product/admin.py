from django import forms
from django.contrib import admin
from nxtbn.product.models import Category,Collection, Color,Product, ProductVariant

# Register your models here.

class CategoryAdmin(admin.ModelAdmin):
    list_display = ('id','name', 'parent', 'family_tree')
    list_filter = ('parent',)
    search_fields = ('name', 'description')

    def family_tree(self, obj):
        family_tree = obj.get_family_tree()
        category_names = [item['name'] for item in family_tree]
        return ' > '.join(category_names)

admin.site.register(Category,CategoryAdmin)


class CollectionAdmin(admin.ModelAdmin):

    list_display = ('id','name', 'is_active', 'created_by', 'last_modified_by')
    list_filter = ('is_active',)
    search_fields = ('name', 'description')
    readonly_fields = ('last_modified_by',) 
    fieldsets = (
        (None, {
            'fields': ('name', 'description', 'is_active', 'image')
        }),
        ('Metadata', {
            'fields': ('created_by', 'last_modified_by')
        })
    )


admin.site.register(Collection,CollectionAdmin)




class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 1

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    inlines = [ProductVariantInline]
    list_display = ('id','name', "slug", 'category', 'supplier',)
    list_filter = ('category', 'supplier',)
    search_fields = ('name', 'summary', 'description')
    readonly_fields = ('last_modified_by',) 


@admin.register(ProductVariant)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('id', 'product', 'name', 'currency', 'price', "currency")


class ColorAdminForm(forms.ModelForm):
    class Meta:
        model = Color
        fields = '__all__'
        widgets = {
            'code': forms.TextInput(attrs={'type': 'color'}),
        }
        
@admin.register(Color)
class ColorAdmin(admin.ModelAdmin):
    form = ColorAdminForm
    list_display = ('name', 'code')
    search_fields = ('name', 'code')