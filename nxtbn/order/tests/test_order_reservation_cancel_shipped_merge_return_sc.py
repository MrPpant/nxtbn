import random
from decimal import Decimal
from django.conf import settings
from rest_framework import status
from rest_framework.reverse import reverse
from nxtbn.core import PublishableStatus
from nxtbn.core.utils import normalize_amount_currencywise
from nxtbn.home.base_tests import BaseTestCase
from nxtbn.order import OrderStatus, OrderStockReservationStatus, ReturnReason, ReturnReceiveStatus
from nxtbn.order.models import Order, OrderLineItem, ReturnLineItem
from nxtbn.product.models import Product, ProductVariant
from rest_framework.test import APIClient
from nxtbn.product.tests import ProductFactory, ProductTypeFactory, ProductVariantFactory
from nxtbn.shipping.tests import ShippingMethodFactory
from nxtbn.tax.tests import TaxClassFactory, TaxRateFactory
from nxtbn.warehouse.tests import StockFactory, WarehouseFactory

from django.test.utils import override_settings
from django.db.models import Sum


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class OrderStockReservationTest(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.adminLogin()

        self.product_type = ProductTypeFactory(
            name="Physical Product Type",
        )


        self.variant = ProductVariantFactory(
            product=ProductFactory(
                product_type=self.product_type,
                status=PublishableStatus.PUBLISHED,
            ),
            track_inventory=True,
            allow_backorder=False   ,
            currency=settings.BASE_CURRENCY,
            price=normalize_amount_currencywise(100.00, settings.BASE_CURRENCY),
            cost_per_unit=50.00,
        )   
        

        self.warehosue_us_central= WarehouseFactory()
        self.warehosue_us_east= WarehouseFactory()
        self.warehosue_us_west= WarehouseFactory()
        

        StockFactory(
            warehouse=self.warehosue_us_central,
            product_variant=self.variant,
            quantity=5,
            reserved=0,
        )

        StockFactory(
            warehouse=self.warehosue_us_east,
            product_variant=self.variant,
            quantity=6,
            reserved=0,
        )
       



        self.order_api_url = reverse('admin_order_create')
        self.order_estimate_api_url = reverse('admin_order_estimate')

    def test_order_stock_tracking_with_disallowed_backorder_return(self):
        
        payload_more_than_stock = {
            "variants": [
                {
                    "alias": self.variant.alias,
                    "quantity": 15, # Expect bad request as we have only 11 quantity in stock
                },
            ]
        }

        order_out_of_stock_response_with_stock_tracking = self.auth_client.post(self.order_api_url, payload_more_than_stock, format='json')
        self.assertEqual(order_out_of_stock_response_with_stock_tracking.status_code, status.HTTP_400_BAD_REQUEST)


        order_payload_less_than_stock = {
                "variants": [
                    {
                        "alias": self.variant.alias,
                        "quantity": 7, # Expect success as we have 11 quantity in stock
                    },
                ]
            }

        order_less_than_stock_response_with_stock_tracking = self.auth_client.post(self.order_api_url, order_payload_less_than_stock, format='json')
        self.assertEqual(order_less_than_stock_response_with_stock_tracking.status_code, status.HTTP_200_OK)

        # as order is successfully created, we should have 7 reserved quantity of 11 quantity in stock
        remained_stock = ProductVariant.objects.get(alias=self.variant.alias).warehouse_stocks.aggregate(total=Sum('quantity'))['total']
        reserved_stock = ProductVariant.objects.get(alias=self.variant.alias).warehouse_stocks.aggregate(total=Sum('reserved'))['total']

        self.assertEqual(remained_stock, 11)
        self.assertEqual(reserved_stock, 7)

        order = Order.objects.get(alias=order_less_than_stock_response_with_stock_tracking.data['order_alias'])
        self.assertEqual(order.reservation_status, OrderStockReservationStatus.RESERVED)


        # Now Ship the successfull order
        order_status_update_url = reverse('order-status-update', args=[order_less_than_stock_response_with_stock_tracking.data['order_alias']])
        approve = self.auth_client.patch(order_status_update_url, {"status": OrderStatus.APPROVED}, format='json')
        processing = self.auth_client.patch(order_status_update_url, {"status": OrderStatus.PACKED}, format='json')
        approved = self.auth_client.patch(order_status_update_url, {"status": OrderStatus.SHIPPED}, format='json')

        self.assertEqual(approve.status_code, status.HTTP_200_OK)
        self.assertEqual(processing.status_code, status.HTTP_200_OK)
        self.assertEqual(approved.status_code, status.HTTP_200_OK)

        # as it is shipped, reserved quantity should be 0 and stock should be 4
        remained_stock_after_shipping = ProductVariant.objects.get(alias=self.variant.alias).warehouse_stocks.aggregate(total=Sum('quantity'))['total']
        reserved_stock_after_shipping = ProductVariant.objects.get(alias=self.variant.alias).warehouse_stocks.aggregate(total=Sum('reserved'))['total']

        self.assertEqual(remained_stock_after_shipping, 4)
        self.assertEqual(reserved_stock_after_shipping, 0)

        # Now try to return

        # Before return, we need to make sure item is delivered
        delivered = self.auth_client.patch(order_status_update_url, {"status": OrderStatus.DELIVERED}, format='json')
        self.assertEqual(delivered.status_code, status.HTTP_200_OK)


        return_request_url = reverse('return-request')
        line_items = OrderLineItem.objects.filter(order__alias=order_less_than_stock_response_with_stock_tracking.data['order_alias'])

      
        return_request_payload = {
            "reason": ReturnReason.DAMAGED,
            "order": order_less_than_stock_response_with_stock_tracking.data['order_id'],
            "line_items": [
            {
                "order_line_item": line_items[0].id,
                "quantity": 3,
                "max_quantity": 3,
                "destination": self.warehosue_us_central.id,
            }
            ]
        }


        return_request_response = self.auth_client.post(return_request_url, return_request_payload, format='json')
        self.assertEqual(return_request_response.status_code, status.HTTP_201_CREATED) # Return request is created
        
        
        # Now receive the return
        return_line_items_status_update_url = reverse('return-line-item-status-update')

        line_items_ids = list(ReturnLineItem.objects.filter(order_line_item__in=line_items).values_list('id', flat=True))
        return_line_item_payload = {
            "receiving_status": ReturnReceiveStatus.RECEIVED,
            "line_item_ids": line_items_ids,
        }

        return_line_item_response = self.auth_client.put(return_line_items_status_update_url, return_line_item_payload, format='json')
        self.assertEqual(return_line_item_response.status_code, status.HTTP_200_OK)

        # Now stock should be 7 and reserved should be 0
        remained_stock_after_return = ProductVariant.objects.get(alias=self.variant.alias).warehouse_stocks.aggregate(total=Sum('quantity'))['total']
        reserved_stock_after_return = ProductVariant.objects.get(alias=self.variant.alias).warehouse_stocks.aggregate(total=Sum('reserved'))['total']

        self.assertEqual(remained_stock_after_return, 7)
        self.assertEqual(reserved_stock_after_return, 0)



    def test_order_back_order_allowed(self):
        # test backorder. in stock 5 but ordered 7. 2 should be backordered. Allowing order even if stock is less than ordered quantity
        self.variant_track_order_backorder = ProductVariantFactory(
            product=ProductFactory(
                product_type=self.product_type,
                status=PublishableStatus.PUBLISHED,
            ),
            track_inventory=True,
            allow_backorder=True,
            currency=settings.BASE_CURRENCY,
            price=normalize_amount_currencywise(100.00, settings.BASE_CURRENCY),
            cost_per_unit=50.00,
        )
        self.variant_track_order_without_backorder = ProductVariantFactory(
            product=ProductFactory(
                product_type=self.product_type,
                status=PublishableStatus.PUBLISHED,
            ),
            track_inventory=True,
            allow_backorder=False,
            currency=settings.BASE_CURRENCY,
            price=normalize_amount_currencywise(100.00, settings.BASE_CURRENCY),
            cost_per_unit=50.00,
        )   
        

        self.warehosue_us_east_ohio= WarehouseFactory()
        

        stock_with_bo = StockFactory(
            warehouse=self.warehosue_us_east_ohio,
            product_variant=self.variant_track_order_backorder,
            quantity=5,
            reserved=0,
        )
        stock_without_bo = StockFactory(
            warehouse=self.warehosue_us_east_ohio,
            product_variant=self.variant_track_order_without_backorder,
            quantity=10,
            reserved=0,
        )

        order_payload_more_than_stock = {
            "variants": [
                {
                    "alias": self.variant_track_order_backorder.alias,
                    "quantity": 7, # more than stock
                },
                {
                    "alias": self.variant_track_order_without_backorder.alias,
                    "quantity": 8, # less than stock
                },
            ]
        }

        order_out_of_stock_response_with_stock_tracking_bo = self.auth_client.post(self.order_api_url, order_payload_more_than_stock, format='json')
        self.assertEqual(order_out_of_stock_response_with_stock_tracking_bo.status_code, status.HTTP_200_OK) # success as backorder is allowed

        # as order is successfully created, we should have 5 reserved quantity of 5 quantity in stock
        remained_stock_with_bo = ProductVariant.objects.get(alias=self.variant_track_order_backorder.alias).warehouse_stocks.aggregate(total=Sum('quantity'))['total']
        reserved_stock_with_bo = ProductVariant.objects.get(alias=self.variant_track_order_backorder.alias).warehouse_stocks.aggregate(total=Sum('reserved'))['total']

        self.assertEqual(remained_stock_with_bo, 5)
        self.assertEqual(reserved_stock_with_bo, 0)

        remained_stock_without_bo = ProductVariant.objects.get(alias=self.variant_track_order_without_backorder.alias).warehouse_stocks.aggregate(total=Sum('quantity'))['total']
        reserved_stock_without_bo = ProductVariant.objects.get(alias=self.variant_track_order_without_backorder.alias).warehouse_stocks.aggregate(total=Sum('reserved'))['total']

        self.assertEqual(remained_stock_without_bo, 10)
        self.assertEqual(reserved_stock_without_bo, 0)

        # make sure reservation is failed
        order = Order.objects.get(alias=order_out_of_stock_response_with_stock_tracking_bo.data['order_alias'])
        self.assertEqual(order.reservation_status, OrderStockReservationStatus.FAILED)

        # Now Ship the successfull order
        order_status_update_url = reverse('order-status-update', args=[order_out_of_stock_response_with_stock_tracking_bo.data['order_alias']])
        approve = self.auth_client.patch(order_status_update_url, {"status": OrderStatus.APPROVED}, format='json')
        packed = self.auth_client.patch(order_status_update_url, {"status": OrderStatus.PACKED}, format='json')
        shipped = self.auth_client.patch(order_status_update_url, {"status": OrderStatus.SHIPPED}, format='json')
        
        self.assertEqual(approve.status_code, status.HTTP_200_OK)
        self.assertEqual(packed.status_code, status.HTTP_400_BAD_REQUEST) # as order is not reserved, mean is not in stock, so packing should not be allowed

        self.assertEqual(shipped.status_code, status.HTTP_400_BAD_REQUEST) # as order is not reserved, it should not be shipped

        # Now increase stock 5 item in both and re-try reserve stock for order
        stock_with_bo.quantity += 5
        stock_with_bo.save()

        stock_without_bo.quantity += 5
        stock_without_bo.save()

        # retry reserve stock
        retry_reservation_url = reverse('retry-stock-reservation', args=[order_out_of_stock_response_with_stock_tracking_bo.data['order_alias']])
        retry_reservation_response = self.auth_client.post(retry_reservation_url, format='json')
        self.assertEqual(retry_reservation_response.status_code, status.HTTP_200_OK)

        # now check if it is reserved as expected
        order = Order.objects.get(alias=order_out_of_stock_response_with_stock_tracking_bo.data['order_alias'])
        self.assertEqual(order.reservation_status, OrderStockReservationStatus.RESERVED)

        # check stock and reserved quantity
        remained_stock_with_bo = ProductVariant.objects.get(alias=self.variant_track_order_backorder.alias).warehouse_stocks.aggregate(total=Sum('quantity'))['total']
        reserved_stock_with_bo = ProductVariant.objects.get(alias=self.variant_track_order_backorder.alias).warehouse_stocks.aggregate(total=Sum('reserved'))['total']

        self.assertEqual(remained_stock_with_bo, 10)
        self.assertEqual(reserved_stock_with_bo, 7)

        remained_stock_without_bo = ProductVariant.objects.get(alias=self.variant_track_order_without_backorder.alias).warehouse_stocks.aggregate(total=Sum('quantity'))['total']
        reserved_stock_without_bo = ProductVariant.objects.get(alias=self.variant_track_order_without_backorder.alias).warehouse_stocks.aggregate(total=Sum('reserved'))['total']

        self.assertEqual(remained_stock_without_bo, 15)
        self.assertEqual(reserved_stock_without_bo, 8)

        # now pack
        packed = self.auth_client.patch(order_status_update_url, {"status": OrderStatus.PACKED}, format='json')
        self.assertEqual(packed.status_code, status.HTTP_200_OK) # as order is reserved, it should be packed

        # as enough stock is available and order is reserved, now ship the order
        shipped = self.auth_client.put(order_status_update_url, {"status": OrderStatus.SHIPPED}, format='json')
        self.assertEqual(shipped.status_code, status.HTTP_200_OK)

        # as it is shipped, reserved quantity should be 0 and stock should be 3 and 7
        remained_stock_after_shipping_with_bo = ProductVariant.objects.get(alias=self.variant_track_order_backorder.alias).warehouse_stocks.aggregate(total=Sum('quantity'))['total']
        reserved_stock_after_shipping_with_bo = ProductVariant.objects.get(alias=self.variant_track_order_backorder.alias).warehouse_stocks.aggregate(total=Sum('reserved'))['total']

        self.assertEqual(remained_stock_after_shipping_with_bo, 3)
        self.assertEqual(reserved_stock_after_shipping_with_bo, 0)

        remained_stock_after_shipping_without_bo = ProductVariant.objects.get(alias=self.variant_track_order_without_backorder.alias).warehouse_stocks.aggregate(total=Sum('quantity'))['total']
        reserved_stock_after_shipping_without_bo = ProductVariant.objects.get(alias=self.variant_track_order_without_backorder.alias).warehouse_stocks.aggregate(total=Sum('reserved'))['total']

        self.assertEqual(remained_stock_after_shipping_without_bo, 7)
        self.assertEqual(reserved_stock_after_shipping_without_bo, 0)


    def test_order_stock_tracking_with_cancelled_order(self):
        self.variant_temp = ProductVariantFactory(
            product=ProductFactory(
                product_type=self.product_type,
                status=PublishableStatus.PUBLISHED,
            ),
            track_inventory=True,
            allow_backorder=False,
            currency=settings.BASE_CURRENCY,
            price=normalize_amount_currencywise(100.00, settings.BASE_CURRENCY),
            cost_per_unit=50.00,
        )

        StockFactory(
            warehouse=self.warehosue_us_east,
            product_variant=self.variant_temp,
            quantity=5,
            reserved=0,
        )

        order_payload = {
            "variants": [
                {
                    "alias": self.variant_temp.alias,
                    "quantity": 5, # exactly in stock
                },
            ]
        }

        order_response = self.auth_client.post(self.order_api_url, order_payload, format='json')
        self.assertEqual(order_response.status_code, status.HTTP_200_OK)

        # cancel the order
        order_status_update_url = reverse('order-status-update', args=[order_response.data['order_alias']])
        cancel = self.auth_client.put(order_status_update_url, {"status": OrderStatus.CANCELLED}, format='json')
        self.assertEqual(cancel.status_code, status.HTTP_200_OK)

        # as order is cancelled, reserved quantity should be 0 and stock should be 5
        remained_stock_after_cancel = ProductVariant.objects.get(alias=self.variant_temp.alias).warehouse_stocks.aggregate(total=Sum('quantity'))['total']
        reserved_stock_after_cancel = ProductVariant.objects.get(alias=self.variant_temp.alias).warehouse_stocks.aggregate(total=Sum('reserved'))['total']

        self.assertEqual(remained_stock_after_cancel, 5)
        self.assertEqual(reserved_stock_after_cancel, 0)

    def test_order_without_tracking_stock(self):
        self.variant_not_track_inventory = ProductVariantFactory(
            product=ProductFactory(
                product_type=self.product_type,
                status=PublishableStatus.PUBLISHED,
            ),
            track_inventory=False,
            allow_backorder=False,
            currency=settings.BASE_CURRENCY,
            price=normalize_amount_currencywise(100.00, settings.BASE_CURRENCY),
            cost_per_unit=50.00,
        )

        order_payload = {
            "variants": [
                {
                    "alias": self.variant_not_track_inventory.alias,
                    "quantity": 5,
                },
            ]
        }

        order_response = self.auth_client.post(self.order_api_url, order_payload, format='json')
        self.assertEqual(order_response.status_code, status.HTTP_200_OK)

        # as order is created, reserved quantity should be 0 and stock should be 0
        remained_stock = ProductVariant.objects.get(alias=self.variant_not_track_inventory.alias).warehouse_stocks.aggregate(total=Sum('quantity'))['total'] or 0
        reserved_stock = ProductVariant.objects.get(alias=self.variant_not_track_inventory.alias).warehouse_stocks.aggregate(total=Sum('reserved'))['total'] or 0

        self.assertEqual(remained_stock, 0)
        self.assertEqual(reserved_stock, 0)

        # Now Ship the successfull order
        order_status_update_url = reverse('order-status-update', args=[order_response.data['order_alias']])
        approve = self.auth_client.patch(order_status_update_url, {"status": OrderStatus.APPROVED}, format='json')
        processing = self.auth_client.patch(order_status_update_url, {"status": OrderStatus.PACKED}, format='json')
        shipped = self.auth_client.patch(order_status_update_url, {"status": OrderStatus.SHIPPED}, format='json')

        self.assertEqual(approve.status_code, status.HTTP_200_OK)
        self.assertEqual(processing.status_code, status.HTTP_200_OK)
        self.assertEqual(shipped.status_code, status.HTTP_200_OK)


        # as it is shipped, reserved quantity should be 0 and stock should be 0
        remained_stock_after_shipping = ProductVariant.objects.get(alias=self.variant_not_track_inventory.alias).warehouse_stocks.aggregate(total=Sum('quantity'))['total'] or 0
        reserved_stock_after_shipping = ProductVariant.objects.get(alias=self.variant_not_track_inventory.alias).warehouse_stocks.aggregate(total=Sum('reserved'))['total'] or 0

        self.assertEqual(remained_stock_after_shipping, 0)
        self.assertEqual(reserved_stock_after_shipping, 0)

        # mark it as delivered
        delivered = self.auth_client.patch(order_status_update_url, {"status": OrderStatus.DELIVERED}, format='json')

        # now try to return
        return_request_url = reverse('return-request')
        line_items = OrderLineItem.objects.filter(order__alias=order_response.data['order_alias'])

        return_request_payload = {
            "reason": ReturnReason.DAMAGED,
            "order": order_response.data['order_id'],
            "line_items": [
            {
                "order_line_item": line_items[0].id,
                "quantity": 3,
                "max_quantity": 3,
                "destination": self.warehosue_us_east.id,
            }
            ]
        }

        return_request_response = self.auth_client.post(return_request_url, return_request_payload, format='json')
        self.assertEqual(return_request_response.status_code, status.HTTP_201_CREATED)
        
        # Now receive the return
        return_line_items_status_update_url = reverse('return-line-item-status-update')

        line_items_ids = list(ReturnLineItem.objects.filter(order_line_item__in=line_items).values_list('id', flat=True))
        return_line_item_payload = {
            "receiving_status": ReturnReceiveStatus.RECEIVED,
            "line_item_ids": line_items_ids,
        }

        return_line_item_response = self.auth_client.put(return_line_items_status_update_url, return_line_item_payload, format='json')
        self.assertEqual(return_line_item_response.status_code, status.HTTP_200_OK)

        # as it is received, stock should be 0
        remained_stock_after_return = ProductVariant.objects.get(alias=self.variant_not_track_inventory.alias).warehouse_stocks.aggregate(total=Sum('quantity'))['total'] or 0
        reserved_stock_after_return = ProductVariant.objects.get(alias=self.variant_not_track_inventory.alias).warehouse_stocks.aggregate(total=Sum('reserved'))['total'] or 0

        self.assertEqual(remained_stock_after_return, 0)
        self.assertEqual(reserved_stock_after_return, 0)
        