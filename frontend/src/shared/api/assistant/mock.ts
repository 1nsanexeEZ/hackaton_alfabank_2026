import { calcAnnuityPayment, formatMoney } from '../../lib'
import {
  AssistantError,
  type AskHandlers,
  type AskInput,
  type AssistantAnswerDto,
  type AssistantApi,
  type AssistantApplicationDto,
  type AssistantHistoryMessageDto,
  type AssistantIntent,
  type AssistantMode,
  type AssistantStatusDto,
} from './types'

/**
 * Помощник на моках: работает без сервиса, чтобы окно можно было показать в демо.
 * Ответы — шаблоны на типовые вопросы; в режиме `rules` они короче, как у настоящего сервиса.
 * Состояние ИИ переключается из окна (только в dev): работает / по шаблонам / недоступен.
 */
export type MockAssistantState = 'llm' | 'rules' | 'off'

let state: MockAssistantState = 'llm'

export function setMockAssistantState(next: MockAssistantState): void {
  state = next
}

export function mockAssistantState(): MockAssistantState {
  return state
}

const APPLICATIONS: AssistantApplicationDto[] = [
  { id: 'mock-app-142', number: '2026-000142', product_code: 'equipment', status: 'rejected', client_stage: 'Заявка отклонена' },
  { id: 'mock-app-214', number: '2026-000214', product_code: 'working_capital', status: 'offer_ready', client_stage: 'Предложение готово' },
  { id: 'mock-app-187', number: '2026-000187', product_code: 'overdraft', status: 'in_review', client_stage: 'Проверяем данные' },
]

const PRODUCT_TITLE: Record<string, string> = {
  equipment: 'кредит на оборудование',
  working_capital: 'кредит на оборотные средства',
  overdraft: 'овердрафт',
}

interface Reply {
  intent: AssistantIntent
  /** Развёрнутый ответ модели и короткий шаблонный */
  full: string
  short: string
  applicationId: string | null
}

const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms))

function unavailable(): AssistantError {
  return new AssistantError('unavailable', 'Помощник временно недоступен')
}

function latest(): AssistantApplicationDto {
  return [...APPLICATIONS].sort((a, b) => b.number.localeCompare(a.number))[0]!
}

function pickApplication(id: string | null): AssistantApplicationDto {
  return APPLICATIONS.find((item) => item.id === id) ?? latest()
}

function decisionReply(app: AssistantApplicationDto): Reply {
  const title = PRODUCT_TITLE[app.product_code] ?? 'кредит'
  const base = { intent: 'decision' as const, applicationId: app.id }
  if (app.status === 'offer_ready') {
    return {
      ...base,
      full: `По заявке № ${app.number} (${title}) банк принял положительное решение: одобрено ${formatMoney(1_500_000)} на 24 месяца по ставке 17,9% годовых. Условия сверены с данными банка. Предложение действует 7 дней: откройте заявку, проверьте условия и примите их, после этого можно подписать договор.`,
      short: `По заявке № ${app.number} кредит одобрен: ${formatMoney(1_500_000)} на 24 месяца, ставка 17,9%. Откройте заявку, чтобы принять предложение.`,
    }
  }
  if (app.status === 'rejected') {
    return {
      ...base,
      full: `По заявке № ${app.number} (${title}) банк не смог одобрить кредит. Основная причина — выручка за последние месяцы ниже, чем нужно для запрошенной суммы. Это не окончательный вердикт: уменьшите сумму или увеличьте срок и подайте заявку заново — платёж станет меньше, и шансов на одобрение больше.`,
      short: `По заявке № ${app.number} банк отказал: выручки не хватает для запрошенной суммы. Попробуйте подать заявку на меньшую сумму.`,
    }
  }
  return {
    ...base,
    full: `По заявке № ${app.number} (${title}) решения пока нет: банк проверяет данные компании. Обычно это занимает до одного рабочего дня. Как только решение появится, вы получите уведомление в кабинете.`,
    short: `По заявке № ${app.number} решения пока нет, банк проверяет данные. Мы сообщим, как только оно появится.`,
  }
}

function statusReply(app: AssistantApplicationDto): Reply {
  const stage = app.client_stage ?? 'в обработке'
  return {
    intent: 'status',
    applicationId: app.id,
    full: `Заявка № ${app.number} сейчас на этапе «${stage}». Следующий шаг — ${
      app.status === 'offer_ready' ? 'принять предложение и подписать договор' : app.status === 'rejected' ? 'подать новую заявку с другими условиями' : 'решение банка, мы пришлём уведомление'
    }. Полный ход рассмотрения и документы — в карточке заявки.`,
    short: `Заявка № ${app.number}: этап «${stage}».`,
  }
}

function productsReply(): Reply {
  return {
    intent: 'products',
    applicationId: null,
    full: 'Для малого бизнеса сейчас подойдут три продукта. «Оборотный кредит» — до 5 млн ₽ на срок до 24 месяцев, если нужно пополнить оборот. «Овердрафт» — лимит на счёте до 1 млн ₽, платите только за использованные дни. «Кредит на оборудование» — до 10 млн ₽ на срок до 60 месяцев. Какой подходит именно вам, покажет подбор в калькуляторе: он учитывает вашу компанию и предодобрение.',
    short: 'Подойдут оборотный кредит, овердрафт и кредит на оборудование. Подбор под вашу компанию — в калькуляторе на главной.',
  }
}

function parseAmount(text: string): number | null {
  const million = /(\d+(?:[.,]\d+)?)\s*(?:млн|миллион)/i.exec(text)
  if (million) return Math.round(Number.parseFloat(million[1]!.replace(',', '.')) * 1_000_000)
  const thousand = /(\d+(?:[.,]\d+)?)\s*(?:тыс|к\b)/i.exec(text)
  if (thousand) return Math.round(Number.parseFloat(thousand[1]!.replace(',', '.')) * 1_000)
  const plain = /(\d[\d\s]{4,})/.exec(text)
  return plain ? Number.parseInt(plain[1]!.replace(/\s/g, ''), 10) : null
}

function parseMonths(text: string): number | null {
  const years = /(\d+)\s*(?:год|лет)/i.exec(text)
  if (years) return Number.parseInt(years[1]!, 10) * 12
  const months = /(\d+)\s*мес/i.exec(text)
  return months ? Number.parseInt(months[1]!, 10) : null
}

function paymentReply(text: string): Reply {
  const amount = parseAmount(text)
  const months = parseMonths(text)
  if (!amount || !months) {
    return {
      intent: 'payment',
      applicationId: null,
      full: 'Чтобы посчитать платёж, назовите сумму и срок, например: «Какой платёж по 1 млн ₽ на 12 месяцев?». Точный расчёт по вашей ставке — в калькуляторе на главной странице.',
      short: 'Назовите сумму и срок, например: «платёж по 1 млн ₽ на 12 месяцев».',
    }
  }
  const rate = 17.9
  const payment = calcAnnuityPayment(amount, rate, months)
  return {
    intent: 'payment',
    applicationId: null,
    full: `Ориентировочно: ${formatMoney(amount)} на ${months} мес. по ставке ${rate.toString().replace('.', ',')}% годовых — это около ${formatMoney(payment)} в месяц, переплата примерно ${formatMoney(payment * months - amount)}. Точный платёж зависит от ставки, которую банк назначит вам по заявке, — её увидите в предложении.`,
    short: `Примерно ${formatMoney(payment)} в месяц при ставке ${rate.toString().replace('.', ',')}%. Точный платёж — в калькуляторе.`,
  }
}

function adviceReply(app: AssistantApplicationDto): Reply {
  return {
    intent: 'decision',
    applicationId: app.id,
    full: `Чтобы заявку одобрили с большей вероятностью: запросите сумму поменьше или увеличьте срок — платёж станет легче для вашей выручки; приложите свежую выписку по счёту и отчётность; убедитесь, что даны все согласия, в том числе руководителя на запрос кредитной истории. Если откроете заявку № ${app.number}, я подскажу, чего именно не хватает.`,
    short: 'Попробуйте запросить меньшую сумму или больший срок и приложите свежую выписку по счёту.',
  }
}

function greetingReply(): Reply {
  return {
    intent: 'greeting',
    applicationId: null,
    full: 'Здравствуйте! Я помогаю разобраться с вашими заявками: объясню решение банка, подскажу, на каком этапе заявка и что можно улучшить, а ещё прикину платёж по сумме и сроку. Что вас интересует?',
    short: 'Здравствуйте! Спросите про решение по заявке, её этап или платёж.',
  }
}

function offTopicReply(): Reply {
  return {
    intent: 'off_topic',
    applicationId: null,
    full: 'Я отвечаю только по кредитам и вашим заявкам в кабинете. Могу рассказать, что решил банк, где сейчас заявка, какие кредиты подойдут и какой будет платёж.',
    short: 'Я отвечаю только по кредитам и заявкам в кабинете.',
  }
}

/** Вопрос → ответ по ключевым словам; для типовых вопросов из подсказок и ещё нескольких формулировок */
function answerFor(text: string, applicationId: string | null): Reply {
  const lower = text.toLowerCase()
  const app = pickApplication(applicationId)
  if (/(скор|балл|модел|bki|бки|кредитн\w+ истор|причин\w* код|фактор)/.test(lower)) {
    return {
      intent: 'internal_data',
      applicationId: null,
      full: 'Скоринговые баллы, факторы и данные бюро кредитных историй клиенту не раскрываются. Зато я могу объяснить решение простыми словами и подсказать, что улучшить.',
      short: 'Внутренние оценки банка я не раскрываю. Могу объяснить решение простыми словами.',
    }
  }
  if (/(платёж|платеж|переплат|ежемесяч)/.test(lower) || (parseAmount(lower) && parseMonths(lower))) return paymentReply(lower)
  if (/(улучш|одобрил|одобрят|повысить|шанс)/.test(lower)) return adviceReply(app)
  if (/(решил|решени|одобр|отказ|почему)/.test(lower)) return decisionReply(app)
  if (/(где|статус|этап|как дела|на каком)/.test(lower)) return statusReply(app)
  if (/(кредит|продукт|подойд|овердрафт|ставк)/.test(lower)) return productsReply()
  if (/(привет|здравствуй|добрый)/.test(lower)) return greetingReply()
  return offTopicReply()
}

const conversations = new Map<string, AssistantHistoryMessageDto[]>()
let seq = 0

function nextId(prefix: string): string {
  seq += 1
  return `${prefix}-${Date.now().toString(36)}-${seq}`
}

function chunks(text: string): string[] {
  const words = text.split(/(?<=\s)/)
  const result: string[] = []
  for (let index = 0; index < words.length; index += 3) result.push(words.slice(index, index + 3).join(''))
  return result
}

export const mockAssistantApi: AssistantApi = {
  async status(): Promise<AssistantStatusDto> {
    await sleep(150)
    if (state === 'off') throw unavailable()
    const llm = state === 'llm'
    return {
      enabled: llm,
      mode: llm ? 'llm' : 'rules',
      model: llm ? 'mock-llm' : null,
      host: null,
      reachable: llm,
      reason: llm ? null : 'Модель выключена в демо',
    }
  },

  async applications() {
    await sleep(200)
    if (state === 'off') throw unavailable()
    return APPLICATIONS.map((item) => ({ ...item }))
  },

  async createConversation() {
    await sleep(100)
    if (state === 'off') throw unavailable()
    const id = nextId('mock-conv')
    conversations.set(id, [])
    return { id, created_at: new Date().toISOString() }
  },

  async conversation(id) {
    await sleep(150)
    if (state === 'off') throw unavailable()
    const messages = conversations.get(id)
    // Как у сервиса: диалоги живут в памяти и пропадают с перезапуском — после перезагрузки страницы 404
    if (!messages) throw new AssistantError('not_found', 'Диалог не найден')
    return { id, created_at: new Date().toISOString(), messages: messages.map((item) => ({ ...item })) }
  },

  async ask(id: string, input: AskInput, handlers: AskHandlers, signal?: AbortSignal): Promise<AssistantAnswerDto> {
    if (state === 'off') {
      await sleep(300)
      throw unavailable()
    }
    const history = conversations.get(id)
    if (!history) throw new AssistantError('not_found', 'Диалог не найден')
    if (input.application_id && !APPLICATIONS.some((item) => item.id === input.application_id)) {
      throw new AssistantError('not_found', 'Заявка не найдена')
    }
    const mode: AssistantMode = state === 'llm' ? 'llm' : 'rules'
    const reply = answerFor(input.text, input.application_id)
    const text = mode === 'llm' ? reply.full : reply.short
    const now = new Date().toISOString()
    history.push({ id: nextId('mock-msg'), role: 'user', text: input.text, created_at: now, application_id: input.application_id, mode: null })

    handlers.onThinking?.()
    await sleep(mode === 'llm' ? 900 : 350)
    for (const part of chunks(text)) {
      if (signal?.aborted) throw new DOMException('Aborted', 'AbortError')
      handlers.onDelta(part)
      await sleep(mode === 'llm' ? 55 : 25)
    }

    const answer: AssistantAnswerDto = {
      message_id: nextId('mock-msg'),
      text,
      mode,
      intent: reply.intent,
      application_id: reply.applicationId,
      fallback_reason: null,
    }
    history.push({ id: answer.message_id, role: 'assistant', text, created_at: new Date().toISOString(), application_id: answer.application_id, mode })
    return answer
  },
}
