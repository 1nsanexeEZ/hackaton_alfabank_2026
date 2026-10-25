"""The print form of the loan contract, drawn with fpdf2.

Pure Python: no system libraries, the same PDF on Windows, in CI and in the
container. Fonts (PT Sans, PT Mono, OFL) are embedded. Layout follows
docs/design/contract-mockup.html: the deal UID and its QR code on the first
page (Bank of Russia letter on 218-FZ), the terms table, general terms,
requisites with the signature stamps (GOST R 7.0.97-2016 p. 5.23), the payment
schedule and the signing log.
"""

import logging
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import qrcode
from fpdf import FPDF, XPos, YPos
from fpdf.fonts import FontFace
from qrcode.constants import ERROR_CORRECT_M

from src.modules.applications.application.dto.contract_documents import (
    BankSealDTO,
    ClientSignatureDTO,
    ContractPrintDTO,
)
from src.modules.applications.application.interfaces.contracts import ContractRenderer
from src.modules.applications.infrastructure.contract_pdf.money import money, rubles_in_words

FONTS = Path(__file__).parent / "fonts"
# fontTools tells about every font subset at INFO; that is noise in the logs.
logging.getLogger("fontTools").setLevel(logging.WARNING)
MSK = timezone(timedelta(hours=3), "МСК")
MONTHS = (
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
)
PURPOSES = {
    "working_capital": "пополнение оборотных средств",
    "cash_gap": "покрытие кассового разрыва",
    "equipment": "покупка оборудования",
    "vehicles": "покупка транспорта",
    "real_estate": "покупка коммерческой недвижимости",
    "contract_execution": "исполнение контракта",
    "refinancing": "рефинансирование",
    "expansion": "развитие бизнеса",
}
REPAYMENTS = {
    "annuity": "равными (аннуитетными) платежами",
    "differentiated": "дифференцированными платежами",
    "interest_only": "ежемесячно процентами, основной долг — в конце срока",
    "by_contract_schedule": "по графику",
}
# The bank's requisites from open sources (the case is the bank's own).
BANK_NAME = "Акционерное общество «Альфа-Банк»"
BANK_LINE = (
    "ИНН 7728168971 · ОГРН 1027700067328 · Генеральная лицензия Банка России № 1326\n"
    "107078, г. Москва, ул. Каланчёвская, д. 27"
)
BANK_REQUISITES = (
    "АО «Альфа-Банк»\nИНН 7728168971 · КПП 770801001 · ОГРН 1027700067328\n"
    "БИК 044525593 · к/с 30101810200000000593 в ГУ Банка России по ЦФО\n"
    "107078, г. Москва, ул. Каланчёвская, д. 27"
)
DEMO = "Демо-стенд «Альфа Хак 2026»"

INK = (17, 20, 24)
INK_2 = (74, 81, 96)
INK_3 = (123, 130, 145)
LINE = (217, 221, 228)
ALFA = (239, 49, 36)
SIG = (31, 78, 140)
SIG_BG = (244, 248, 253)
SIG_TEXT = (15, 39, 71)
WATERMARK = (241, 242, 244)

LEFT = 16.0
WIDTH = 178.0


def _entrepreneur(legal_form: str) -> bool:
    return str(legal_form) == "IE"


def _msk(moment: datetime) -> datetime:
    aware = moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment
    return aware.astimezone(MSK)


def _long_date(day: date) -> str:
    return f"«{day.day}» {MONTHS[day.month - 1]} {day.year} г."


def _add_months(day: date, months: int) -> date:
    month = day.month - 1 + months
    year, month = day.year + month // 12, month % 12 + 1
    last = (date(year + (month == 12), month % 12 + 1, 1) - timedelta(days=1)).day
    return date(year, month, min(day.day, last))


def _rate(rate: Decimal) -> str:
    return f"{rate.normalize():f}".replace(".", ",")


def _term(months: int) -> str:
    if months % 100 in range(11, 15):
        word = "месяцев"
    else:
        word = {1: "месяц", 2: "месяца", 3: "месяца", 4: "месяца"}.get(months % 10, "месяцев")
    return f"{months} {word}"


class _Pdf(FPDF):
    def __init__(self, document: ContractPrintDTO) -> None:
        super().__init__(orientation="P", unit="mm", format="A4")
        self.document = document
        self.add_font("PTSans", "", FONTS / "PTSans-Regular.ttf")
        self.add_font("PTSans", "B", FONTS / "PTSans-Bold.ttf")
        self.add_font("PTMono", "", FONTS / "PTMono-Regular.ttf")
        self.set_margins(LEFT, 16, LEFT)
        self.set_auto_page_break(auto=True, margin=22)
        self.set_lang("ru")
        self.set_title(f"Кредитный договор № {document.contract.number}")
        self.set_author(BANK_NAME)
        self.set_subject(f"УИд {document.uid}")
        self.set_creator("Кредитный кабинет")

    def header(self) -> None:
        mark = "ПРОЕКТ" if self.document.kind == "draft" else "ОБРАЗЕЦ"
        self.set_font("PTSans", "B", 88)
        self.set_text_color(*WATERMARK)
        with self.rotation(32, x=105, y=160):
            width = self.get_string_width(mark)
            self.text(105 - width / 2, 175, mark)
        self.set_xy(LEFT, 16)

    def footer(self) -> None:
        self.set_y(-15)
        self.set_draw_color(*LINE)
        self.line(LEFT, self.get_y() - 1.5, LEFT + WIDTH, self.get_y() - 1.5)
        self.set_font("PTSans", "", 7)
        self.set_text_color(*INK_3)
        number = self.document.contract.number
        self.cell(WIDTH / 2, 4, f"Кредитный договор № {number} · УИд {self.document.uid}")
        self.cell(WIDTH / 2, 4, f"{DEMO} · стр. {self.page_no()} из {{nb}}", align="R")

    # --- building blocks -------------------------------------------------

    def font(self, size: float, bold: bool = False, mono: bool = False) -> None:
        self.set_font("PTMono" if mono else "PTSans", "B" if bold and not mono else "", size)

    def paragraph(self, text: str, size: float = 9, height: float = 4.4) -> None:
        self.font(size)
        self.set_text_color(*INK)
        self.multi_cell(0, height, text, align="J", markdown=True)
        self.ln(1.2)

    def heading(self, text: str) -> None:
        if self.get_y() > 255:
            self.add_page()
        self.ln(2)
        self.font(10.5, bold=True)
        self.set_text_color(*INK)
        self.cell(0, 6, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(0.8)

    def clause(self, number: str, title: str, text: str) -> None:
        self.font(9)
        self.set_text_color(*INK)
        self.multi_cell(0, 4.3, f"**{number} {title}** {text}", align="J", markdown=True)
        self.ln(1)

    def logo(self, x: float, y: float, size: float) -> None:
        self.set_fill_color(*ALFA)
        self.rect(x, y, size, size, style="F", round_corners=True, corner_radius=size * 0.22)
        self.set_text_color(255, 255, 255)
        self.font(size * 2.1, bold=True)
        width = self.get_string_width("А")
        self.text(x + (size - width) / 2, y + size * 0.7, "А")
        self.set_fill_color(255, 255, 255)
        self.rect(x + size * 0.3, y + size * 0.78, size * 0.4, size * 0.07, style="F")

    def qr(self, text: str, x: float, y: float, size: float) -> None:
        code = qrcode.QRCode(error_correction=ERROR_CORRECT_M, border=0)
        code.add_data(text)
        code.make(fit=True)
        matrix = code.get_matrix()
        cell = size / len(matrix)
        self.set_fill_color(*INK)
        for row, line in enumerate(matrix):
            for column, dark in enumerate(line):
                if dark:
                    self.rect(x + column * cell, y + row * cell, cell + 0.01, cell + 0.01, "F")

    def box_text(
        self, x: float, y: float, width: float, lines: list[tuple[str, float, bool, bool]]
    ) -> float:
        """Lines (text, size, bold, mono) from (x, y) in a column; returns the y below."""
        self.set_xy(x, y)
        for text, size, bold, mono in lines:
            self.font(size, bold=bold, mono=mono)
            self.set_x(x)
            self.multi_cell(
                width, size * 0.48, text, align="L", new_x=XPos.LMARGIN, new_y=YPos.NEXT
            )
        return self.get_y()

    def table_start(self) -> None:
        """A table takes the current fill color for its cells unless it is the default one."""
        self.set_fill_color(0)
        self.set_draw_color(*LINE)


class FpdfContractRenderer(ContractRenderer):
    def render(self, document: ContractPrintDTO) -> bytes:
        pdf = _Pdf(document)
        pdf.add_page()
        self._first_page(pdf, document)
        pdf.add_page()
        self._general_terms(pdf, document)
        pdf.add_page()
        self._parties(pdf, document)
        pdf.add_page()
        self._schedule(pdf, document)
        self._log(pdf, document)
        return bytes(pdf.output())

    # --- page 1 ------------------------------------------------------------

    def _first_page(self, pdf: _Pdf, document: ContractPrintDTO) -> None:
        contract, terms = document.contract, document.contract.terms
        pdf.logo(LEFT, 16, 10)
        pdf.set_text_color(*INK)
        pdf.set_xy(LEFT + 13, 15.6)
        pdf.font(13, bold=True)
        pdf.cell(80, 6, "АЛЬФА-БАНК")
        pdf.set_text_color(*INK_2)
        pdf.box_text(LEFT + 13, 22, 88, [(f"{BANK_NAME}\n{BANK_LINE}", 6.6, False, False)])

        # deal UID: one line of the contract font size and a QR code (Bank of Russia letter)
        box_x, box_y, box_w, box_h = 120.0, 15.0, 74.0, 27.0
        pdf.set_draw_color(*INK)
        pdf.set_line_width(0.3)
        pdf.rect(box_x, box_y, box_w, box_h)
        pdf.qr(document.uid, box_x + 2.5, box_y + 2.5, 22)
        pdf.set_text_color(*INK)
        pdf.box_text(
            box_x + 26.5,
            box_y + 2.4,
            box_w - 28.5,
            [
                ("УИд договора (сделки)", 7, True, False),
                (document.uid, 6.6, False, True),
                ("QR-код содержит УИд договора (сделки), 218-ФЗ", 6.2, False, False),
            ],
        )

        pdf.set_y(47)
        if document.kind == "draft":
            expires = _msk(terms.expires_at)
            pdf.set_fill_color(255, 247, 224)
            pdf.set_draw_color(234, 196, 106)
            pdf.font(8.4)
            pdf.set_text_color(*INK)
            pdf.multi_cell(
                0,
                4.2,
                "**Проект договора.** Не является заключённым договором до подписания обеими "
                "сторонами. Предложение Банка действует до "
                f"{expires:%d.%m.%Y %H:%M} МСК (ст. 435, 440 ГК РФ).",
                border=1,
                fill=True,
                markdown=True,
                padding=2,
                new_x=XPos.LMARGIN,
                new_y=YPos.NEXT,
            )
            pdf.ln(2)

        pdf.font(15, bold=True)
        pdf.set_text_color(*INK)
        pdf.cell(
            0,
            8,
            f"КРЕДИТНЫЙ ДОГОВОР № {contract.number}",
            align="C",
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )
        pdf.font(9)
        pdf.set_text_color(*INK_2)
        who = (
            "индивидуального предпринимателя"
            if _entrepreneur(contract.borrower.legal_form)
            else "юридического лица"
        )
        pdf.cell(
            0,
            5,
            f"Индивидуальные условия кредитования {who}",
            align="C",
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )
        pdf.ln(2)
        pdf.set_text_color(*INK)
        signed = document.client_signature
        day = _msk(signed.signed_at).date() if signed else None
        pdf.cell(WIDTH / 2, 5, "г. Москва")
        pdf.cell(
            WIDTH / 2,
            5,
            _long_date(day) if day else "дата — день подписания сторонами",
            align="R",
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )
        pdf.ln(2)
        pdf.paragraph(self._preamble(document))

        pdf.heading("1. Индивидуальные условия")
        schedule = contract.schedule
        base = day or _msk(document.issued_at).date()
        purpose = PURPOSES.get(document.purpose or "", document.purpose or "не указана")
        rows = [
            ("Сумма кредита", f"{money(terms.amount)} ₽ ({rubles_in_words(terms.amount)})", True),
            (
                "Срок кредита",
                f"{_term(terms.term_months)}, окончательное погашение — "
                f"{_add_months(base, terms.term_months):%d.%m.%Y}",
                True,
            ),
            (
                "Процентная ставка",
                f"{_rate(terms.rate)} % годовых, фиксированная на весь срок",
                True,
            ),
            ("Продукт и цель", f"«{document.product_name}»; {purpose}", False),
            (
                "Порядок предоставления",
                "Единовременно, на расчётный счёт Заёмщика в Банке, не позднее 3 рабочих дней "
                "с даты подписания договора обеими сторонами",
                False,
            ),
            (
                "Порядок погашения",
                f"Ежемесячно, {REPAYMENTS.get(schedule.repayment, schedule.repayment)}; первый "
                f"платёж {money(schedule.monthly_payment)} ₽; график — Приложение № 1",
                False,
            ),
            (
                "Проценты за весь срок",
                f"{money(schedule.total_interest)} ₽; всего к возврату "
                f"{money(schedule.total_paid)} ₽ при погашении по графику",
                False,
            ),
            (
                "Обеспечение",
                "Без обеспечения" if not terms.conditions else "; ".join(terms.conditions),
                False,
            ),
            (
                "Досрочное погашение",
                "Полное или частичное, без комиссии, по заявлению в Кредитном кабинете не позднее "
                "чем за 5 рабочих дней",
                False,
            ),
            (
                "Неустойка",
                "0,1 % от суммы просроченного платежа за каждый день просрочки (ст. 330 ГК РФ)",
                False,
            ),
            ("Комиссии", "Не взимаются", False),
            (
                "Срок действия предложения",
                f"до {_msk(terms.expires_at):%d.%m.%Y %H:%M} МСК; "
                "после — нужно новое решение Банка",
                False,
            ),
            (
                "Основание",
                f"Решение Банка № {str(terms.decision_id)[:8]}; отпечаток условий SHA-256: "
                f"{contract.offer_hash[:16]}…{contract.offer_hash[-8:]}",
                False,
            ),
        ]
        pdf.font(8.6)
        pdf.table_start()
        with pdf.table(
            col_widths=(8, 50, 120),
            text_align=("CENTER", "LEFT", "LEFT"),
            line_height=4.3,
            first_row_as_headings=False,
            padding=(1.2, 1.6),
            borders_layout="ALL",
        ) as table:
            for index, (name, value, key) in enumerate(rows, start=1):
                row = table.row()
                row.cell(str(index), style=FontFace(color=INK_3))
                row.cell(name, style=FontFace(color=INK_2))
                row.cell(value, style=FontFace(emphasis="BOLD" if key else None, color=INK))
        pdf.ln(2)
        pdf.font(7.8)
        pdf.set_text_color(*INK_2)
        pdf.multi_cell(
            0,
            3.8,
            "Условия, не указанные в таблице, определены разделами 2 и 3. Подписывая договор, "
            "Заёмщик подтверждает, что получил его текст до подписания в электронном виде.",
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )

    def _preamble(self, document: ContractPrintDTO) -> str:
        borrower = document.contract.borrower
        ogrn = "ОГРНИП" if _entrepreneur(borrower.legal_form) else "ОГРН"
        requisites = f"ИНН {borrower.inn}, {ogrn} {borrower.ogrn}"
        if borrower.kpp:
            requisites += f", КПП {borrower.kpp}"
        if _entrepreneur(borrower.legal_form):
            party = (
                f"**{borrower.name}** ({requisites}, далее — «Заёмщик»), "
                "действующий от своего имени"
            )
        else:
            head = borrower.head_name or "уполномоченного лица"
            party = (
                f"**{borrower.name}** ({requisites}, далее — «Заёмщик») в лице генерального "
                f"директора **{head}**, действующего на основании Устава (полномочия подтверждены "
                "сведениями ЕГРЮЛ)"
            )
        return (
            f"**{BANK_NAME}** (далее — «Банк») в лице уполномоченного лица, подписывающего "
            f"договор электронной подписью Банка, с одной стороны, и {party}, с другой стороны, "
            "заключили настоящий договор о нижеследующем."
        )

    # --- page 2 ------------------------------------------------------------

    def _general_terms(self, pdf: _Pdf, document: ContractPrintDTO) -> None:
        pdf.heading("2. Общие условия")
        for number, title, text in GENERAL_TERMS:
            pdf.clause(number, title, text)
        pdf.heading("3. Электронное взаимодействие и подписание")
        for number, title, text in SIGNING_TERMS:
            pdf.clause(number, title, text)

    # --- page 3 ------------------------------------------------------------

    def _parties(self, pdf: _Pdf, document: ContractPrintDTO) -> None:
        pdf.heading("4. Реквизиты и подписи сторон")
        borrower = document.contract.borrower
        top = pdf.get_y() + 1
        column = (WIDTH - 8) / 2
        right = LEFT + column + 8
        pdf.set_text_color(*INK)
        pdf.box_text(LEFT, top, column, [("Банк", 9.5, True, False)])
        pdf.box_text(right, top, column, [("Заёмщик", 9.5, True, False)])
        pdf.set_text_color(*INK_2)
        requisites = f"{borrower.name}\nИНН {borrower.inn}"
        if borrower.kpp:
            requisites += f" · КПП {borrower.kpp}"
        requisites += f" · ОГРН{'ИП' if _entrepreneur(borrower.legal_form) else ''} {borrower.ogrn}"
        requisites += "\nРасчётный счёт в АО «Альфа-Банк»"
        pdf.box_text(LEFT, top + 6, column, [(BANK_REQUISITES, 7.6, False, False)])
        pdf.box_text(right, top + 6, column, [(requisites, 7.6, False, False)])

        stamp_y = top + 28
        if document.bank_seal is not None:
            self._bank_stamp(pdf, LEFT, stamp_y, column, document.bank_seal)
        else:
            self._placeholder(
                pdf,
                LEFT,
                stamp_y,
                column,
                "Место для электронной подписи Банка",
                "Проставляется автоматически сразу после подписи Заёмщика",
            )
        if document.client_signature is not None:
            self._client_stamp(pdf, right, stamp_y, column, document.client_signature)
        else:
            head = borrower.head_name or "уполномоченное лицо"
            self._placeholder(
                pdf,
                right,
                stamp_y,
                column,
                "Место для простой электронной подписи Заёмщика",
                f"{head} — пароль и подтверждение в Кредитном кабинете",
            )

        # check page of the document
        box_y = stamp_y + 42
        pdf.set_draw_color(*LINE)
        pdf.rect(LEFT, box_y, WIDTH, 30, round_corners=True, corner_radius=1.5)
        pdf.qr(document.verify_url, LEFT + 3, box_y + 3, 24)
        pdf.set_text_color(*INK)
        pdf.box_text(
            LEFT + 31,
            box_y + 4,
            WIDTH - 35,
            [
                ("Проверить подлинность договора", 9, True, False),
                (
                    "Отсканируйте код или откройте ссылку: сервис покажет, кем и когда подписан "
                    "документ, и сверит загруженный файл с экземпляром в архиве Банка.",
                    7.8,
                    False,
                    False,
                ),
                (document.verify_url, 7.2, False, True),
                (f"Идентификатор документа: {document.document_id}", 7.2, False, True),
            ],
        )
        pdf.set_y(box_y + 34)
        pdf.font(7.6)
        pdf.set_text_color(*INK_2)
        note = (
            "Отметки об электронной подписи — по п. 5.23 ГОСТ Р 7.0.97-2016. Подпись Банка "
            "встроена в файл (PAdES) и видна в панели подписей программы просмотра PDF. "
            f"{DEMO}: ключ Банка выпущен демо-удостоверяющим центром стенда и не является "
            "квалифицированным."
            if document.kind == "signed"
            else "Это проект: подписей ещё нет. После подписи Заёмщика Банк сформирует итоговый "
            "экземпляр с отметками об электронных подписях и листом подписания."
        )
        pdf.multi_cell(0, 3.8, note, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def _placeholder(
        self, pdf: _Pdf, x: float, y: float, width: float, title: str, hint: str
    ) -> None:
        pdf.set_draw_color(*INK_3)
        pdf.set_dash_pattern(dash=1.2, gap=1)
        pdf.rect(x, y, width, 36, round_corners=True, corner_radius=1.5)
        pdf.set_dash_pattern()
        pdf.set_text_color(*INK_2)
        pdf.box_text(x + 4, y + 12, width - 8, [(title, 8.4, True, False)])
        pdf.set_text_color(*INK_3)
        pdf.box_text(x + 4, pdf.get_y() + 0.6, width - 8, [(hint, 7.6, False, False)])

    def _stamp_frame(self, pdf: _Pdf, x: float, y: float, width: float, title: str) -> float:
        pdf.set_draw_color(*SIG)
        pdf.set_fill_color(*SIG_BG)
        pdf.set_line_width(0.45)
        pdf.rect(x, y, width, 36, style="DF", round_corners=True, corner_radius=1.5)
        pdf.set_line_width(0.2)
        pdf.set_text_color(*SIG_TEXT)
        pdf.box_text(x + 10, y + 2.2, width - 12, [(title, 6.6, True, False)])
        pdf.set_draw_color(170, 190, 215)
        pdf.line(x + 2.5, y + 9.4, x + width - 2.5, y + 9.4)
        return y + 10.6

    def _rows(
        self, pdf: _Pdf, x: float, y: float, width: float, rows: list[tuple[str, str, bool]]
    ) -> None:
        for label, value, mono in rows:
            pdf.set_xy(x + 2.5, y)
            pdf.font(6.8)
            pdf.set_text_color(59, 91, 134)
            pdf.cell(19, 3.6, label)
            pdf.set_text_color(*SIG_TEXT)
            pdf.font(6.6 if mono else 6.9, bold=not mono, mono=mono)
            pdf.set_xy(x + 22, y)
            pdf.multi_cell(width - 24.5, 3.6, value, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            y = pdf.get_y() + 0.3

    def _bank_stamp(self, pdf: _Pdf, x: float, y: float, width: float, seal: BankSealDTO) -> None:
        body = self._stamp_frame(
            pdf, x, y, width, "ДОКУМЕНТ ПОДПИСАН УСИЛЕННОЙ ЭЛЕКТРОННОЙ ПОДПИСЬЮ"
        )
        pdf.logo(x + 2.5, y + 2, 5.6)
        cert = seal.certificate
        self._rows(
            pdf,
            x,
            body,
            width,
            [
                ("Владелец", f"{cert.subject}, автоматическое подписание", False),
                ("Сертификат", cert.serial, True),
                (
                    "Действителен",
                    f"с {_msk(cert.valid_from):%d.%m.%Y} по {_msk(cert.valid_to):%d.%m.%Y}",
                    False,
                ),
                (
                    "Подписано",
                    f"{_msk(seal.signed_at):%d.%m.%Y %H:%M:%S} МСК, метка времени",
                    False,
                ),
                ("Издатель", cert.issuer, False),
            ],
        )

    def _client_stamp(
        self, pdf: _Pdf, x: float, y: float, width: float, client: ClientSignatureDTO
    ) -> None:
        body = self._stamp_frame(pdf, x, y, width, "ПОДПИСАНО ПРОСТОЙ ЭЛЕКТРОННОЙ ПОДПИСЬЮ")
        pdf.set_fill_color(*SIG)
        pdf.ellipse(x + 2.6, y + 2.2, 5.4, 5.4, style="F")
        pdf.set_draw_color(255, 255, 255)
        pdf.set_line_width(0.5)
        pdf.line(x + 3.8, y + 5.0, x + 5.0, y + 6.2)
        pdf.line(x + 5.0, y + 6.2, x + 7.0, y + 3.8)
        pdf.set_line_width(0.2)
        authority = "по ЕГРЮЛ" if client.authority == "registry" else "по доверенности"
        signed = f"{_msk(client.signed_at):%d.%m.%Y %H:%M:%S} МСК"
        if client.ip:
            signed += f" · IP {client.ip}"
        document_hash = client.document_hash
        self._rows(
            pdf,
            x,
            body,
            width,
            [
                ("Подписант", f"{client.signer}, {client.role}", False),
                ("Полномочие", authority, False),
                ("Способ", "пароль и подтверждение в Кредитном кабинете", False),
                ("Подписано", signed, False),
                (
                    "Проект",
                    f"{document_hash[:20]}…" if document_hash else "по отпечатку условий",
                    bool(document_hash),
                ),
            ],
        )

    # --- page 4 ------------------------------------------------------------

    def _schedule(self, pdf: _Pdf, document: ContractPrintDTO) -> None:
        contract, schedule = document.contract, document.contract.schedule
        pdf.heading("Приложение № 1. График платежей")
        signed = document.client_signature
        base = _msk(signed.signed_at).date() if signed else _msk(document.issued_at).date()
        pdf.font(8)
        pdf.set_text_color(*INK_2)
        pdf.cell(
            0,
            4,
            f"к кредитному договору № {contract.number} · {money(schedule.amount)} ₽ · "
            f"{_term(schedule.term_months)} · {_rate(schedule.rate)} % годовых",
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )
        pdf.ln(1.5)
        pdf.font(7.6)
        pdf.set_text_color(*INK)
        pdf.table_start()
        with pdf.table(
            col_widths=(8, 24, 36, 34, 36, 40),
            text_align=("LEFT", "LEFT", "RIGHT", "RIGHT", "RIGHT", "RIGHT"),
            line_height=3.7,
            padding=(0.6, 1.2),
            borders_layout="HORIZONTAL_LINES",
            headings_style=FontFace(emphasis="BOLD", color=INK_2),
        ) as table:
            heading = table.row()
            for title in (
                "№",
                "Дата",
                "Основной долг, ₽",
                "Проценты, ₽",
                "Платёж, ₽",
                "Остаток, ₽",
            ):
                heading.cell(title)
            for payment in schedule.payments:
                due = payment.due_date or _add_months(base, payment.number)
                row = table.row()
                row.cell(str(payment.number))
                row.cell(f"{due:%d.%m.%Y}")
                row.cell(money(payment.principal))
                row.cell(money(payment.interest))
                row.cell(money(payment.total))
                row.cell(money(payment.balance_after))
            total = table.row()
            bold = FontFace(emphasis="BOLD")
            total.cell("Итого", colspan=2, style=bold)
            total.cell(money(schedule.amount), style=bold)
            total.cell(money(schedule.total_interest), style=bold)
            total.cell(money(schedule.total_paid), style=bold)
            total.cell("")

    def _log(self, pdf: _Pdf, document: ContractPrintDTO) -> None:
        pdf.heading("Лист подписания")
        pdf.font(7.6)
        pdf.table_start()
        with pdf.table(
            col_widths=(30, 98, 50),
            text_align="LEFT",
            line_height=3.7,
            padding=(0.8, 1.2),
            borders_layout="HORIZONTAL_LINES",
            headings_style=FontFace(emphasis="BOLD", color=INK_2),
        ) as table:
            heading = table.row()
            for title in ("Дата и время, МСК", "Событие", "Кто"):
                heading.cell(title)
            for event in document.events:
                row = table.row()
                row.cell(f"{_msk(event.at):%d.%m.%Y %H:%M:%S}")
                text = event.text + (f" · звено {event.hash[:12]}" if event.hash else "")
                row.cell(text)
                row.cell(event.actor)
            if document.kind == "draft":
                row = table.row()
                row.cell("—")
                row.cell("Ожидает подписи Заёмщика, затем Банка")
                row.cell("")
        pdf.ln(1.5)
        pdf.font(7.2)
        pdf.set_text_color(*INK_3)
        pdf.multi_cell(
            0,
            3.6,
            "Каждое звено журнала содержит хеш предыдущего: запись нельзя изменить или удалить "
            "незаметно. Журнал хранится в системе Банка и показывается на странице проверки.",
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )


GENERAL_TERMS: tuple[tuple[str, str, str], ...] = (
    (
        "2.1.",
        "Предмет.",
        "Банк предоставляет Заёмщику денежные средства (кредит) в размере и на условиях договора, "
        "а Заёмщик возвращает кредит и уплачивает проценты на него (ст. 819 ГК РФ).",
    ),
    (
        "2.2.",
        "Проценты",
        "начисляются на остаток основного долга со дня, следующего за днём выдачи, по день "
        "погашения включительно, исходя из фактического числа дней в году (ст. 809 ГК РФ). "
        "Ставка не меняется Банком в одностороннем порядке.",
    ),
    (
        "2.3.",
        "Погашение.",
        "Платежи списываются Банком с расчётного счёта Заёмщика в даты графика без "
        "дополнительного распоряжения (заранее данный акцепт). Поступившие средства направляются "
        "сначала на проценты, затем на основной долг, затем на неустойку.",
    ),
    (
        "2.4.",
        "Обязанности Заёмщика:",
        "использовать кредит по цели; не реже раза в квартал предоставлять бухгалтерскую "
        "отчётность через Кредитный кабинет; в течение 5 рабочих дней сообщать о смене "
        "руководителя, реорганизации, начале ликвидации или банкротства, о новых кредитах "
        "и поручительствах свыше 10 % выручки.",
    ),
    (
        "2.5.",
        "Досрочное истребование.",
        "Банк вправе потребовать досрочного возврата кредита и процентов при просрочке платежа "
        "более 30 дней, нецелевом использовании, недостоверных сведениях, начале ликвидации или "
        "банкротства Заёмщика (ст. 811, 814 ГК РФ).",
    ),
    (
        "2.6.",
        "Ответственность.",
        "За нарушение сроков платежей Заёмщик уплачивает неустойку по п. 10 таблицы. Стороны "
        "несут имущественную ответственность за неисполнение договора по законодательству РФ "
        "(ст. 30 Федерального закона № 395-1 «О банках и банковской деятельности»).",
    ),
    (
        "2.7.",
        "Кредитная история.",
        "Банк передаёт сведения об обязательствах Заёмщика в бюро кредитных историй "
        "(Федеральный закон № 218-ФЗ). Договору присвоен уникальный идентификатор, указанный на "
        "первой странице.",
    ),
    (
        "2.8.",
        "Персональные данные.",
        "Сведения о представителях Заёмщика Банк обрабатывает на основании согласий, данных "
        "в Кредитном кабинете до подачи заявки (Федеральный закон № 152-ФЗ), и для исполнения "
        "договора; проверки по Федеральному закону № 115-ФЗ проведены до заключения договора.",
    ),
)

SIGNING_TERMS: tuple[tuple[str, str, str], ...] = (
    (
        "3.1.",
        "Форма.",
        "Договор составлен в форме одного электронного документа и подписывается электронными "
        "подписями сторон; простая письменная форма соблюдена (ст. 160, п. 2 ст. 434, "
        "ст. 820 ГК РФ).",
    ),
    (
        "3.2.",
        "Подпись Заёмщика.",
        "Заёмщик подписывает договор простой электронной подписью в Кредитном кабинете: "
        "повторный ввод пароля учётной записи уполномоченного лица и подтверждение документа, "
        "SHA-256 которого фиксируется в листе подписания, по Правилам электронного "
        "взаимодействия, принятым при подписании (ч. 2 ст. 6, ст. 9 Федерального закона "
        "№ 63-ФЗ). Подписант определяется по учётной записи и её полномочию в компании "
        "(ЕГРЮЛ или доверенность); пароль хранится в тайне.",
    ),
    (
        "3.3.",
        "Подпись Банка.",
        "Банк подписывает договор усиленной электронной подписью, созданной автоматически после "
        "подписи Заёмщика. Подпись встроена в файл (PAdES), содержит метку времени и позволяет "
        "обнаружить любое изменение документа после подписания (ч. 3 ст. 5 Федерального закона "
        "№ 63-ФЗ).",
    ),
    (
        "3.4.",
        "Равнозначность.",
        "Стороны признают договор, подписанный указанными подписями, равнозначным документу на "
        "бумажном носителе, подписанному собственноручно и заверенному печатью (ч. 2, 3 ст. 6 "
        "Федерального закона № 63-ФЗ).",
    ),
    (
        "3.5.",
        "Проверка.",
        "Подлинность проверяется на странице проверки по QR-коду раздела 4: сервис сверяет "
        "подпись Банка, хеш файла и сведения о подписи Заёмщика с записью в системе Банка.",
    ),
    (
        "3.6.",
        "Срок действия и расторжение.",
        "Договор вступает в силу с момента подписания обеими сторонами и действует до полного "
        "исполнения обязательств. Расторжение — по соглашению сторон или по основаниям п. 2.5; "
        "Заёмщик вправе расторгнуть договор, полностью погасив задолженность.",
    ),
    (
        "3.7.",
        "Споры",
        "рассматриваются в Арбитражном суде г. Москвы после претензионного порядка "
        "(30 календарных дней).",
    ),
)
