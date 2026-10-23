"""Enumerations of the applications module."""

from enum import StrEnum


class ApplicationStatus(StrEnum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    IN_REVIEW = "in_review"
    INFO_REQUESTED = "info_requested"
    OFFER_READY = "offer_ready"
    SIGNING = "signing"
    SIGNED = "signed"
    DISBURSED = "disbursed"
    REJECTED = "rejected"
    OFFER_DECLINED = "offer_declined"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class DocumentStatus(StrEnum):
    PENDING_UPLOAD = "pending_upload"
    UPLOADED = "uploaded"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class InfoRequestStatus(StrEnum):
    OPEN = "open"
    ANSWERED = "answered"
    EXPIRED = "expired"
