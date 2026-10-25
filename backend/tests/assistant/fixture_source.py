"""Context source on fixtures: the S-1…S-8 applications and the product catalog
as the facades return them (`data/demo.json`, `data/products.json`, exported
from `seed` and the decision golden files). The question set runs on it; the
adapter over the real facades has its own tests (test_context_source.py)."""

import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

from src.core.domain import Money
from src.modules.assistant.application.interfaces.context import ContextSource
from src.modules.assistant.domain.exceptions import ApplicationNotFoundError
from src.modules.assistant.domain.views import (
    ApplicationView,
    ClientDecisionView,
    DecisionTermsView,
    InfoRequestView,
    LoanRequestView,
    PaymentView,
    ProductView,
    RequestedInfoView,
    RequiredDocumentView,
    Viewer,
)
from src.modules.products.domain.calculator import PaymentCalculator

DATA_DIR = Path(__file__).resolve().parent / "data"


class DemoAccount:
    def __init__(self, raw: dict[str, Any]) -> None:
        self.login: str = raw["login"]
        self.account_id = UUID(raw["account_id"])
        self.role: str = raw["role"]
        self.organization_ids = frozenset(UUID(o) for o in raw["organization_ids"])
        self.can_sign: bool = raw["can_sign"]


class FixtureContextSource(ContextSource):
    def __init__(self, data_dir: Path = DATA_DIR) -> None:
        demo = json.loads((data_dir / "demo.json").read_text(encoding="utf-8"))
        catalog = json.loads((data_dir / "products.json").read_text(encoding="utf-8"))
        self.accounts = {a["login"]: DemoAccount(a) for a in demo["accounts"]}
        self._can_sign = {a.account_id: a.can_sign for a in self.accounts.values()}
        self._apps: dict[UUID, ApplicationView] = {}
        self._decisions: dict[UUID, ClientDecisionView] = {}
        self.scenarios: dict[str, UUID] = {}
        for raw in demo["applications"]:
            app = _application(raw)
            self._apps[app.id] = app
            self.scenarios[raw["scenario"]] = app.id
            if raw.get("decision"):
                self._decisions[app.id] = _decision(raw["decision"])
        self._products = [_product(p) for p in catalog]

    async def get_application(self, viewer: Viewer, application_id: UUID) -> ApplicationView:
        app = self._apps.get(application_id)
        if app is None or not viewer.may_see(app.organization_id):
            raise ApplicationNotFoundError()
        can_sign = viewer.organization_ids is not None and self._can_sign[viewer.account_id]
        return ApplicationView(**{**_fields(app), "viewer_can_sign": can_sign})

    async def list_applications(self, viewer: Viewer) -> list[ApplicationView]:
        if viewer.organization_ids is None:
            return []
        apps = [a for a in self._apps.values() if viewer.may_see(a.organization_id)]
        return sorted(apps, key=lambda a: a.number)

    async def get_client_decision(
        self, viewer: Viewer, application_id: UUID
    ) -> ClientDecisionView | None:
        await self.get_application(viewer, application_id)
        return self._decisions.get(application_id)

    async def list_products(self) -> list[ProductView]:
        return list(self._products)

    def calculate_payment(
        self, amount: Decimal, term_months: int, rate: Decimal, repayment: str
    ) -> PaymentView:
        try:
            schedule = PaymentCalculator().schedule(Money(amount), term_months, rate, repayment)
        except Exception as error:  # the products module's ValidationError
            raise ValueError(str(error)) from None
        return PaymentView(
            amount=amount,
            term_months=term_months,
            rate=rate,
            repayment=repayment,
            monthly_payment=schedule.monthly_payment.amount,
            total_interest=schedule.total_interest.amount,
            total_paid=schedule.total_paid.amount,
        )


def _fields(app: ApplicationView) -> dict[str, Any]:
    return {name: getattr(app, name) for name in ApplicationView.__slots__}


def _application(raw: dict[str, Any]) -> ApplicationView:
    request = raw.get("request")
    return ApplicationView(
        id=UUID(raw["id"]),
        number=raw["number"],
        organization_id=UUID(raw["organization_id"]),
        product_code=raw["product_code"],
        status=raw["status"],
        client_stage=raw.get("client_stage"),
        request=LoanRequestView(
            amount=Decimal(request["amount"]),
            term_months=request["term_months"],
            purpose=request["purpose"],
            purpose_comment=request.get("purpose_comment"),
        )
        if request
        else None,
        info_requests=tuple(
            InfoRequestView(
                requested_fields=tuple(r["requested_fields"]),
                requested_documents=tuple(r["requested_documents"]),
                comment=r["comment"],
                due_at=datetime.fromisoformat(r["due_at"]) if r.get("due_at") else None,
                status=r["status"],
            )
            for r in raw.get("info_requests", [])
        ),
        updated_at=datetime.fromisoformat(raw["updated_at"]),
    )


def _decision(raw: dict[str, Any]) -> ClientDecisionView:
    terms = raw.get("terms")
    info = raw.get("requested_info")
    return ClientDecisionView(
        outcome=raw["outcome"],
        terms=DecisionTermsView(
            amount=Decimal(terms["amount"]),
            term_months=terms["term_months"],
            rate=Decimal(terms["rate"]),
            monthly_payment=Decimal(terms["monthly_payment"]),
            schedule_type=terms["schedule_type"],
            conditions=tuple(terms["conditions"]),
            expires_at=datetime.fromisoformat(terms["expires_at"]),
        )
        if terms
        else None,
        alternative_product_code=raw.get("alternative_product_code"),
        client_explanation=raw["client_explanation"],
        improvement_hints=tuple(raw.get("improvement_hints", [])),
        requested_info=RequestedInfoView(
            fields=tuple(info["fields"]),
            documents=tuple(info["documents"]),
            comment=info["comment"],
        )
        if info
        else None,
    )


def _product(raw: dict[str, Any]) -> ProductView:
    program = raw.get("support_program")
    return ProductView(
        code=raw["code"],
        name=raw["name"],
        short_description=raw["short_description"],
        description_plain=raw["description_plain"],
        purposes=tuple(raw["purposes"]),
        facility=raw["facility"],
        repayment_options=tuple(raw["repayment_options"]),
        amount_min=Decimal(raw["amount_min"]),
        amount_max=Decimal(raw["amount_max"]),
        term_min_months=raw["term_min_months"],
        term_max_months=raw["term_max_months"],
        rate_base=Decimal(raw["rate_base"]),
        rate_max=Decimal(raw["rate_max"]),
        collateral_kind=raw["collateral_kind"],
        collateral_types=tuple(raw["collateral_types"]),
        min_business_age_months=raw["min_business_age_months"],
        min_annual_revenue=Decimal(raw["min_annual_revenue"])
        if raw.get("min_annual_revenue")
        else None,
        required_documents=tuple(
            RequiredDocumentView(
                type=d["type"],
                title=d["title"],
                required_from_amount=Decimal(d["required_from_amount"])
                if d.get("required_from_amount")
                else None,
                legal_forms=tuple(d.get("legal_forms", [])),
            )
            for d in raw["required_documents"]
        ),
        support_program_name=program["name"] if program else None,
        support_rate_cap=Decimal(program["rate_cap"]) if program else None,
    )
