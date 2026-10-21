import type { ApplicationDraft, ApplicationStatus } from '@/entities/application'

export interface SubmitApplicationPayload extends ApplicationDraft {
  inn: string
  contactName: string
  purpose: string
}

export interface SubmitApplicationResult {
  id: string
  number: string
  status: ApplicationStatus
}

const MOCK_LATENCY_MS = 900

/**
 * Мок отправки заявки, пока нет BFF.
 * TODO: заменить на POST /api/applications, контракт ответа оставить тем же.
 */
export async function submitApplication(payload: SubmitApplicationPayload): Promise<SubmitApplicationResult> {
  await new Promise((resolve) => setTimeout(resolve, MOCK_LATENCY_MS))

  const suffix = Date.now().toString().slice(-6)
  return {
    id: `${payload.inn}-${suffix}`,
    number: `ЗК-${suffix}`,
    status: 'submitted',
  }
}
