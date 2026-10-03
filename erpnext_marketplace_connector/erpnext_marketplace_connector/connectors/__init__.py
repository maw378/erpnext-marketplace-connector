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


def get_connector(store: Document) -> BaseConnector:
	platform = frappe.db.get_value("Marketplace Channel", store.marketplace_channel, "platform")
	connector_class = CONNECTORS.get(platform)
	if not connector_class:
		frappe.throw(f"No connector implemented for platform {platform}")
	return connector_class(store)
