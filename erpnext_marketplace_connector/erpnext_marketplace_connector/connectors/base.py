from frappe.model.document import Document


class BaseConnector:
	"""Interface every platform connector (Shopify, WooCommerce, Salla, Zid, ...) implements.

	A connector is constructed from a Marketplace Channel document and talks to that
	one platform's API using the credentials stored on it.
	"""

	def __init__(self, channel: Document):
		self.channel = channel

	def fetch_new_orders(self) -> list[dict]:
		"""Return orders created/updated on the channel since the last sync."""
		raise NotImplementedError

	def push_stock_levels(self, item_code_to_qty: dict[str, float]) -> None:
		"""Push available quantities (keyed by Item Code) to the channel."""
		raise NotImplementedError

	def push_prices(self, item_code_to_rate: dict[str, float]) -> None:
		"""Push prices (keyed by Item Code) to the channel."""
		raise NotImplementedError

	def verify_webhook_signature(self, request_body: bytes, signature_header: str) -> bool:
		"""Validate an inbound webhook against this channel's webhook secret."""
		raise NotImplementedError
