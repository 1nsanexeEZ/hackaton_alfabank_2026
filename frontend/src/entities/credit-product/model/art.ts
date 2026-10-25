import unsecured from '../assets/credit-01-bez-zaloga.svg'
import secured from '../assets/credit-02-pod-zalog.svg'
import creditLine from '../assets/credit-03-kreditnaya-liniya.svg'
import overdraft from '../assets/credit-04-overdraft.svg'
import auto from '../assets/credit-05-avtokredit.svg'
import mortgage from '../assets/credit-06-biznes-ipoteka.svg'
import refinance from '../assets/credit-07-refinansirovanie.svg'
import govSupport from '../assets/credit-08-gospodderzhka.svg'
import startup from '../assets/credit-09-oborotnye-sredstva.svg'

/**
 * Иллюстрация продукта по его коду из каталога. Продукт, заведённый в админке позже, —
 * без картинки: карточка остаётся с номером и текстом, как раньше.
 */
const BY_CODE: Record<string, string> = {
  UNSECURED: unsecured,
  SECURED: secured,
  CREDIT_LINE: creditLine,
  OVERDRAFT: overdraft,
  AUTO: auto,
  MORTGAGE: mortgage,
  REFINANCE: refinance,
  GOV_SUPPORT: govSupport,
  STARTUP: startup,
}

export const productArt = (code: string): string | null => BY_CODE[code.toUpperCase()] ?? null
