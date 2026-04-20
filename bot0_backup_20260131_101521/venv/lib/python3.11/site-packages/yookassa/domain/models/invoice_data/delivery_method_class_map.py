# -*- coding: utf-8 -*-
from yookassa.domain.common.data_context import DataContext
from yookassa.domain.models.invoice import DeliveryMethodType
# requests
from yookassa.domain.models.invoice_data.request.delivery_method_self import \
    DeliveryMethodSelf as RequestDeliveryMethodSelf
# responses
from yookassa.domain.models.invoice_data.response.delivery_method_self import \
    DeliveryMethodSelf as ResponseDeliveryMethodSelf
from yookassa.domain.models.invoice_data.response.delivery_method_unknown import \
    DeliveryMethodUnknown as ResponseDeliveryMethodUnknown


class DeliveryMethodClassMap(DataContext):
    """
    Сопоставление классов DeliveryMethod по типу.
    """  # noqa: E501

    def __init__(self):
        super(DeliveryMethodClassMap, self).__init__(('request', 'response'))

    @property
    def request(self):
        return {
            DeliveryMethodType.SELF: RequestDeliveryMethodSelf,
        }

    @property
    def response(self):
        return {
            DeliveryMethodType.SELF: ResponseDeliveryMethodSelf,
            DeliveryMethodType.UNKNOWN: ResponseDeliveryMethodUnknown,
        }
