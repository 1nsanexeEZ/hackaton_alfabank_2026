import { reactive, ref, toValue, watch, type MaybeRefOrGetter } from 'vue'

import type { ApplicationDraft } from '@/entities/application'
import { isValidInn, onlyDigits } from '@/shared/lib'

import { submitApplication, type SubmitApplicationResult } from '../api/submitApplication'

export const PURPOSE_OPTIONS = [
  { value: 'working-capital', label: 'Пополнение оборотных средств' },
  { value: 'development', label: 'Развитие бизнеса' },
  { value: 'equipment', label: 'Покупка оборудования или транспорта' },
  { value: 'refinancing', label: 'Рефинансирование кредитов' },
  { value: 'other', label: 'Другое' },
] as const

export type Purpose = (typeof PURPOSE_OPTIONS)[number]['value']

type Field = 'inn' | 'contactName' | 'consent'

/** Синтетические данные для быстрой проверки сценария экспертами */
const DEMO_VALUES = {
  inn: '7720123457',
  contactName: 'Анна Смирнова',
  purpose: 'equipment',
} as const

function createEmptyForm() {
  return {
    inn: '',
    contactName: '',
    purpose: 'working-capital' as Purpose,
    consent: false,
  }
}

export function useApplicationForm(draft: MaybeRefOrGetter<ApplicationDraft>) {
  const form = reactive(createEmptyForm())
  const errors = reactive<Partial<Record<Field, string>>>({})
  const status = ref<'idle' | 'submitting' | 'success' | 'error'>('idle')
  const result = ref<SubmitApplicationResult | null>(null)
  const wasSubmitted = ref(false)

  function validate(): boolean {
    const inn = onlyDigits(form.inn)
    errors.inn = isValidInn(inn) ? undefined : 'Проверьте ИНН: 10 цифр для компании или 12 для ИП'
    errors.contactName = form.contactName.trim().length >= 2 ? undefined : 'Укажите, как к вам обращаться'
    errors.consent = form.consent ? undefined : 'Нужно согласие на обработку данных'
    return !errors.inn && !errors.contactName && !errors.consent
  }

  // После первой попытки отправки подсвечиваем ошибки сразу при вводе
  watch(form, () => {
    if (wasSubmitted.value) validate()
  })

  async function submit() {
    wasSubmitted.value = true
    if (!validate() || status.value === 'submitting') return

    status.value = 'submitting'
    try {
      result.value = await submitApplication({
        ...toValue(draft),
        inn: onlyDigits(form.inn),
        contactName: form.contactName.trim(),
        purpose: form.purpose,
      })
      status.value = 'success'
    } catch {
      status.value = 'error'
    }
  }

  function reset() {
    Object.assign(form, createEmptyForm())
    for (const key of Object.keys(errors) as Field[]) errors[key] = undefined
    wasSubmitted.value = false
    result.value = null
    status.value = 'idle'
  }

  function fillDemo() {
    Object.assign(form, { ...DEMO_VALUES, consent: true })
  }

  return { form, errors, status, result, submit, reset, fillDemo }
}
