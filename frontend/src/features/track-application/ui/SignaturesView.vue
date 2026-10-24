<script setup lang="ts">
import { PenLine } from 'lucide-vue-next'
import { computed, shallowRef, watch } from 'vue'

import { clientApi, type ContractSignatureDto } from '@/shared/api'
import { formatMoscowDateTime } from '@/shared/lib'

/**
 * Подписи сторон подписанного договора — те же сведения, что на странице проверки по QR
 * (GET /contracts/verify/{document_id}): заёмщик — простая ЭП паролем, банк — усиленная, PAdES с меткой
 * времени. Не загрузились — блок просто не показываем, договор и так можно скачать и проверить.
 */
const props = defineProps<{ documentId: string }>()

const signatures = shallowRef<ContractSignatureDto[]>([])

watch(
  () => props.documentId,
  async (id) => {
    try {
      signatures.value = (await clientApi.verifyContract(id)).signatures
    } catch {
      signatures.value = []
    }
  },
  { immediate: true },
)

const AUTHORITY = { registry: 'руководитель по ЕГРЮЛ', power_of_attorney: 'по доверенности' } as const
const METHOD: Record<string, string> = { password: 'пароль от кабинета', pades: 'подпись в PDF (PAdES)' }

/** Серийный номер сертификата длинный — в карточке хватает начала и конца */
const shortSerial = (serial: string) => (serial.length > 20 ? `${serial.slice(0, 8)}…${serial.slice(-8)}` : serial)

const cards = computed(() =>
  signatures.value.map((signature) => ({
    party: signature.party,
    title: signature.party === 'client' ? 'Заёмщик' : 'Банк',
    kind: signature.type === 'simple' ? 'простая электронная подпись' : 'усиленная электронная подпись',
    rows: [
      { label: 'Подписант', value: signature.signer, mono: false },
      ...(signature.role ? [{ label: 'Должность', value: signature.role, mono: false }] : []),
      ...(signature.authority ? [{ label: 'Полномочие', value: AUTHORITY[signature.authority], mono: false }] : []),
      ...(signature.certificate ? [{ label: 'Сертификат', value: shortSerial(signature.certificate.serial), mono: true }] : []),
      ...(signature.certificate ? [{ label: 'Издатель', value: signature.certificate.issuer, mono: false }] : []),
      { label: signature.timestamp_at ? 'Метка времени' : 'Подписано', value: formatMoscowDateTime(signature.timestamp_at ?? signature.signed_at), mono: false },
      { label: 'Способ', value: METHOD[signature.method] ?? signature.method, mono: false },
    ],
  })),
)
</script>

<template>
  <div v-if="cards.length" class="grid gap-3 sm:grid-cols-2">
    <section
      v-for="card in cards"
      :key="card.party"
      class="flex flex-col gap-3 rounded-2xl border border-line px-4 py-4"
      :aria-label="`Подпись: ${card.title.toLowerCase()}`"
    >
      <div class="flex items-center gap-2.5">
        <span
          v-if="card.party === 'bank'"
          class="flex size-7 items-center justify-center rounded-lg bg-brand text-sm font-black text-white"
          aria-hidden="true"
        >
          А
        </span>
        <span v-else class="flex size-7 items-center justify-center rounded-lg bg-info-soft text-info" aria-hidden="true">
          <PenLine class="size-4" />
        </span>
        <div class="leading-tight">
          <p class="text-sm font-bold text-ink">{{ card.title }}</p>
          <p class="text-xs text-ink-secondary">{{ card.kind }}</p>
        </div>
      </div>
      <dl class="grid grid-cols-[6rem_minmax(0,1fr)] gap-x-2.5 gap-y-1 text-[0.8125rem]">
        <template v-for="row in card.rows" :key="row.label">
          <dt class="text-ink-secondary">{{ row.label }}</dt>
          <dd class="break-words text-ink" :class="row.mono && 'font-mono text-xs'">{{ row.value }}</dd>
        </template>
      </dl>
    </section>
  </div>
</template>
