from django.urls import path

from nxtbn.order.api.dashboard import views as order_views


urlpatterns = [
    path('orders/', order_views.OrderListView.as_view(), name='order-list'),
    path('orders/create/', order_views.OrderCreateView.as_view(), name='admin_order_create'),
    path('orders/eastimate/', order_views.OrderEastimateView.as_view(), name='admin_order_estimate'),
    path('create-customer/', order_views.CreateCustomAPIView.as_view(), name='create-customer'),
    path('orders/<uuid:alias>/', order_views.OrderDetailView.as_view(), name='order-detail'),
    path('orders/status/update/<uuid:alias>/', order_views.OrderStatusUpdateAPIView.as_view(), name='order-status-update'),
    path('orders/fulfill/<uuid:alias>/', order_views.OrderMarkAsFullfiledAPIView.as_view(), name='order-fulfillment-status-update'),
    path('orders/payment-term/update/<uuid:alias>/', order_views.OrderPaymentTermUpdateAPIView.as_view(), name='order-payment-term-update'),
    path('orders/payment-method/update/<uuid:alias>/', order_views.OrderPaymentMethodUpdateAPIView.as_view(), name='order-payment-method-update'),
    path('orders/return-request/', order_views.ReturnRequestAPIView.as_view(), name='return-request'),
    path('orders/return-request/<int:id>/', order_views.ReturnRequestDetailAPIView.as_view(), name='return-request-detail'),
    path('orders/return-line-item/receiving-status/update/', order_views.ReturnLineItemStatusUpdateAPIView.as_view(), name='return-line-item-status-update'),
    path('orders/return-request/status/bulk-update/', order_views.ReturnRequestBulkUpdateAPIView.as_view(), name='return-request-status-update'),
    path('stats/', order_views.BasicStatsView.as_view(), name='basic-stats'),
    path('stats/overview/', order_views.OrderOverviewStatsView.as_view(), name='order_overview_stats'),
    path('order-summary/', order_views.OrderSummaryAPIView.as_view(), name='order-summary'), # statistics/trending
]
