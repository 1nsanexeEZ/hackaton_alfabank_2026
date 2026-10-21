from src.core.exceptions.exceptions import ConflictError


class ProductNotAvailableError(ConflictError):
    """The product exists but can't be chosen for a new application (archived)."""

    code = "product_not_available"
    default_message = "Product is not available for new applications"
