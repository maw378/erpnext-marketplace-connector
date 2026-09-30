import frappe
from frappe.model.document import Document

from .base import BaseConnector
from .salla import SallaConnector
from .shopify import ShopifyConnector
from .woocommerce import WooCommerceConnector
from .zid import ZidConnector

CONNECTORS = {
	"Shopify": ShopifyConnector,
	"WooCommerce": WooCommerceConnector,
	"Salla": SallaConnector,
	"Zid": ZidConnector,
}


def get_connector(channel: Document) -> BaseConnector:
	connector_class = CONNECTORS.get(channel.platform)
	if not connector_class:
		frappe.throw(f"No connector implemented for platform {channel.platform}")
	return connector_class(channel)
