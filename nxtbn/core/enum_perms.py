
from django.db import models

class PermissionsEnum(models.TextChoices):
    CAN_APPROVE_ORDER = "can_approve_order"
    CAN_CANCEL_ORDER = "can_cancel_order"
    CAN_SHIP_ORDER = "can_ship_order"
    CAN_PACK_ORDER = "can_pack_order"
    CAN_DELIVER_ORDER = "can_deliver_order"
    CAN_UPDATE_ORDER_PYMENT_TERM = "can_update_order_payment_term"
    CAN_UPDATE_ORDER_PAYMENT_METHOD = "can_update_order_payment_method"
    CAN_FULLFILL_ORDER = "can_fullfill_order" #  Directly fullfill order, will not check lifecycle
    

    CAN_INITIATE_PAYMENT_REFUND = "CAN_INITIATE_PAYMENT_REFUND"

    CAN_BULK_PRODUCT_STATUS_UPDATE = "can_bulk_product_status_update"
    CAN_BULK_PRODUCT_DELETE = "can_bulk_product_delete"

    CAN_RECEIVE_TRANSFERRED_STOCK = "can_receive_transferred_stock" 
    CAN_MARK_STOCK_TRANSFER_AS_COMPLETED = "can_mark_stock_transfer_as_completed"

    CAN_READ_CUSTOMER = "can_read_customer"
    CAN_UPDATE_CUSTOMER = "can_create_customer"