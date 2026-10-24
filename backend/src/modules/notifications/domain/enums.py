"""Value sets of the feed, shared by the contract, the records and the texts."""

from typing import Literal

FeedItemType = Literal[
    "status_changed",
    "stage_changed",
    "info_requested",
    "offer_ready",
    "task_assigned",
    "advice",
    "news",
    "support",
]
RecipientType = Literal["account", "role"]
Audience = Literal["client", "bank"]
Priority = Literal["low", "normal", "high"]
StreamEventName = Literal["feed_item", "application_updated", "heartbeat"]
