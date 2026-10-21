import { DEMO_CREDIT_PRODUCTS } from '@/entities/credit-product'
import { session, shortName } from '@/entities/session'
import { configureCreditMock } from '@/shared/api'

/**
 * Мок кредитного API живёт в shared и не знает о сущностях. Здесь отдаём ему каталог продуктов
 * и текущего сотрудника — так же, как бэкенд взял бы их из своей БД и из токена.
 */
configureCreditMock({
  products: DEMO_CREDIT_PRODUCTS.map((product) => ({
    id: product.id,
    title: product.title,
    rateFrom: product.rateFrom,
    amountMin: product.amount.min,
    amountMax: product.amount.max,
    termMin: product.termMonths.min,
    termMax: product.termMonths.max,
    decisionTime: product.decisionTime,
  })),
  actor: () => shortName(session.state.me),
  can: session.can,
})
