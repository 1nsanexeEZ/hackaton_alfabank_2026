"""Enumerations of clients: rights inside a company (not to be confused with
token permissions), legal and tax forms, registry and check statuses, sources
of the financial figures."""

from enum import StrEnum


class OrgPermission(StrEnum):
    VIEW = "view"
    SUBMIT_APPLICATION = "submit_application"
    SIGN = "sign"
    MANAGE_MEMBERS = "manage_members"
    EDIT_FINANCIALS = "edit_financials"


class MemberRole(StrEnum):
    OWNER = "owner"
    DIRECTOR = "director"
    ACCOUNTANT = "accountant"
    EMPLOYEE = "employee"


class Authority(StrEnum):
    """Why the member may act for the company."""

    REGISTRY = "registry"
    POWER_OF_ATTORNEY = "power_of_attorney"
    UNCONFIRMED = "unconfirmed"


class LegalForm(StrEnum):
    LLC = "LLC"  # ООО
    IE = "IE"  # ИП
    JSC = "JSC"  # АО

    @property
    def is_entrepreneur(self) -> bool:
        return self is LegalForm.IE


class RegistryStatus(StrEnum):
    """Status in ЕГРЮЛ/ЕГРИП. Submission is not blocked by it here: the stop
    factor belongs to decision."""

    ACTIVE = "active"
    LIQUIDATING = "liquidating"
    LIQUIDATED = "liquidated"
    BANKRUPT = "bankrupt"


class TaxRegime(StrEnum):
    OSN = "osn"
    USN = "usn"
    AUSN = "ausn"
    ESHN = "eshn"
    PATENT = "patent"


class VerificationStatus(StrEnum):
    UNVERIFIED = "unverified"
    VERIFIED = "verified"
    MISMATCH = "mismatch"


class ReportSource(StrEnum):
    # Typed in by the client.
    DECLARED = "declared"
    # From the tax service (enrichment).
    FNS = "fns"
    # Computed from a bank statement.
    BANK_STATEMENT = "bank_statement"
