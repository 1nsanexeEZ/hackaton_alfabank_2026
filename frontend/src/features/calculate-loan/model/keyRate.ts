import { shallowRef } from 'vue'

import { clientApi, type KeyRateDto } from '@/shared/api'

/**
 * Действующая ключевая ставка (GET /market/key-rate, без входа): калькулятор объясняет, от чего
 * считаются ставки продуктов. Грузим один раз за сессию страницы; не ответила — подписи просто нет.
 */
const keyRate = shallowRef<KeyRateDto | null>(null)
let requested = false

export function useKeyRate() {
  if (!requested) {
    requested = true
    clientApi
      .keyRate()
      .then((rate) => (keyRate.value = rate))
      .catch(() => (requested = false))
  }
  return keyRate
}
