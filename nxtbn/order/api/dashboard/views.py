from django.conf import settings
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.response import Response
from django.utils.translation import gettext_lazy as _
from rest_framework.permissions  import AllowAny
from rest_framework.exceptions import APIException
from rest_framework.exceptions import ValidationError

from rest_framework.views import APIView
from django.db.models import Sum, Count, F
from django.db import transaction
from django.db.models.functions import TruncMonth, TruncDay, TruncWeek, TruncHour

from django.utils import timezone

from datetime import timedelta

from decimal import Decimal

from rest_framework import filters as drf_filters
import django_filters
from django_filters import rest_framework as filters

from nxtbn.core.admin_permissions import GranularPermission, CommonPermissions, has_required_perm
from nxtbn.core.enum_perms import PermissionsEnum
from nxtbn.core.utils import to_currency_unit
from nxtbn.order.proccesor.views import OrderProccessorAPIView
from nxtbn.order import OrderAuthorizationStatus, OrderChargeStatus, OrderStatus, ReturnStatus
from nxtbn.order.models import Order, OrderLineItem, ReturnLineItem, ReturnRequest
from nxtbn.payment import PaymentMethod
from nxtbn.payment.models import Payment
from nxtbn.product.models import ProductVariant
from nxtbn.users import UserRole
from nxtbn.users.admin import User
from .serializers import CustomerCreateSerializer, OrderDetailsSerializer, OrderListSerializer, OrderPaymentUpdateSerializer, OrderStatusUpdateSerializer, OrderPaymentMethodSerializer, ReturnLineItemSerializer, ReturnLineItemStatusUpdateSerializer, ReturnRequestBulkUpdateSerializer, ReturnRequestDetailsSerializer, ReturnRequestSerializer, ReturnRequestStatusUpdateSerializer
from nxtbn.core.paginator import NxtbnPagination
from datetime import datetime

from babel.numbers import get_currency_precision

from calendar import monthrange, day_name
from nxtbn.warehouse.utils import adjust_stocks_returned_items
from nxtbn.warehouse.utils import deduct_reservation_on_packed_for_dispatch, release_stock
from nxtbn.order import OrderStockReservationStatus, ReturnReceiveStatus




class OrderFilter(filters.FilterSet):
    status = filters.ChoiceFilter(choices=OrderStatus.choices)
    charge_status = filters.ChoiceFilter(choices=OrderChargeStatus.choices)
    authorize_status = filters.ChoiceFilter(choices=OrderAuthorizationStatus.choices)
    currency = filters.CharFilter(field_name='currency', lookup_expr='iexact')
    payment_method = django_filters.ChoiceFilter(choices=PaymentMethod.choices, method='filter_by_payment_method')
    created_at = filters.DateFromToRangeFilter(field_name='created_at') # eg. ?created_at_after=2023-09-01&created_at_before=2023-09-12
    min_order_value = django_filters.NumberFilter(field_name='total_price', lookup_expr='gte', method='filter_min_order_value')
    max_order_value = django_filters.NumberFilter(field_name='total_price', lookup_expr='lte', method='filter_max_order_value')

    class Meta:
        model = Order
        fields = [
            'status',
            'charge_status',
            'authorize_status',
            'currency',
            'payment_method',
            'created_at',
            'min_order_value',
            'max_order_value',
        ]

    def filter_by_payment_method(self, queryset, name, value):
        return queryset.filter(payments__payment_method=value).distinct()
    
    def filter_min_order_value(self, queryset, name, value):
        """
        Filter orders with total_price greater than or equal to the specified min_order_value in units.
        """
        if value is not None:
            precision = get_currency_precision(settings.BASE_CURRENCY)
            min_value_in_subunits = int(value * (10 ** precision))
            return queryset.filter(total_price__gte=min_value_in_subunits)
        return queryset

    def filter_max_order_value(self, queryset, name, value):
        """
        Filter orders with total_price less than or equal to the specified max_order_value in units.
        """
        if value is not None:
            precision = get_currency_precision(settings.BASE_CURRENCY)
            max_value_in_subunits = int(value * (10 ** precision))
            return queryset.filter(total_price__lte=max_value_in_subunits)
        return queryset


class OrderListView(generics.ListAPIView):
    permission_classes = (CommonPermissions, )
    queryset = Order.objects.all()
    serializer_class = OrderListSerializer
    pagination_class = NxtbnPagination

    filter_backends = [
        django_filters.rest_framework.DjangoFilterBackend,
        drf_filters.SearchFilter,
        drf_filters.OrderingFilter
    ]
    filterset_class = OrderFilter
    search_fields = ['alias', 'id', 'user__username', 'supplier__name']
    ordering_fields = ['created_at']


class OrderDetailView(generics.RetrieveAPIView):
    permission_classes = (CommonPermissions, )
    queryset = Order.objects.all()
    serializer_class = OrderDetailsSerializer
    lookup_field = 'alias'


comparables = ['today', 'this week', 'this month', 'this year',]

compare_opposite_title_tr = {
    'today': _('Yesterday'),
    'this week': _('Last Week'),
    'this month': _('Last Month'),
    'this year': _('Last Year'),
}

compare_opposite_title = {
    'today': 'Yesterday',
    'this week': 'Last Week',
    'this month': 'Last Month',
    'this year': 'Last Year',
}


class BasicStatsView(APIView):
    permission_classes = (CommonPermissions, )
    def get(self, request):
        # Get start and end dates from query parameters
        start_date_str = request.query_params.get('start_date')
        end_date_str = request.query_params.get('end_date')
        range_name = request.query_params.get('range_name', None)

        # Parse dates if provided, or default to all-time if not provided
        start_date = datetime.strptime(start_date_str, "%Y-%m-%d") if start_date_str else None
        end_date = datetime.strptime(end_date_str, "%Y-%m-%d") + timedelta(days=1) if end_date_str else timezone.now() + timedelta(days=1) # Add 1 day to adjust for end date as inclusive


        # Set a previous period for calculating percentage change
        if start_date and end_date:
            previous_start_date = start_date - (end_date - start_date)
            previous_end_date = start_date
        else:
            previous_end_date = end_date - timedelta(days=7)
            previous_start_date = previous_end_date - timedelta(days=7)

        # Filter current period orders
        orders_queryset = Order.objects.all() # All orders including return and cancelled orders
        orders_without_cancelation_and_return = Order.objects.exclude(status=OrderStatus.CANCELLED).exclude(status=OrderStatus.RETURNED)
        if start_date:
            orders_queryset = orders_queryset.filter(created_at__gte=start_date)
            orders_without_cancelation_and_return = orders_without_cancelation_and_return.filter(created_at__gte=start_date)
        if end_date:
            orders_queryset = orders_queryset.filter(created_at__lte=end_date)
            orders_without_cancelation_and_return = orders_without_cancelation_and_return.filter(created_at__lte=end_date)

        # Total Orders
        total_orders = orders_queryset.count()

        # Total Sale (sum of total_price in Orders)
        total_sale = orders_queryset.aggregate(total=Sum(F('total_price_without_tax')))['total'] or 0      

        net_sales = orders_without_cancelation_and_return.aggregate(net_total=Sum(F('total_price_without_tax')))['net_total'] or 0
        total_variants_sold = OrderLineItem.objects.filter(
            order__created_at__gte=start_date, order__created_at__lte=end_date
        ).aggregate(total=Sum('quantity'))['total'] or 0
        data = {
            'percetage_change_preiod_title': '',
            'sales': { # total sales including return and cancelled orders and excluding tax
                'amount': to_currency_unit(total_sale, settings.BASE_CURRENCY, locale='en_US'),
                'last_percentage_change': ''
            },
            'orders': {
                'amount': total_orders,
                'last_percentage_change': ''
            },
            'variants': {
                'amount': total_variants_sold,
            },
            'net_sales': { # total sales excluding return and cancelled orders and excluding tax
                'amount': to_currency_unit(net_sales, settings.BASE_CURRENCY, locale='en_US'),
                'last_percentage_change': ''
            }
        }


        # Calculate totals for the previous period
        if range_name and  range_name.lower() in comparables:
            previous_orders_queryset = Order.objects.filter(created_at__gte=previous_start_date, created_at__lte=previous_end_date)
            previous_total_orders = previous_orders_queryset.count()
            previous_total_sale = previous_orders_queryset.aggregate(total=Sum(F('total_price')))['total'] or 0

            previous_payments_queryset = Payment.objects.filter(created_at__gte=previous_start_date, created_at__lte=previous_end_date)
            previous_net_sales = previous_payments_queryset.aggregate(net_total=Sum(F('payment_amount')))['net_total'] or 0

            # Calculate percentage changes
            orders_last_percentage_change = round(((total_orders - previous_total_orders) / previous_total_orders * 100), 2) if previous_total_orders > 0 else 0
            sales_last_percentage_change = round(((total_sale - previous_total_sale) / previous_total_sale * 100), 2) if previous_total_sale > 0 else 0
            net_sales_last_percentage_change = round(((net_sales - previous_net_sales) / previous_net_sales * 100), 2) if previous_net_sales > 0 else 0

            data['sales']['last_percentage_change'] = sales_last_percentage_change
            data['orders']['last_percentage_change'] = orders_last_percentage_change
            data['net_sales']['last_percentage_change'] = net_sales_last_percentage_change


            
            data['percetage_change_preiod_title'] = compare_opposite_title_tr[range_name.lower()]
        

        return Response(data)


class OrderOverviewStatsView(APIView):
    permission_classes = (CommonPermissions, )
    """
    View to provide an overview of order statistics within a specified date range.
    Methods:
    -------
    get(request):
        Handles GET requests to retrieve order statistics such as pending, delivered, returned, and cancelled orders.
        Query Parameters:
            - start_date (str): The start date for the statistics in 'YYYY-MM-DD' format.
            - end_date (str): The end date for the statistics in 'YYYY-MM-DD' format.
            - range_name (str, optional): The name of the date range.
    """

      

    def get(self, request):
        start_date_str = request.query_params.get('start_date')
        end_date_str = request.query_params.get('end_date')
        range_name = request.query_params.get('range_name', None)

        # Parse dates if provided, or default to all-time if not provided
        start_date = datetime.strptime(start_date_str, "%Y-%m-%d") if start_date_str else None
        end_date = datetime.strptime(end_date_str, "%Y-%m-%d") + timedelta(days=1) if end_date_str else timezone.now() + timedelta(days=1)

        order_pending = Order.objects.filter(status=OrderStatus.PENDING).count()

        all_orders_in_period = Order.objects.filter(created_at__gte=start_date, created_at__lte=end_date)
        order_delivered = all_orders_in_period.filter(status=OrderStatus.DELIVERED).aggregate(total=Sum(F('total_price_without_tax')))['total'] or 0
        order_returned = all_orders_in_period.filter(status=OrderStatus.RETURNED).aggregate(total=Sum(F('total_price_without_tax')))['total'] or 0
        order_cancelled = all_orders_in_period.filter(status=OrderStatus.CANCELLED).aggregate(total=Sum(F('total_price_without_tax')))['total'] or 0

        last_order = Order.objects.all().last()
        data = {
            'order_pending': {
                'amount': order_pending,
                'last_order': last_order.created_at if last_order else None
            },
            'order_delivered': {
                'amount': to_currency_unit(order_delivered, settings.BASE_CURRENCY, locale='en_US'),
                'last_percentage_change': ''
            },
            'order_returned': {
                'amount': to_currency_unit(order_returned, settings.BASE_CURRENCY, locale='en_US'),
                'last_percentage_change': ''
            },
            'order_cancelled': {
                'amount': to_currency_unit(order_cancelled, settings.BASE_CURRENCY, locale='en_US'),
                'last_percentage_change': ''
            }
        }

        # Calculate previous period dates based on range_name
        today = timezone.now().date()
        previous_start_date, previous_end_date = None, None
        if range_name and range_name.lower() in comparables:
            if compare_opposite_title[range_name.lower()] == 'Yesterday':
                previous_start_date = today - timedelta(days=1)
                previous_end_date = today - timedelta(days=1)
            elif compare_opposite_title[range_name.lower()] == 'Last Week':
                previous_start_date = today - timedelta(days=today.weekday() + 7)
                previous_end_date = previous_start_date + timedelta(days=6)
            elif compare_opposite_title[range_name.lower()] == 'Last Month':
                previous_start_date = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
                previous_end_date = today.replace(day=1) - timedelta(days=1)
            elif compare_opposite_title[range_name.lower()] == 'Last Year':
                previous_start_date = today.replace(year=today.year - 1, month=1, day=1)
                previous_end_date = today.replace(year=today.year - 1, month=12, day=31)

        # Get totals for the previous period
        if previous_start_date and previous_end_date:
            previous_orders = Order.objects.filter(created_at__gte=previous_start_date, created_at__lte=previous_end_date)
            previous_delivered = previous_orders.filter(status=OrderStatus.DELIVERED).aggregate(total=Sum(F('total_price_without_tax')))['total'] or 0
            previous_returned = previous_orders.filter(status=OrderStatus.RETURNED).aggregate(total=Sum(F('total_price_without_tax')))['total'] or 0
            previous_cancelled = previous_orders.filter(status=OrderStatus.CANCELLED).aggregate(total=Sum(F('total_price_without_tax')))['total'] or 0

            # Calculate percentage changes
            delivered_percentage_change = round(((order_delivered - previous_delivered) / previous_delivered * 100), 2) if previous_delivered > 0 else 0
            returned_percentage_change = round(((order_returned - previous_returned) / previous_returned * 100), 2) if previous_returned > 0 else 0
            cancelled_percentage_change = round(((order_cancelled - previous_cancelled) / previous_cancelled * 100), 2) if previous_cancelled > 0 else 0

            # Add to response
            data['order_delivered']['last_percentage_change'] = delivered_percentage_change
            data['order_returned']['last_percentage_change'] = returned_percentage_change
            data['order_cancelled']['last_percentage_change'] = cancelled_percentage_change

        # Set percentage change period title
        if range_name and range_name.lower() in comparables:
            data['percetage_change_preiod_title'] = compare_opposite_title_tr[range_name.lower()]

        return Response(data)



class OrderSummaryAPIView(APIView):
    permission_classes = (CommonPermissions, )
    def get(self, request, *args, **kwargs):
        time_period = request.query_params.get('time_period')  # 'year', 'month', 'week', 'day'
        current_date = datetime.now()

        if not time_period:
            raise ValidationError({"error": "time_period query parameter is required."})

        if time_period not in ['year', 'month', 'week', 'day']:
            raise ValidationError({"error": "Invalid time_period. Choose from 'year', 'month', 'week', or 'day'."})

        queryset = Order.objects.all()

        # Default to current year
        year = int(request.query_params.get('year', current_date.year))
        queryset = queryset.filter(created_at__year=year)

        if time_period == 'year':
            # Yearly data by month
            data = queryset.annotate(month=TruncMonth('created_at')) \
                           .values('month') \
                           .annotate(total=Sum('total_price')) \
                           .order_by('month')

            formatted_data = [
                [datetime(year, i, 1).strftime('%B'), 
                 to_currency_unit(next((d['total'] for d in data if d['month'].month == i), 0), settings.BASE_CURRENCY)]
                for i in range(1, 13)
            ]

        elif time_period == 'month':
            # Monthly data by day
            month = int(request.query_params.get('month', current_date.month))
            queryset = queryset.filter(created_at__month=month)
            days_in_month = monthrange(year, month)[1]

            data = queryset.annotate(day=TruncDay('created_at')) \
                           .values('day') \
                           .annotate(total=Sum('total_price')) \
                           .order_by('day')

            formatted_data = [
                [f'{datetime(year, month, day).strftime("%B")} {day}', 
                 to_currency_unit(next((d['total'] for d in data if d['day'].day == day), 0), settings.BASE_CURRENCY)]
                for day in range(1, days_in_month + 1)
            ]

        elif time_period == 'week':
            # Weekly data by day of the week
            week_start = current_date - timedelta(days=current_date.weekday())
            week_end = week_start + timedelta(days=6)

            queryset = queryset.filter(created_at__date__range=[week_start.date(), week_end.date()])

            data = queryset.annotate(day=TruncDay('created_at')) \
                           .values('day') \
                           .annotate(total=Sum('total_price')) \
                           .order_by('day')

            formatted_data = [
                [day_name[(week_start + timedelta(days=i)).weekday()], 
                 to_currency_unit(next((d['total'] for d in data if d['day'].date() == (week_start + timedelta(days=i)).date()), 0), settings.BASE_CURRENCY)]
                for i in range(7)
            ]

        elif time_period == 'day':
            # Daily data by hour
            queryset = queryset.filter(created_at__date=current_date.date())

            data = queryset.annotate(hour=TruncHour('created_at')) \
                           .values('hour') \
                           .annotate(total=Sum('total_price')) \
                           .order_by('hour')

            formatted_data = [
                [datetime(2022, 1, 1, hour).strftime('%I %p'), 
                 to_currency_unit(next((d['total'] for d in data if d['hour'].hour == hour), 0), settings.BASE_CURRENCY)]
                for hour in range(24)
            ]

        return Response(formatted_data)
class OrderEastimateView(OrderProccessorAPIView):
    create_order = False # Eastimate order

    def check_permissions(self, request):
        if not request.user.is_staff:
            self.permission_denied(
                request,
                message=_("You do not have permission to perform this action."),
                code='permission_denied'
            )

class OrderCreateView(OrderProccessorAPIView):
    required_perm = 'add_order'
    create_order = True # Eastimate and create order

    def check_permissions(self, request):        
        if not has_required_perm(request.user, 'add_order', Order):
            self.permission_denied(
                request,
                message=_("You do not have permission to perform this action."),
                code='permission_denied'
            )

class CreateCustomAPIView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = CustomerCreateSerializer

class OrderStatusUpdateAPIView(generics.UpdateAPIView):
    queryset = Order.objects.all()
    serializer_class = OrderStatusUpdateSerializer
    lookup_field = 'alias'

    def check_permissions(self, request):
        status = request.data.get('status')
        user = request.user

        permission_map = {
            OrderStatus.CANCELLED: PermissionsEnum.CAN_CANCEL_ORDER,
            OrderStatus.SHIPPED: PermissionsEnum.CAN_SHIP_ORDER,
            OrderStatus.DELIVERED: PermissionsEnum.CAN_DELIVER_ORDER,
            OrderStatus.APPROVED: PermissionsEnum.CAN_APPROVE_ORDER,
            OrderStatus.PACKED: PermissionsEnum.CAN_PACK_ORDER,
        }

        required_permission = permission_map.get(status)
        if required_permission and not has_required_perm(user, required_permission, Order):
            self.permission_denied(
                request,
                message=_("You do not have permission to perform this action."),
                code='permission_denied'
            )

class OrderMarkAsFullfiledAPIView(generics.GenericAPIView):
    queryset = Order.objects.all()
    serializer_class = OrderStatusUpdateSerializer
    permission_classes = (GranularPermission, )
    required_perm = PermissionsEnum.CAN_FULLFILL_ORDER

    def patch(self, request, *args, **kwargs):
        with transaction.atomic():
            instance = Order.objects.get(alias=kwargs['alias'])

            if instance.status == OrderStatus.DELIVERED:
                raise ValidationError("Order is already marked as fulfilled.")
            
            if instance.status == OrderStatus.CANCELLED:
                raise ValidationError("Cannot mark a cancelled order as fulfilled.")
            
            if instance.status == OrderStatus.RETURNED:
                raise ValidationError("Cannot mark a returned order as fulfilled.")
            
            # Now check stock and reservation
            if instance.reservation_status == OrderStockReservationStatus.DISPATCHED: # do nothing if already dispatched
                pass
            else:
                deduct_reservation_on_packed_for_dispatch(instance)

            instance.status = OrderStatus.DELIVERED
            instance.save()
            return Response({"message": "Order marked as fulfilled."}, status=status.HTTP_200_OK)

class OrderPaymentTermUpdateAPIView(generics.UpdateAPIView):
    model = Order
    permission_classes = (GranularPermission, )
    queryset = Order.objects.all()
    serializer_class = OrderPaymentUpdateSerializer
    lookup_field = 'alias'
    required_perm = PermissionsEnum.CAN_UPDATE_ORDER_PYMENT_TERM

class OrderPaymentMethodUpdateAPIView(generics.UpdateAPIView):
    model = Order
    permission_classes = (GranularPermission, )
    required_perm = PermissionsEnum.CAN_UPDATE_ORDER_PAYMENT_METHOD
    queryset = Order.objects.all()
    serializer_class = OrderPaymentMethodSerializer
    lookup_field = 'alias'


class ReturnRequestFilter(filters.FilterSet):
    order_alias = filters.CharFilter(field_name='order__alias', lookup_expr='iexact')
    class Meta:
        model = ReturnRequest
        fields = [
            'id',
            'status',
            'reason',
            'order_alias',
        ]


class ReturnRequestFilterMixing:
    filter_backends = [
        filters.DjangoFilterBackend,
        drf_filters.SearchFilter,
        drf_filters.OrderingFilter,
    ]
    search_fields = [
        'id',
        'status',
        'reason',
        'reason_details',
        'order__alias',
    ]
    ordering_fields = [
        'order',
    ]
    filterset_class = ReturnRequestFilter  # Use the filter class here


class ReturnRequestAPIView(ReturnRequestFilterMixing, generics.ListCreateAPIView):
    permission_classes = (CommonPermissions, )
    model = ReturnRequest
    queryset = ReturnRequest.objects.all()
    serializer_class = ReturnRequestSerializer
    
class ReturnRequestDetailAPIView(generics.RetrieveUpdateAPIView):
    permission_classes = (CommonPermissions, )
    model = ReturnRequest
    queryset = ReturnRequest.objects.all()
    serializer_class = ReturnRequestDetailsSerializer
    lookup_field = 'id'

    def get_serializer_class(self):
        if self.request.method in ['PATCH', 'PUT']:
            return ReturnRequestStatusUpdateSerializer
        return self.serializer_class

class ReturnLineItemStatusUpdateAPIView(generics.UpdateAPIView):
    permission_classes = (CommonPermissions, )
    model = ReturnRequest

    serializer_class = ReturnLineItemStatusUpdateSerializer


    def update(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        receiving_status = serializer.validated_data['receiving_status']
        line_item_ids = serializer.validated_data['line_item_ids']

        # Update the receiving status for the specified line items
        line_items = ReturnLineItem.objects.filter(id__in=line_item_ids)

        if line_items.count() != len(line_item_ids):
            return Response(
                {"error": "Some line items were not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        line_items.update(receiving_status=receiving_status)

        adjust_stocks_returned_items(line_items)

        return Response(
            {"message": "Receiving status updated successfully."},
            status=status.HTTP_200_OK
        )
    

class ReturnRequestBulkUpdateAPIView(generics.UpdateAPIView):
    permission_classes = (CommonPermissions, )
    model = ReturnRequest

    serializer_class = ReturnRequestBulkUpdateSerializer

    def update(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        request_ids = serializer.validated_data['request_ids']
        request_status = serializer.validated_data['status']

        # Update the status for the specified return requests
        return_requests = ReturnRequest.objects.filter(id__in=request_ids)

        to_update = {
            'status': request_status
        }

        if request_status == ReturnStatus.APPROVED:
            to_update['approved_at'] = timezone.now()
            to_update['approved_by'] = request.user

        if request_status == ReturnStatus.REVIEWED:
            to_update['reviewed_by'] = request.user

        if request_status == ReturnStatus.COMPLETED:
            to_update['completed_at'] = timezone.now()
            to_update['completed_by'] = request.user

        if request_status == ReturnStatus.CANCELLED:
            to_update['cancelled_at'] = timezone.now()

        return_requests.update(**to_update)

        return Response(
            {"message": "Return requests updated successfully."},
            status=status.HTTP_200_OK
        )
    