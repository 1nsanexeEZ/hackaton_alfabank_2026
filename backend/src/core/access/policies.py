from enum import StrEnum


class Policies(StrEnum):
    NOT_DELETED = "not_deleted"
    OWN_ONLY = "own_only"
    # Row belongs to an organization the user is a member of (OrganizationOwnedMixin).
    ORG_MEMBER = "org_member"
