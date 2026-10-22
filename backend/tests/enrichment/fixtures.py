"""«Чужой» формат ответов моков (кириллица, копейки, даты строками) для тестов адаптеров."""

from __future__ import annotations

ROMASHKA_EGRUL = {
    "ИНН": "7701158817",
    "ОГРН": "1027700399869",
    "НаимПолн": "Общество с ограниченной ответственностью «Ромашка»",
    "Статус": {"Код": "ACTIVE"},
    "ДатаРег": "2019-01-15",
    "ОКВЭДОсн": {"Код": "56.10"},
    "ОКВЭДДоп": [{"Код": "56.29"}],
    "Руководитель": {"ФИО": "Смирнова Анна Сергеевна", "Должность": "Генеральный директор"},
    "Учредители": [{"ФИО": "Смирнова Анна Сергеевна", "Доля": 100}],
    "Адрес": {"Полный": "г. Москва, ул. Тверская, д. 1", "КодРегиона": "77"},
    "МассовыйАдрес": False,
    "ОрганизационнаяФорма": "ООО",
    "КПП": "770101001",
}

ROMASHKA_FNS = {
    "inn": "7701158817",
    "arrears_kop": 0,
    "avg_headcount": 12,
    "revenue_kop": 4_750_000_000,
    "expenses_kop": 4_100_000_000,
    "tax_regime": "УСН",
    "disqualified_head": False,
    "msp_registry": True,
    "report_year": 2025,
}

ROMASHKA_BKI = {
    "obligations": [
        {
            "type": "loan",
            "creditor": "АО «Банк»",
            "amount_kop": 500_000_000,
            "outstanding_kop": 300_000_000,
            "monthly_payment_kop": 18_000_000,
            "opened": "2023-06-01",
            "closes": "2028-06-01",
            "overdue_days": 0,
            "max_overdue_days": 0,
        }
    ],
    "inquiries_30d": 1,
}

ZAKAT_EGRUL = {
    **ROMASHKA_EGRUL,
    "ИНН": "7703417070",
    "Статус": {"Код": "LIQUIDATING"},
    "Руководитель": {"ФИО": "Закатов Олег Олегович", "Должность": "Генеральный директор"},
}

ZAKAT_FNS = {
    **ROMASHKA_FNS,
    "inn": "7703417070",
    "arrears_kop": 35_000_000,
    "account_blocks": [
        {
            "decision_number": "4512",
            "date": "2026-09-30",
            "authority_code": "7703",
            "reason": "Неуплата налогов",
        }
    ],
}

# ГИР БО отдаёт периоды от новых к старым — адаптер сортирует; суммы в тыс. ₽.
ZAKAT_GIR_BO = {
    "inn": "7703417070",
    "unit": "тыс. руб.",
    "available": True,
    "reason": None,
    "periods": [
        {
            "year": 2025,
            "balance": {
                "1150_fixed_assets": 3150,
                "1210_inventories": 1800,
                "1230_receivables": 2700,
                "1250_cash": 1350,
                "1600_total_assets": 9000,
                "1300_equity": -2400,
                "1400_long_term_liabilities": 0,
                "1500_short_term_liabilities": 11400,
                "1700_total_liabilities": 9000,
            },
            "income": {
                "2110_revenue": 18000,
                "2120_cost_of_sales": 21000,
                "2200_sales_profit": -3000,
                "2330_interest_payable": 1100,
                "2300_profit_before_tax": -4100,
                "2400_net_profit": -4100,
            },
        },
        {
            "year": 2024,
            "balance": {
                "1150_fixed_assets": 3675,
                "1210_inventories": 2100,
                "1230_receivables": 3150,
                "1250_cash": 1575,
                "1600_total_assets": 10500,
                "1300_equity": 600,
                "1400_long_term_liabilities": 0,
                "1500_short_term_liabilities": 9900,
                "1700_total_liabilities": 10500,
            },
            "income": {
                "2110_revenue": 21000,
                "2120_cost_of_sales": 20500,
                "2200_sales_profit": 500,
                "2330_interest_payable": 950,
                "2300_profit_before_tax": -450,
                "2400_net_profit": -450,
            },
        },
    ],
}

IVANOV_GIR_BO = {
    "inn": "770669871605",
    "unit": "тыс. руб.",
    "available": False,
    "reason": "ИП не сдают бухгалтерскую отчётность в ГИР БО",
    "periods": [],
}

ZAKAT_KONTUR = {
    "inn": "7703417070",
    "reliability": "red",
    "reliability_notes": ["Юрлицо в процессе ликвидации", "Исполнительные производства"],
    "arbitration": {"as_defendant": 6, "as_plaintiff": 0, "defendant_sum_rub": 5_200_000},
    "enforcement_proceedings": {"active": 4, "sum_rub": 2_600_000},
    "gov_contracts": {"count": 0, "sum_rub": 0},
    "bankruptcy_messages": [
        {"date": "2026-08-12", "type": "Введение процедуры наблюдения", "case": "А40-1234/2026"}
    ],
    "active_pledges": 1,
    "affiliated_companies": 2,
    "checked_at": "2026-10-21",
}

ZAKATOV_BKI = {
    "subject": {"last_name": "Закатов", "first_name": "Олег", "middle_name": "Олегович"},
    "obligations": [
        {
            "type": "consumer",
            "creditor": "ПАО «Кредит»",
            "amount_kop": 80_000_000,
            "outstanding_kop": 65_000_000,
            "monthly_payment_kop": 2_700_000,
            "opened": "2024-03-01",
            "closes": "2028-03-01",
            "overdue_days": 45,
            "max_overdue_days": 45,
        }
    ],
    "inquiries_30d": 4,
}
