from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from rest_framework import serializers
from django.db import transaction


from nxtbn.discount.api.dashboard.serializers import PromoCodeBasicSerializer
from nxtbn.order import AddressType, OrderChargeStatus, OrderStatus, PaymentTerms, ReturnReceiveStatus, ReturnStatus
from nxtbn.order.api.storefront.serializers import AddressSerializer
from nxtbn.order.models import Address, Order, OrderDeviceMeta, OrderLineItem, ReturnLineItem, ReturnRequest
from nxtbn.payment.api.dashboard.serializers import BasicPaymentSerializer
from nxtbn.payment.models import Payment
from nxtbn.product.api.dashboard.serializers import ProductVariantSerializer
from nxtbn.product.models import ProductVariant
from nxtbn.users.models import User
from nxtbn.warehouse.utils import deduct_reservation_on_packed_for_dispatch, release_stock

class LineVariantSerializer(serializers.ModelSerializer):
    variant_thumbnail = serializers.SerializerMethodField()
    price = serializers.SerializerMethodField()
    class Meta:
        model = ProductVariant
        fields = ['alias', 'name', 'sku', "variant_thumbnail", "price",]

    def get_variant_thumbnail(self, obj):
        return obj.variant_thumbnail(self.context.get('request'))
    
    def get_price(self, obj):
        return obj.humanize_total_price()

class OrderLineItemSerializer(serializers.ModelSerializer):
    variant = LineVariantSerializer()
    total_price = serializers.SerializerMethodField()
    price_per_unit = serializers.SerializerMethodField()
    name = serializers.CharField(source='variant.get_descriptive_name')
    class Meta:
        model = OrderLineItem
        fields = ('id', 'quantity', 'price_per_unit', 'total_price', "variant", 'name',)

    def get_total_price(self, obj):
        return obj.humanize_total_price()
    
    def get_price_per_unit(self, obj):
        return obj.humanize_price_per_unit()


class OrderListSerializer(serializers.ModelSerializer):
    user = serializers.StringRelatedField()
    payment_method = serializers.CharField(source='get_payment_method')
    humanize_total_price = serializers.CharField()

    class Meta:
        model = Order
        fields = '__all__'




class OrderLineItemCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderLineItem
        fields = ['variant', 'quantity', 'price_per_unit', 'currency',]






class AddressMutationalSerializer(serializers.ModelSerializer):
    class Meta:
        model = Address
        fields = ['id', 'street_address', 'city', 'state', 'postal_code', 'country', 'phone_number', 'first_name', 'last_name', 'user']
        write_only_fields = ['user']

class CustomerCreateSerializer(serializers.ModelSerializer):
    address = AddressMutationalSerializer(write_only=True)

    class Meta:
        model = User
        fields = ['id','full_name', 'first_name', 'last_name', 'phone_number', 'email', 'address']
        read_only_fields = ['id', 'full_name',]

    @transaction.atomic
    def create(self, validated_data):
        address_data = validated_data.pop('address')
        email = validated_data.get('email')
        username = email.split('@')[0]
        if User.objects.filter(username=username).exists():
            username = f"{username}_{User.objects.count()}"
        
        validated_data['username'] = username
        
        user = User.objects.create(**validated_data)
        Address.objects.create(
            user=user, 
            address_type=AddressType.DSA_DBA,
            **address_data
        )
        return user

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("A customer with this email already exists.")
        return value
    

class OrderDeviceMetaSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderDeviceMeta
        exclude = ('id', 'order',)
class OrderDetailsSerializer(serializers.ModelSerializer):
    line_items = OrderLineItemSerializer(many=True, read_only=True)
    shipping_address = AddressSerializer()
    billing_address =  AddressSerializer()
    total_price = serializers.SerializerMethodField()
    total_price_without_symbol = serializers.SerializerMethodField()
    total_shipping_cost = serializers.SerializerMethodField()
    total_discounted_amount = serializers.SerializerMethodField()
    total_tax = serializers.SerializerMethodField()
    due = serializers.SerializerMethodField()
    overcharged_amount = serializers.CharField(source='get_overcharged_amount')
    payment_method = serializers.CharField(source='get_payment_method')
    promo_code = PromoCodeBasicSerializer()
    payments = BasicPaymentSerializer(many=True)
    total_paid_amount = serializers.SerializerMethodField()
    device_meta = OrderDeviceMetaSerializer()

    class Meta:
        model = Order
        fields = (
            'id',
            'alias',
            'user',
            'supplier',
            'total_price',
            'total_price_without_symbol',
            'total_shipping_cost',
            'total_discounted_amount',
            'total_tax',
            'due',
            'overcharged_amount',
            'customer_currency',
            'status',
            'authorize_status',
            'charge_status',
            'payment_method',
            'created_at',
            'shipping_address',
            'billing_address',
            'line_items',
            'promo_code',
            'gift_card',
            'due_date',
            'payment_term',
            'payments',
            'preferred_payment_method',
            'is_overdue',
            'total_paid_amount',
            'device_meta',
            'reservation_status',
            'comment',
        )

    def get_total_price(self, obj):
        return obj.humanize_total_price()
    
    def get_total_price_without_symbol(self, obj):
        return obj.humanize_total_price(locale='')
    
    def get_total_shipping_cost(self, obj):
        return obj.humanize_total_shipping_cost()
    
    def get_total_discounted_amount(self, obj):
        return obj.humanize_total_discounted_amount()
    
    def get_total_tax(self, obj):
        return obj.humanize_total_tax()
    
    def get_total_paid_amount(self, obj):
        return obj.humanize_total_paid_amount()
    
    def get_due(self, obj):
        return obj.get_due()
    

class OrderStatusUpdateSerializer(serializers.ModelSerializer):
    status = serializers.ChoiceField(choices=OrderStatus.choices)

    class Meta:
        model = Order
        fields = ['status']

    def validate(self, attrs):
        order = self.instance

        current_status = order.status
        new_status = attrs.get('status')

        if new_status == OrderStatus.CANCELLED:
            if current_status == OrderStatus.CANCELLED:
                raise serializers.ValidationError(_("Order is already cancelled."))
            elif current_status not in [OrderStatus.PENDING, OrderStatus.APPROVED]:
                raise serializers.ValidationError(_(f"{current_status} orders cannot be cancelled."))
        
        if new_status == OrderStatus.PACKED:
            if current_status != OrderStatus.APPROVED:
                raise serializers.ValidationError(_("Only pending orders can be started for packing."))
            
        if new_status == OrderStatus.SHIPPED:
            if current_status == OrderStatus.CANCELLED:
                raise serializers.ValidationError(_("Cancelled orders cannot be shipped."))
            if current_status in [OrderStatus.SHIPPED, OrderStatus.DELIVERED]:
                raise serializers.ValidationError(_("Order is already shipped or delivered."))
            if current_status == OrderStatus.RETURNED:
                raise serializers.ValidationError(_("Returned orders cannot be re-shipped."))
            if current_status != OrderStatus.PACKED:
                raise serializers.ValidationError(_("Order must be packed before it can be shipped."))
            
        if new_status == OrderStatus.DELIVERED:
            if current_status == OrderStatus.CANCELLED:
                raise serializers.ValidationError(_("Cancelled orders cannot be delivered."))
            if current_status in [OrderStatus.DELIVERED]:
                raise serializers.ValidationError(_("Order is already delivered."))
            if current_status != OrderStatus.SHIPPED:
                raise serializers.ValidationError(_("Order must be shipped before mark it as delivered."))
        
        return attrs
    
    def update(self, instance, validated_data):
        if validated_data.get('status') == OrderStatus.CANCELLED:
            release_stock(instance)

        if validated_data.get('status') == OrderStatus.PACKED:
            deduct_reservation_on_packed_for_dispatch(instance)
        
        return super().update(instance, validated_data)
    



class OrderPaymentUpdateSerializer(serializers.ModelSerializer):
    payment_term = serializers.ChoiceField(choices=PaymentTerms.choices, required=False)
    due_date = serializers.DateField(required=False, write_only=True)
    date_within = serializers.IntegerField(required=False, write_only=True)

    class Meta:
        model = Order
        fields = ['payment_term', 'due_date', 'date_within']

    def validate(self, attrs):
        order = self.instance
        if order.charge_status != OrderChargeStatus.DUE:
            raise serializers.ValidationError(_("Cannot change payment term for orders with charged funds."))
        return attrs
    
    def validate_due_date(self, value):
        if value and value < timezone.now().date():
            raise serializers.ValidationError(_("Due date cannot be in the past."))
        return value
    
    
    def update(self, instance, validated_data):
        payment_term = validated_data.get('payment_term')
        due_date = validated_data.get('due_date')
        date_within = validated_data.get('date_within')
        
        if payment_term:
            instance.payment_term = payment_term

        if date_within:
            # Ensure the calculated due date is explicitly converted to a `date` object
            instance.due_date = (timezone.now() + timezone.timedelta(days=date_within)).date()
            instance.payment_term = PaymentTerms.FIXED_DATE

        if due_date:
            instance.due_date = due_date
            instance.payment_term = PaymentTerms.FIXED_DATE

        instance.save()
        return instance


class OrderPaymentMethodSerializer(serializers.ModelSerializer):
        preferred_payment_method = serializers.CharField()

        class Meta:
            model = Order
            fields = ['preferred_payment_method']

        def validate(self, attrs):
            order = self.instance
            if order.charge_status != OrderChargeStatus.DUE:
                raise serializers.ValidationError(_("Cannot change payment method for orders with charged funds."))
              
            return attrs
        



class ReturnLineItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReturnLineItem
        fields = ['id', 'order_line_item', 'quantity', 'refunded_amount', 'destination',]
        read_only_fields = ['refunded_amount']

class ReturnRequestSerializer(serializers.ModelSerializer):
    line_items = ReturnLineItemSerializer(many=True, write_only=True)
    reason_details = serializers.CharField(required=False)
    order_alias = serializers.CharField(source='order.alias', read_only=True)
    approved_by = serializers.StringRelatedField(read_only=True)
    reviewed_by = serializers.StringRelatedField(read_only=True)
    initiated_by = serializers.StringRelatedField(read_only=True)
    class Meta:
        model = ReturnRequest
        fields = [
            'id',
            'initiated_by',
            'reviewed_by',
            'approved_by',
            'order',
            'order_alias',
            'status',
            'reason',
            'reason_details',
            'approved_at',
            'rejected_at', 
            'completed_at',
            'cancelled_at',
            'line_items'
        ]
        read_only_fields = [
            'id',
            'initiated_by',
            'reviewed_by',
            'approved_by', 
            'approved_at',
            'rejected_at',
            'completed_at',
            'cancelled_at',
            'status',
            'order_alias'
        ]

    def validate_line_items(self, line_items):
        """Validate each line item to ensure no active return request already exists."""
        for line_item_data in line_items:
            order_line_item = line_item_data['order_line_item']
            # Check for existing return requests regardless of status
            existing_return = ReturnLineItem.objects.filter(
                order_line_item=order_line_item
            ).exists()
            
            if existing_return:
                raise serializers.ValidationError(
                    f"A return request for the product '{order_line_item.get_descriptive_name()}' is already initiated or resolved."
                )
        return line_items
    
    def validate(self, attrs):
        order = attrs.get('order')
        if order.status != OrderStatus.DELIVERED:
            raise serializers.ValidationError("Return requests can only be initiated for delivered orders.")
        return attrs
    
    def create(self, validated_data):
        line_items_data = validated_data.pop('line_items')
        # Set intiated_by to the current user
        validated_data['initiated_by'] = self.context['request'].user
        return_request = ReturnRequest.objects.create(**validated_data)
        order = validated_data.get('order')
        order.status = OrderStatus.PENDING_RETURN
        order.save()
        for line_item_data in line_items_data:
            ReturnLineItem.objects.create(return_request=return_request, **line_item_data)
        return return_request


class ReturnLineItemDetailsSerializer(serializers.ModelSerializer):
    order_line_item = OrderLineItemSerializer()
    destination = serializers.SerializerMethodField()
    class Meta:
        model = ReturnLineItem
        fields = ['id', 'order_line_item', 'quantity', 'refunded_amount', 'receiving_status', 'destination']
        read_only_fields = ['refunded_amount']

    def get_destination(self, obj):
        return obj.destination.name



class ReturnRequestDetailsSerializer(serializers.ModelSerializer):
    line_items = ReturnLineItemDetailsSerializer(many=True)
    reason_details = serializers.CharField(required=False)
    order_alias = serializers.CharField(source='order.alias', read_only=True)
    approved_by = serializers.StringRelatedField(read_only=True)
    reviewed_by = serializers.StringRelatedField(read_only=True)
    initiated_by = serializers.StringRelatedField(read_only=True)
    class Meta:
        model = ReturnRequest
        fields = [
            'id',
            'initiated_by',
            'reviewed_by',
            'approved_by',
            'order',
            'order_alias',
            'status',
            'reason',
            'reason_details',
            'approved_at',
            'rejected_at', 
            'completed_at',
            'cancelled_at',
            'line_items'
        ]
        
class ReturnRequestStatusUpdateSerializer(serializers.ModelSerializer):
    status = serializers.ChoiceField(choices=ReturnStatus.choices)

    class Meta:
        model = ReturnRequest
        fields = ['status']
    
    def validate_status(self, value):
        if self.instance.status in [ReturnStatus.COMPLETED, ReturnStatus.CANCELLED]:
            raise serializers.ValidationError(_("Cannot update status of a resolved return request."))
        return value
    
    def update(self, instance, validated_data):
        status = validated_data.get('status')
        if status == ReturnStatus.APPROVED:
            instance.approved_by = self.context['request'].user
            instance.approved_at = timezone.now()
        elif status == ReturnStatus.REJECTED:
            instance.rejected_at = timezone.now()
        elif status == ReturnStatus.COMPLETED:
            instance.completed_at = timezone.now()
            order = instance.order
            order.status = OrderStatus.RETURNED
            order.save()
        elif status == ReturnStatus.CANCELLED:
            instance.cancelled_at = timezone.now()
        elif status == ReturnStatus.REVIEWED:
            instance.reviewed_by = self.context['request'].user

        instance.status = status
        instance.save()
        return instance
    

class ReturnLineItemStatusUpdateSerializer(serializers.Serializer):
    receiving_status = serializers.ChoiceField(choices=ReturnReceiveStatus.choices)
    line_item_ids = serializers.ListField(
        child=serializers.IntegerField(),
        allow_empty=False,
        help_text="List of ReturnLineItem IDs to update"
    )

class ReturnRequestBulkUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=ReturnStatus.choices)
    request_ids = serializers.ListField(
        child=serializers.IntegerField(),
        allow_empty=False,
        help_text="List of ReturnRequest IDs to update"
    )

    def validate_request_ids(self, value):
        if ReturnRequest.objects.filter(id__in=value).count() != len(value):
            raise serializers.ValidationError("One or more return requests do not exist.")
        
        completed_requests = ReturnRequest.objects.filter(id__in=value, status=ReturnStatus.COMPLETED)
        if completed_requests.exists():
            raise serializers.ValidationError("One or more return requests are completed and cannot be updated.")
        
        return value
   