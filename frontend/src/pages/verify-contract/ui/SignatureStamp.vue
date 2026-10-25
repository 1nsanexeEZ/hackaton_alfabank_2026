<script setup lang="ts">
import { computed } from 'vue'

import type { ContractSignatureDto } from '@/shared/api'
import { formatDate, formatMoscowDateTime } from '@/shared/lib'

/**
 * Штамп электронной подписи в духе ГОСТ Р 7.0.97: синяя рамка, вид подписи, подписант, полномочие и время по МСК.
 * У подписи банка — ещё сертификат и метка времени. Картинку собственноручной подписи не рисуем.
 */
const props = defineProps<{ signature: ContractSignatureDto }>()

const AUTHORITY: Record<NonNullable<ContractSignatureDto['authority']>, string> = {
  registry: 'руководитель',
  power_of_attorney: 'по доверенности',
}

const METHOD: Record<string, string> = {
  password: 'пароль от кабинета',
  pades: 'подпись в файле PDF (PAdES)',
}

const title = computed(() =>
  props.signature.type === 'simple' ? 'Подписано простой электронной подписью' : 'Документ подписан усиленной электронной подписью',
)

const rows = computed(() => {
  const { signature } = props
  const certificate = signature.certificate
  return [
    { label: 'Подписант', value: signature.signer },
    signature.role && { label: 'Должность', value: signature.role },
    signature.authority && { label: 'Полномочие', value: AUTHORITY[signature.authority] ?? signature.authority },
    { label: 'Подписано', value: formatMoscowDateTime(signature.signed_at) },
    { label: 'Способ', value: METHOD[signature.method] ?? signature.method },
    signature.rules_version && { label: 'Правила ЭП', value: `ред. от ${signature.rules_version.split('-').reverse().join('.')}` },
    certificate && { label: 'Сертификат', value: certificate.serial, mono: true },
    certificate && { label: 'Владелец', value: certificate.subject },
    certificate && { label: 'Издатель', value: certificate.issuer },
    certificate && { label: 'Действует', value: `с ${formatDate(certificate.valid_from)} по ${formatDate(certificate.valid_to)}` },
    signature.timestamp_at && { label: 'Метка времени', value: formatMoscowDateTime(signature.timestamp_at) },
  ].filter((row): row is { label: string; value: string; mono?: boolean } => Boolean(row))
})
</script>

<template>
  <figure class="rounded-lg border-2 border-info p-4 text-info">
    <figcaption class="text-[11px] font-bold tracking-wide uppercase">{{ title }}</figcaption>
    <p class="mt-0.5 text-xs text-ink-secondary">{{ signature.party === 'bank' ? 'Банк' : 'Заёмщик' }}</p>
    <dl class="mt-3 grid gap-x-3 gap-y-1.5 text-sm sm:grid-cols-[8rem_1fr]">
      <template v-for="row in rows" :key="row.label">
        <dt class="text-xs text-ink-secondary sm:text-sm">{{ row.label }}</dt>
        <dd class="text-ink" :class="row.mono ? 'font-mono text-xs break-all sm:text-sm' : 'break-words'">{{ row.value }}</dd>
      </template>
    </dl>
  </figure>
</template>
