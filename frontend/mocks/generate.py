import json, random, sys

random.seed(2026)

W10 = [2, 4, 10, 3, 5, 9, 4, 6, 8]
W11 = [7, 2, 4, 10, 3, 5, 9, 4, 6, 8]
W12 = [3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8]


def cs(d, w):
    return sum(a * b for a, b in zip(d, w)) % 11 % 10


def inn10(prefix):
    d = [int(c) for c in prefix] + [random.randint(0, 9) for _ in range(9 - len(prefix))]
    return "".join(map(str, d + [cs(d, W10)]))


def inn12(prefix):
    d = [int(c) for c in prefix] + [random.randint(0, 9) for _ in range(10 - len(prefix))]
    d.append(cs(d, W11))
    d.append(cs(d, W12))
    return "".join(map(str, d))


def ogrn(year, region):
    body = f"1{year % 100:02d}{region}" + "".join(str(random.randint(0, 9)) for _ in range(7))
    return body + str(int(body) % 11 % 10)


def ogrnip(year, region):
    body = f"3{year % 100:02d}{region}" + "".join(str(random.randint(0, 9)) for _ in range(9))
    return body + str(int(body) % 13 % 10)


def kpp(inn):
    return inn[:4] + "01001"


def person_inn(region):
    return inn12(region)


# Проверка демо-ИНН из формы
assert cs([int(c) for c in "772012345"], W10) == 7

AUTH = {
    "77": "Межрайонная инспекция ФНС № 46 по г. Москве",
    "78": "Межрайонная инспекция ФНС № 15 по Санкт-Петербургу",
    "66": "Инспекция ФНС по Верх-Исетскому району г. Екатеринбурга",
    "16": "Межрайонная инспекция ФНС № 18 по Республике Татарстан",
    "54": "Инспекция ФНС по Центральному району г. Новосибирска",
    "23": "Инспекция ФНС № 1 по г. Краснодару",
    "52": "Межрайонная инспекция ФНС № 15 по Нижегородской области",
    "63": "Инспекция ФНС по Ленинскому району г. Самары",
}

OKVED = {
    "25.62": "Обработка металлических изделий механическая",
    "28.99": "Производство прочих машин и оборудования специального назначения",
    "33.12": "Ремонт машин и оборудования",
    "41.20": "Строительство жилых и нежилых зданий",
    "43.39": "Производство прочих отделочных и завершающих работ",
    "46.90": "Торговля оптовая неспециализированная",
    "47.11": "Торговля розничная преимущественно пищевыми продуктами в неспециализированных магазинах",
    "47.91": "Торговля розничная по почте или по информационно-коммуникационной сети Интернет",
    "49.41": "Деятельность автомобильного грузового транспорта",
    "52.10": "Деятельность по складированию и хранению",
    "56.10": "Деятельность ресторанов и услуги по доставке продуктов питания",
    "62.01": "Разработка компьютерного программного обеспечения",
    "62.02": "Деятельность консультативная и работы в области компьютерных технологий",
    "68.20": "Аренда и управление собственным или арендованным недвижимым имуществом",
    "73.11": "Деятельность рекламных агентств",
    "86.23": "Стоматологическая практика",
    "96.02": "Предоставление услуг парикмахерскими и салонами красоты",
    "10.71": "Производство хлеба и мучных кондитерских изделий",
}


def okved(main, extra):
    return {
        "main": {"code": main, "name": OKVED[main]},
        "additional": [{"code": c, "name": OKVED[c]} for c in extra],
    }


def money(x):
    return int(round(x / 1000) * 1000)


def financials(revenue, margin, assets, equity_share, debt_lt, growth):
    """ГИР БО: строки бухгалтерского баланса и отчёта о финрезультатах, тыс. руб."""
    out = []
    rev_prev = revenue / (1 + growth)
    for year, rev, k in ((2024, rev_prev, 0.92), (2025, revenue, 1.0)):
        rev = rev / 1000
        net = rev * margin
        a = assets / 1000 * k
        eq = a * equity_share
        lt = debt_lt / 1000 * k
        st = max(a - eq - lt, 0)
        cost = rev * (1 - margin) * 0.82
        out.append({
            "year": year,
            "balance": {
                "1150_fixed_assets": round(a * 0.38),
                "1210_inventories": round(a * 0.21),
                "1230_receivables": round(a * 0.24),
                "1250_cash": round(a * 0.09),
                "1600_total_assets": round(a),
                "1300_equity": round(eq),
                "1400_long_term_liabilities": round(lt),
                "1500_short_term_liabilities": round(st),
                "1700_total_liabilities": round(a),
            },
            "income": {
                "2110_revenue": round(rev),
                "2120_cost_of_sales": round(cost),
                "2200_sales_profit": round(rev - cost - rev * (1 - margin) * 0.12),
                "2330_interest_payable": round(lt * 0.14 + st * 0.05),
                "2300_profit_before_tax": round(net * 1.2 if net > 0 else net),
                "2400_net_profit": round(net),
            },
        })
    return out


def taxes(revenue, regime, years_ok=True):
    rate = {"УСН (доходы минус расходы)": 0.035, "УСН (доходы)": 0.05, "ОСНО": 0.06, "ПСН": 0.008, "АУСН": 0.06}[regime]
    return [
        {"year": 2024, "paid_rub": money(revenue / 1.15 * rate)},
        {"year": 2025, "paid_rub": money(revenue * rate if years_ok else revenue * rate * 0.3)},
    ]


companies = []
entrepreneurs = []


def company(
    *, inn=None, region, short, full, opf="ООО", reg, status="Действующее", status_date=None,
    capital, director, founders, ok, address, employees, regime, revenue, margin, assets,
    equity_share, debt_lt, growth, scenario, expected, msp="Микропредприятие",
    arrears=0, blocks=None, mass_address=False, unreliable=None, disq=False,
    arbitr=None, fssp=None, contracts=0, bankrupt_msgs=None, pledges=0, marker="green",
    marker_notes=None, has_bo=True,
):
    inn = inn or inn10(region + "0" + str(random.randint(1, 9)))
    reg_year = int(reg[:4])
    og = ogrn(reg_year, region)
    blocks = blocks or []
    arbitr = arbitr or {"as_defendant": 0, "as_plaintiff": 0, "defendant_sum_rub": 0}
    fssp = fssp or {"active": 0, "sum_rub": 0}
    founders_out = []
    for f in founders:
        founders_out.append({"name": f[0], "inn": person_inn(region), "share_percent": f[1], "share_rub": money(capital * f[1] / 100)})
    rec = {
        "scenario": scenario,
        "expected_outcome": expected,
        "egrul": {
            "inn": inn,
            "kpp": kpp(inn),
            "ogrn": og,
            "opf": {"ООО": "Общество с ограниченной ответственностью", "АО": "Акционерное общество"}[opf],
            "name_full": full,
            "name_short": short,
            "status": status,
            "status_date": status_date,
            "registration_date": reg,
            "registration_authority": AUTH[region],
            "address": {"region_code": region, "full": address, "unreliable": bool(unreliable and "address" in unreliable)},
            "authorized_capital_rub": capital,
            "director": {
                "position": "Генеральный директор",
                "name": director,
                "inn": person_inn(region),
                "since": reg,
                "unreliable": bool(unreliable and "director" in unreliable),
            },
            "founders": founders_out,
            "okved": okved(*ok),
            "last_update": "2026-10-01",
        },
        "fns": {
            "tax_regime": regime,
            "average_headcount": employees,
            "msp_register": {"included": msp is not None, "category": msp},
            "taxes_paid": taxes(revenue, regime, years_ok=arrears == 0),
            "tax_arrears_rub": arrears,
            "account_blocks": blocks,
            "mass_registration_address": mass_address,
            "disqualified_persons": disq,
            "unreliable_data": unreliable or [],
            "checked_at": "2026-10-20",
        },
        "gir_bo": {"available": has_bo, "currency": "RUB", "unit": "тыс. руб.", "periods": financials(revenue, margin, assets, equity_share, debt_lt, growth) if has_bo else []},
        "kontur": {
            "reliability": marker,
            "reliability_notes": marker_notes or [],
            "arbitration": arbitr,
            "enforcement_proceedings": fssp,
            "gov_contracts": {"count": contracts, "sum_rub": money(contracts * revenue * 0.04)},
            "bankruptcy_messages": bankrupt_msgs or [],
            "active_pledges": pledges,
            "affiliated_companies": random.randint(0, 4),
            "checked_at": "2026-10-20",
        },
    }
    companies.append(rec)


def ip(
    *, region, fio, reg, status="Действующий", status_date=None, ok, employees, regime,
    revenue, scenario, expected, arrears=0, blocks=None, arbitr=None, fssp=None,
    marker="green", marker_notes=None, bankrupt_msgs=None, msp="Микропредприятие",
):
    inn = inn12(region + "0" + str(random.randint(1, 9)))
    rec = {
        "scenario": scenario,
        "expected_outcome": expected,
        "egrip": {
            "inn": inn,
            "ogrnip": ogrnip(int(reg[:4]), region),
            "fio": fio,
            "citizenship": "Российская Федерация",
            "status": status,
            "status_date": status_date,
            "registration_date": reg,
            "registration_authority": AUTH[region],
            "region_code": region,
            "okved": okved(*ok),
            "last_update": "2026-10-01",
        },
        "fns": {
            "tax_regime": regime,
            "average_headcount": employees,
            "msp_register": {"included": msp is not None, "category": msp},
            "taxes_paid": taxes(revenue, regime, years_ok=arrears == 0),
            "tax_arrears_rub": arrears,
            "account_blocks": blocks or [],
            "mass_registration_address": False,
            "disqualified_persons": False,
            "unreliable_data": [],
            "checked_at": "2026-10-20",
        },
        "gir_bo": {"available": False, "reason": "ИП не сдают бухгалтерскую отчётность в ГИР БО", "periods": []},
        "kontur": {
            "reliability": marker,
            "reliability_notes": marker_notes or [],
            "arbitration": arbitr or {"as_defendant": 0, "as_plaintiff": 0, "defendant_sum_rub": 0},
            "enforcement_proceedings": fssp or {"active": 0, "sum_rub": 0},
            "gov_contracts": {"count": 0, "sum_rub": 0},
            "bankruptcy_messages": bankrupt_msgs or [],
            "active_pledges": 0,
            "affiliated_companies": random.randint(0, 2),
            "checked_at": "2026-10-20",
        },
    }
    entrepreneurs.append(rec)


# --- Юрлица ---
company(
    inn="7720123457", region="77", short="ООО «ТехноПрофиль»", full="Общество с ограниченной ответственностью «ТехноПрофиль»",
    reg="2017-03-14", capital=500_000, director="Смирнова Анна Викторовна",
    founders=[("Смирнова Анна Викторовна", 60), ("Голубев Максим Олегович", 40)],
    ok=("25.62", ["28.99", "33.12"]), address="111123, г. Москва, ш. Энтузиастов, д. 56, стр. 3, помещ. 12",
    employees=48, regime="ОСНО", revenue=186_400_000, margin=0.071, assets=92_000_000, equity_share=0.46,
    debt_lt=18_000_000, growth=0.14, contracts=3, pledges=1, msp="Малое предприятие",
    scenario="Демо-ИНН из формы: устойчивый производственный бизнес, растущая выручка", expected="approved",
)
company(
    region="78", short="ООО «Северная Пекарня»", full="Общество с ограниченной ответственностью «Северная Пекарня»",
    reg="2015-09-02", capital=100_000, director="Ковалёв Игорь Сергеевич",
    founders=[("Ковалёв Игорь Сергеевич", 100)],
    ok=("10.71", ["47.11", "56.10"]), address="197342, г. Санкт-Петербург, ул. Сердобольская, д. 64, лит. К, помещ. 3-Н",
    employees=31, regime="УСН (доходы минус расходы)", revenue=74_800_000, margin=0.088, assets=31_000_000,
    equity_share=0.55, debt_lt=4_000_000, growth=0.09,
    scenario="Пекарня с сетью точек, стабильные показатели, без долгов", expected="approved",
)
company(
    region="66", short="ООО «УралЛогистик»", full="Общество с ограниченной ответственностью «УралЛогистик»",
    reg="2019-06-20", capital=250_000, director="Шайхутдинов Ренат Ильдарович",
    founders=[("Шайхутдинов Ренат Ильдарович", 51), ("Морозова Ольга Петровна", 49)],
    ok=("49.41", ["52.10"]), address="620075, Свердловская обл., г. Екатеринбург, ул. Бажова, д. 79, оф. 410",
    employees=22, regime="ОСНО", revenue=128_000_000, margin=0.018, assets=67_000_000, equity_share=0.14,
    debt_lt=39_000_000, growth=0.03, pledges=4,
    arbitr={"as_defendant": 3, "as_plaintiff": 5, "defendant_sum_rub": 2_480_000}, marker="yellow",
    marker_notes=["Высокая долговая нагрузка", "Арбитражные дела в качестве ответчика за последний год"],
    scenario="Грузоперевозки с высокой долговой нагрузкой и низкой маржой", expected="counter_offer",
)
company(
    region="16", short="ООО «КазаньСофт»", full="Общество с ограниченной ответственностью «КазаньСофт»",
    reg="2025-11-10", capital=10_000, director="Гарипова Алсу Рустемовна",
    founders=[("Гарипова Алсу Рустемовна", 100)],
    ok=("62.01", ["62.02"]), address="420107, Республика Татарстан, г. Казань, ул. Петербургская, д. 52, оф. 214",
    employees=4, regime="УСН (доходы)", revenue=6_200_000, margin=0.21, assets=2_100_000, equity_share=0.7,
    debt_lt=0, growth=0.0, has_bo=False, marker="yellow", marker_notes=["Компания зарегистрирована менее 12 месяцев назад"],
    scenario="Молодой бизнес: меньше года, отчётности в ГИР БО ещё нет", expected="info_requested",
)
company(
    region="54", short="ООО «СибСтройМонтаж»", full="Общество с ограниченной ответственностью «СибСтройМонтаж»",
    reg="2016-04-08", capital=10_000, director="Петренко Виталий Андреевич",
    founders=[("Петренко Виталий Андреевич", 100)],
    ok=("41.20", ["43.39"]), address="630099, Новосибирская обл., г. Новосибирск, ул. Советская, д. 5, оф. 1",
    employees=7, regime="ОСНО", revenue=41_000_000, margin=-0.064, assets=58_000_000, equity_share=-0.08,
    debt_lt=22_000_000, growth=-0.37, arrears=1_870_000, mass_address=True,
    blocks=[{"decision_number": "12345", "date": "2026-09-18", "authority_code": "5406", "reason": "Неуплата налогов"}],
    arbitr={"as_defendant": 14, "as_plaintiff": 1, "defendant_sum_rub": 19_300_000},
    fssp={"active": 9, "sum_rub": 6_740_000}, marker="red",
    marker_notes=["Приостановлены операции по счетам", "Налоговая задолженность", "Адрес массовой регистрации", "Отрицательные чистые активы"],
    scenario="Стоп-факторы: блокировка счёта, недоимка, исполнительные производства", expected="rejected",
)
company(
    region="23", short="ООО «Южный Терминал»", full="Общество с ограниченной ответственностью «Южный Терминал»",
    reg="2012-02-15", status="Ликвидировано", status_date="2026-05-27", capital=10_000,
    director="Захарченко Денис Николаевич", founders=[("Захарченко Денис Николаевич", 100)],
    ok=("52.10", ["46.90"]), address="350000, Краснодарский край, г. Краснодар, ул. Северная, д. 324, оф. 7",
    employees=0, regime="ОСНО", revenue=0, margin=0, assets=0, equity_share=0, debt_lt=0, growth=0,
    msp=None, has_bo=False, marker="red", marker_notes=["Юрлицо ликвидировано"],
    scenario="Компания ликвидирована, заявку принимать нельзя", expected="rejected",
)
company(
    region="52", short="ООО «ВолгаТорг»", full="Общество с ограниченной ответственностью «ВолгаТорг»",
    reg="2018-07-30", status="В стадии банкротства", status_date="2026-08-12", capital=20_000,
    director="Лаптев Сергей Геннадьевич", founders=[("Лаптев Сергей Геннадьевич", 50), ("Лаптева Марина Юрьевна", 50)],
    ok=("46.90", ["47.91"]), address="603005, Нижегородская обл., г. Нижний Новгород, ул. Алексеевская, д. 10/16, оф. 302",
    employees=3, regime="ОСНО", revenue=12_000_000, margin=-0.22, assets=9_500_000, equity_share=-0.4,
    debt_lt=6_000_000, growth=-0.61, arrears=640_000,
    arbitr={"as_defendant": 21, "as_plaintiff": 0, "defendant_sum_rub": 34_100_000},
    fssp={"active": 17, "sum_rub": 11_200_000}, marker="red",
    bankrupt_msgs=[{"date": "2026-08-12", "type": "Введение процедуры наблюдения", "case": "А43-18734/2026"}],
    marker_notes=["Процедура банкротства", "Исполнительные производства"],
    scenario="Идёт процедура банкротства", expected="rejected",
)
company(
    region="63", short="ООО «МедиаКуб»", full="Общество с ограниченной ответственностью «МедиаКуб»",
    reg="2020-10-05", capital=10_000, director="Белова Кристина Андреевна",
    founders=[("Белова Кристина Андреевна", 100)],
    ok=("73.11", ["62.02"]), address="443099, Самарская обл., г. Самара, ул. Куйбышева, д. 101, оф. 9",
    employees=9, regime="УСН (доходы)", revenue=23_500_000, margin=0.12, assets=8_000_000, equity_share=0.4,
    debt_lt=0, growth=0.22, unreliable=["address"], marker="yellow",
    marker_notes=["Сведения об адресе недостоверны (запись ФНС)"],
    scenario="Нормальные финансы, но в ЕГРЮЛ отметка о недостоверном адресе", expected="info_requested",
)

# --- ИП ---
ip(
    region="77", fio="Орлов Дмитрий Александрович", reg="2014-05-19", ok=("47.91", ["46.90"]), employees=6,
    regime="УСН (доходы)", revenue=38_000_000,
    scenario="Интернет-магазин, долгая история, без нарушений", expected="approved",
)
ip(
    region="78", fio="Никитина Елена Сергеевна", reg="2021-02-11", ok=("96.02", []), employees=5,
    regime="ПСН", revenue=7_400_000,
    scenario="Салон красоты на патенте, небольшой стабильный оборот", expected="approved",
)
ip(
    region="66", fio="Хабибуллин Тимур Маратович", reg="2022-08-01", ok=("33.12", ["25.62"]), employees=2,
    regime="УСН (доходы минус расходы)", revenue=9_800_000, arrears=212_000,
    fssp={"active": 2, "sum_rub": 268_000}, marker="yellow",
    marker_notes=["Налоговая задолженность", "Исполнительные производства"],
    scenario="Мастерская: есть недоимка и мелкие взыскания", expected="counter_offer",
)
ip(
    region="16", fio="Сафина Гульнара Ильясовна", reg="2026-06-17", ok=("56.10", []), employees=1,
    regime="АУСН", revenue=1_100_000, marker="yellow", marker_notes=["ИП зарегистрирован менее 6 месяцев назад"],
    scenario="Кофейня, ИП открыт 4 месяца назад", expected="info_requested",
)
ip(
    region="54", fio="Громов Павел Викторович", reg="2017-03-03", status="Прекратил деятельность",
    status_date="2025-12-30", ok=("68.20", []), employees=0, regime="УСН (доходы)", revenue=0, msp=None,
    marker="red", marker_notes=["Деятельность ИП прекращена"],
    scenario="ИП закрыт, кредитовать нельзя", expected="rejected",
)

# Контроль идентификаторов
for c in companies:
    i = c["egrul"]["inn"]
    assert cs([int(x) for x in i[:9]], W10) == int(i[9]), i
for e in entrepreneurs:
    i = e["egrip"]["inn"]
    d = [int(x) for x in i]
    assert cs(d[:10], W11) == d[10] and cs(d[:11], W12) == d[11], i
    o = e["egrip"]["ogrnip"]
    assert int(o[:14]) % 13 % 10 == int(o[14]), o

data = {
    "_meta": {
        "description": "Синтетические ответы внешних источников для мок-интеграций. Все компании, люди и реквизиты выдуманы; ИНН/ОГРН/ОГРНИП сгенерированы с корректными контрольными цифрами. Совпадение с реальными лицами случайно.",
        "sources": {
            "egrul": "ЕГРЮЛ ФНС — регистрационные данные юрлиц (egrul.nalog.ru)",
            "egrip": "ЕГРИП ФНС — регистрационные данные ИП (egrul.nalog.ru)",
            "fns": "ФНС «Прозрачный бизнес» — налоговый режим, численность, уплаченные налоги, недоимка, блокировки счетов, реестр МСП (pb.nalog.ru)",
            "gir_bo": "ГИР БО ФНС — бухгалтерская отчётность юрлиц, коды строк форм 0710001/0710002 (bo.nalog.ru)",
            "kontur": "Контур.Фокус — агрегированные индикаторы риска: арбитраж, ФССП, банкротства, госконтракты, залоги",
        },
        "lookup": "Поиск по ИНН: companies[].egrul.inn или entrepreneurs[].egrip.inn. ИНН, которого нет в файле, мок должен возвращать как «не найден».",
        "not_found_inn": [inn10("7799"), inn12("7799")],
        "expected_outcome_values": ["approved", "counter_offer", "info_requested", "rejected"],
        "generated_at": "2026-10-21",
    },
    "companies": companies,
    "entrepreneurs": entrepreneurs,
}

out = sys.argv[1]
with open(out, "w", encoding="utf-8", newline="\n") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
    f.write("\n")

for c in companies:
    print(c["egrul"]["inn"], c["egrul"]["name_short"], c["expected_outcome"])
for e in entrepreneurs:
    print(e["egrip"]["inn"], "ИП", e["egrip"]["fio"], e["expected_outcome"])
