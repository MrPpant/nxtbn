from django.contrib import admin
from nxtbn.cart.models import  CartItem

class CartItemAdmin(admin.ModelAdmin):
    list_display = ('id', 'cart')
    list_filter = ('cart__user',)
    search_fields = ('id', 'cart')

admin.site.register(CartItem, CartItemAdmin)