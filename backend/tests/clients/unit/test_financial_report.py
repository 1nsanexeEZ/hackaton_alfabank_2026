from uuid import uuid4

import pytest

from src.core.domain import Money
from src.core.exceptions.exceptions import NotFoundError, PermissionDeniedError, ValidationError
from src.modules.clients.domain.events import FinancialReportSubmitted
from src.modules.clients.domain.financial_report import ReportFigures, ReportSource
from src.modules.clients.domain.member import Actor
from src.modules.clients.domain.rights import MemberRole
from src.modules.clients.domain.value_objects import FiscalPeriod
from tests.clients.unit.factories import BANK, NOW, add, with_head

FIGURES = ReportFigures(revenue=Money.of(48_000_000), expenses=Money.of(41_000_000))


def test_accountant_declares_a_report() -> None:
    org, _ = with_head("romashka")
    accountant = add(org, MemberRole.ACCOUNTANT)
    report_id = uuid4()

    report = org.submit_financial_report(
        Actor.member(accountant),
        report_id=report_id,
        period=FiscalPeriod(2025),
        figures=FIGURES,
        now=NOW,
    )

    assert report.id == report_id and report.organization_id == org.id
    assert report.source is ReportSource.DECLARED
    assert report.submitted_by == accountant and report.submitted_at == NOW
    assert report.pull_events() == [
        FinancialReportSubmitted(
            occurred_at=NOW,
            organization_id=org.id,
            report_id=report_id,
            period_year=2025,
            period_quarter=None,
            source="declared",
        )
    ]


def test_only_members_with_edit_financials() -> None:
    org, _ = with_head("romashka")
    employee = add(org, MemberRole.EMPLOYEE)
    kwargs = {"report_id": uuid4(), "period": FiscalPeriod(2025), "figures": FIGURES, "now": NOW}
    with pytest.raises(PermissionDeniedError):
        org.submit_financial_report(Actor.member(employee), **kwargs)  # type: ignore[arg-type]
    with pytest.raises(NotFoundError):
        org.submit_financial_report(Actor.member(uuid4()), **kwargs)  # type: ignore[arg-type]


def test_client_declares_only() -> None:
    org, head_id = with_head("romashka")
    kwargs = {"report_id": uuid4(), "period": FiscalPeriod(2025), "figures": FIGURES, "now": NOW}
    with pytest.raises(PermissionDeniedError) as error:
        org.submit_financial_report(Actor.member(head_id), source=ReportSource.FNS, **kwargs)  # type: ignore[arg-type]
    assert error.value.details == {"code": "source_not_allowed", "source": "fns"}

    report = org.submit_financial_report(BANK, source=ReportSource.FNS, **kwargs)  # type: ignore[arg-type]
    assert report.source is ReportSource.FNS and report.submitted_by is None


@pytest.mark.parametrize(
    "period,closed",
    [
        (FiscalPeriod(2026), False),
        (FiscalPeriod(2026, 4), False),
        (FiscalPeriod(2026, 3), True),  # ended on 30.09, now is 21.10
        (FiscalPeriod(2025), True),
    ],
)
def test_period_must_be_over(period: FiscalPeriod, closed: bool) -> None:
    org, head_id = with_head("romashka")

    def submit() -> None:
        org.submit_financial_report(
            Actor.member(head_id), report_id=uuid4(), period=period, figures=FIGURES, now=NOW
        )

    if closed:
        submit()
    else:
        with pytest.raises(ValidationError) as error:
            submit()
        assert error.value.details is not None
        assert error.value.details["code"] == "period_not_closed"


def test_resubmission_revises_the_report() -> None:
    org, head_id = with_head("romashka")
    accountant = add(org, MemberRole.ACCOUNTANT)
    first = org.submit_financial_report(
        Actor.member(head_id),
        report_id=uuid4(),
        period=FiscalPeriod(2025),
        figures=FIGURES,
        now=NOW,
    )
    first.pull_events()
    corrected = ReportFigures(revenue=Money.of(50_000_000), net_profit=Money.of(-1_000))

    same = org.submit_financial_report(
        Actor.member(accountant),
        report_id=uuid4(),
        period=FiscalPeriod(2025),
        figures=corrected,
        now=NOW,
        existing=first,
    )

    assert same is first
    assert first.figures == corrected and first.submitted_by == accountant
    assert [type(e) for e in first.pull_events()] == [FinancialReportSubmitted]
    with pytest.raises(ValueError):
        org.submit_financial_report(
            Actor.member(head_id),
            report_id=uuid4(),
            period=FiscalPeriod(2024),
            figures=FIGURES,
            now=NOW,
            existing=first,
        )


@pytest.mark.parametrize(
    "kwargs,field,code",
    [
        ({"revenue": Money.of(-1)}, "revenue", "negative"),
        ({"expenses": Money.of(-1)}, "expenses", "negative"),
        ({"total_liabilities": Money.of(-1)}, "total_liabilities", "negative"),
        ({"monthly_debt_payments": Money.of(-1)}, "monthly_debt_payments", "negative"),
        ({"expenses": Money.of(1, "USD")}, "expenses", "currency_mismatch"),
    ],
)
def test_figures_validation(kwargs: dict, field: str, code: str) -> None:
    values = {"revenue": Money.of(1_000), **kwargs}
    with pytest.raises(ValidationError) as error:
        ReportFigures(**values)
    assert error.value.details == {"field": field, "code": code}


def test_loss_is_allowed() -> None:
    assert ReportFigures(revenue=Money.of(0), net_profit=Money.of(-5)).net_profit == Money.of(-5)
