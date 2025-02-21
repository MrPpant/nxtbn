from nxtbn.order import OrderStockReservationStatus, ReturnReceiveStatus
from nxtbn.order.models import ReturnLineItem
from nxtbn.warehouse.models import Warehouse, Stock, StockReservation

from django.db import transaction
from rest_framework.exceptions import ValidationError

def adjust_stock(stock, reserved_delta, quantity_delta):
    """
    Adjust stock's reserved and quantity fields atomically.

    Args:
        stock: The stock instance to adjust.
        reserved_delta: Change in reserved quantity (+/-).
        quantity_delta: Change in available quantity (+/-).

    Raises:
        ValidationError: If adjustments would result in negative values for reserved or quantity.
    """
    if stock.quantity + quantity_delta < 0:
        raise ValidationError("Insufficient stock to adjust quantity.")
    if stock.reserved + reserved_delta < 0:
        raise ValidationError("Reserved stock cannot be negative.")

    stock.reserved += reserved_delta
    stock.quantity += quantity_delta
    stock.save()


def reserve_stock(order):
    """
    Reserve stock for the given order by deducting available stock from warehouses.
    If stock is insufficient for any item, the operation will rollback and raise a ValidationError.
    """
    try:
        with transaction.atomic():
            for item in order.line_items.all():
                required_quantity = item.quantity

                if item.variant.track_inventory:
                    # Fetch stocks for the product variant ordered by available quantity
                    stocks = Stock.objects.filter(
                        product_variant=item.variant
                    ).order_by('quantity')

                    for stock in stocks:
                        if required_quantity <= 0:
                            break

                        available_quantity = stock.quantity - stock.reserved
                        if available_quantity <= 0:
                            continue

                        if available_quantity >= required_quantity:
                            # Deduct the required quantity and reserve it
                            adjust_stock(stock, reserved_delta=required_quantity, quantity_delta=0)

                            StockReservation.objects.create(
                                stock=stock,
                                quantity=required_quantity,
                                purpose="Pending Order",
                                order_line=item
                            )

                            required_quantity = 0
                        else:
                            # Partially reserve stock and continue with the remaining quantity
                            adjust_stock(stock, reserved_delta=available_quantity, quantity_delta=0)

                            StockReservation.objects.create(
                                stock=stock,
                                quantity=available_quantity,
                                purpose="Pending Order",
                                order_line=item
                            )

                            required_quantity -= available_quantity

                    if required_quantity > 0:
                        # If we couldn't reserve the full quantity, rollback and raise an error
                        raise ValidationError(f"Insufficient stock for {item.variant.name}")

            # Save the order's reservation status after successful reservation
            order.reservation_status = OrderStockReservationStatus.RESERVED
            order.save()
    except ValidationError:
        # Update the order's reservation status to FAILED outside the transaction
        order.reservation_status = OrderStockReservationStatus.FAILED
        order.save()
        raise

def release_stock(order):
    if order.reservation_status != OrderStockReservationStatus.RESERVED:
        raise ValidationError("Order stock is not reserved; nothing to release.")
    
    with transaction.atomic():
        for item in order.line_items.all():
            if item.variant.track_inventory:
                for reservation in item.stock_reservations.all():
                    stock = reservation.stock
                    adjust_stock(stock, reserved_delta=-reservation.quantity, quantity_delta=0)
                    reservation.delete()

        order.reservation_status = OrderStockReservationStatus.RELEASED
        order.save()
        return order

def deduct_reservation_on_packed_for_dispatch(order):
    if order.reservation_status == OrderStockReservationStatus.NOT_REQUIRED: # As not reservable, nothing to do
        return None
    
    if order.reservation_status == OrderStockReservationStatus.FAILED:
        raise ValidationError("One or more items are not reserved. Please ensure all items are available in stock and reserved before preparing for shipment.")
    
    if order.reservation_status == OrderStockReservationStatus.DISPATCHED:
        raise ValidationError("Order has already been dispatched.")
    
    if order.reservation_status == OrderStockReservationStatus.RELEASED:
        raise ValidationError("Cannot dispatch an order with released stock reservations.")
    
    

    with transaction.atomic():
        for item in order.line_items.all():
            if item.variant.track_inventory:
                # Use the correct related name for accessing reservations
                for reservation in item.stock_reservations.all():
                    stock = reservation.stock

                    if stock.reserved < reservation.quantity:
                        raise ValidationError(
                            f"Reservation quantity for {item.variant.name} exceeds available reserved stock."
                        )

                    # Deduct reserved quantity permanently
                    adjust_stock(stock, reserved_delta=-reservation.quantity, quantity_delta=-reservation.quantity)

                    # Remove the reservation
                    reservation.delete()

        order.reservation_status = OrderStockReservationStatus.DISPATCHED
        order.save()
        return order
    


def adjust_stocks_returned_items(line_items_instances):
    with transaction.atomic():
        for return_line_item in line_items_instances:
            order_line_item = return_line_item.order_line_item
            variant = order_line_item.variant
            quantity_to_return = return_line_item.quantity

            if not variant.track_inventory:
                continue

            stock, created = Stock.objects.get_or_create(
                product_variant=variant,
                warehouse=return_line_item.destination,
                defaults={"quantity": 0, "reserved": 0}
            )
            
            # Adjust the stock quantity
            adjust_stock(stock, reserved_delta=0, quantity_delta=quantity_to_return)

            # Mark the receiving status as received for the return line item
            return_line_item.receiving_status = ReturnReceiveStatus.RECEIVED
            return_line_item.save()
