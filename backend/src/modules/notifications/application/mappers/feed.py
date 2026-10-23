"""Stored feed records -> DTO of the use cases."""

from src.modules.notifications.application.dto.feed import FeedItemDTO, FeedRecordDTO
from src.modules.notifications.domain.feed import FeedRecord


def feed_item_dto(record: FeedRecord) -> FeedItemDTO:
    return FeedItemDTO(
        id=record.id,
        type=record.type,
        title=record.title,
        body=record.body,
        link=record.link,
        priority=record.priority,
        action_required=record.action_required,
        organization_id=record.organization_id,
        application_id=record.application_id,
        created_at=record.created_at,
        read_at=record.read_at,
    )


def feed_record_dto(record: FeedRecord) -> FeedRecordDTO:
    return FeedRecordDTO(item=feed_item_dto(record), seq=record.seq, audience=record.audience)
