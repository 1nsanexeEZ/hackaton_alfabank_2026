"""Shared field types for Pydantic schemas."""

from typing import Annotated

import nh3
from pydantic import AfterValidator


def _strip_html(value: str) -> str:
    return nh3.clean(value, tags=set()).strip()


# Free text from a user (comments, purposes, names): HTML is stripped before it
# reaches the domain, so it can be safely rendered on the frontend and in the feed.
SafeString = Annotated[str, AfterValidator(_strip_html)]
