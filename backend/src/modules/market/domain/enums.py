from enum import StrEnum


class RateSource(StrEnum):
    """Who entered a stored rate: the admin by hand or a sync with cbr.ru."""

    ADMIN = "admin"
    CBR = "cbr"
