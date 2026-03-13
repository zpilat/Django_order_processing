class ServiceError(Exception):
    """Základní výjimka service vrstvy."""


class ServiceValidationError(ServiceError):
    """Vyhozeno při nevalidním vstupu pro service operaci."""


class ServiceOperationError(ServiceError):
    """Vyhozeno při chybě provedení service operace."""
