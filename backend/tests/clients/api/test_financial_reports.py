from decimal import Decimal

from src.modules.clients.facade import FinancialReportDTO
from tests.clients.api.conftest import KUZNETSOVA, PETROV, SMIRNOVA, Demo


def reports_url(demo: Demo, code: str) -> str:
    return f"/organizations/{demo.orgs[code]}/financial-reports"


def test_seeded_reports(demo: Demo) -> None:
    body = demo.client.get(reports_url(demo, "romashka"), headers=demo.as_client(KUZNETSOVA))
    assert body.status_code == 200
    assert [
        (r["period_year"], r["period_quarter"], r["source"], r["revenue"], r["expenses"])
        for r in body.json()
    ] == [
        (2025, None, "declared", "48000000.00", "41000000.00"),
        (2024, None, "declared", "40000000.00", None),
    ]
    ivanov = demo.client.get(reports_url(demo, "ivanov"), headers=demo.as_client(KUZNETSOVA))
    assert len(ivanov.json()) == 1


def test_accountant_declares_a_quarter(demo: Demo) -> None:
    response = demo.client.post(
        reports_url(demo, "romashka"),
        json={
            "period_year": 2026,
            "period_quarter": 3,
            "revenue": "12500000.50",
            "expenses": "11000000",
            "net_profit": "-15000",
            "monthly_debt_payments": "180000",
        },
        headers=demo.as_client(KUZNETSOVA),
    )
    assert response.status_code == 201, response.text
    report = response.json()
    assert (report["period_year"], report["period_quarter"]) == (2026, 3)
    assert report["revenue"] == "12500000.50" and report["net_profit"] == "-15000.00"
    assert report["submitted_by"] == str(demo.id_of(KUZNETSOVA))

    [record] = demo.outbox()
    assert record.message_type == "FinancialReportSubmitted"
    assert record.key == str(demo.orgs["romashka"])
    assert record.envelope["payload"] == {
        "organization_id": str(demo.orgs["romashka"]),
        "period_year": 2026,
        "period_quarter": 3,
    }
    years = [
        r["period_quarter"]
        for r in demo.client.get(
            reports_url(demo, "romashka"), headers=demo.as_client(SMIRNOVA)
        ).json()
    ]
    assert years == [3, None, None]


def test_same_period_revises_the_report(demo: Demo) -> None:
    response = demo.client.post(
        reports_url(demo, "romashka"),
        json={"period_year": 2025, "revenue": "50000000"},
        headers=demo.as_client(SMIRNOVA),
    )
    assert response.status_code == 200
    assert response.json()["revenue"] == "50000000.00" and response.json()["expenses"] is None
    reports = demo.client.get(reports_url(demo, "romashka"), headers=demo.as_client(SMIRNOVA))
    assert len(reports.json()) == 2

    async def snapshot(facade):  # type: ignore[no-untyped-def]
        return await facade.get_snapshot(demo.orgs["romashka"])

    assert demo.facade_call(snapshot).financial_reports[0] == FinancialReportDTO(
        period_year=2025, period_quarter=None, source="declared", revenue=Decimal("50000000")
    )
    assert [r.message_type for r in demo.outbox()] == ["FinancialReportSubmitted"]


def test_report_rules(demo: Demo) -> None:
    headers = demo.as_client(SMIRNOVA)
    current_year = demo.client.post(
        reports_url(demo, "romashka"), json={"period_year": 2026, "revenue": "1"}, headers=headers
    )
    assert current_year.status_code == 422
    assert current_year.json()["details"]["code"] == "period_not_closed"
    negative = demo.client.post(
        reports_url(demo, "romashka"), json={"period_year": 2025, "revenue": "-1"}, headers=headers
    )
    assert negative.status_code == 422
    stranger = demo.client.post(
        reports_url(demo, "romashka"),
        json={"period_year": 2025, "revenue": "1"},
        headers=demo.as_client(PETROV),
    )
    assert stranger.status_code == 404
    underwriter = demo.client.post(
        reports_url(demo, "romashka"),
        json={"period_year": 2025, "revenue": "1"},
        headers=demo.as_underwriter(),
    )
    assert underwriter.status_code == 403
    assert demo.outbox() == []


def test_employee_does_not_edit_financials(demo: Demo) -> None:
    employee = demo.identity.add_account(email="employee@romashka.test")
    added = demo.client.post(
        f"/organizations/{demo.orgs['romashka']}/members",
        json={"login": "employee@romashka.test", "role": "employee"},
        headers=demo.as_client(SMIRNOVA),
    )
    assert added.status_code == 201
    headers = demo.headers(
        ["organizations.read", "organizations.update"],
        {"organizations.read": ["org_member"], "organizations.update": ["org_member"]},
        employee.id,
    )
    response = demo.client.post(
        reports_url(demo, "romashka"), json={"period_year": 2025, "revenue": "1"}, headers=headers
    )
    assert response.status_code == 403
    assert response.json()["details"]["permission"] == "edit_financials"
