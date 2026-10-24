<script setup lang="ts">
import { SegmentedControl, TextField } from '@/shared/ui'

import type { ThirdPartyForm } from '../model/thirdParty'

/**
 * Третье лицо в заявке — одинаково для выгодоприобретателя и владельца залога:
 * организация или ИП — наименование и ИНН, физлицо — ФИО и ИНН по желанию.
 * prefix — путь в ошибках и data-field: beneficiary.beneficiary, collateral.owner_party.
 */
const props = defineProps<{ prefix: string; errors: Record<string, string> }>()

const party = defineModel<ThirdPartyForm>('party', { required: true })

const KIND_OPTIONS: { value: ThirdPartyForm['kind']; label: string }[] = [
  { value: 'organization', label: 'Организация / ИП' },
  { value: 'person', label: 'Физлицо' },
]

const error = (field: string) => props.errors[`${props.prefix}.${field}`]
</script>

<template>
  <div class="space-y-4">
    <SegmentedControl v-model="party.kind" :options="KIND_OPTIONS" label="Кто это" small />
    <div class="grid gap-4 sm:grid-cols-[2fr_1fr]">
      <TextField
        v-model="party.name"
        :data-field="`${prefix}.name`"
        :label="party.kind === 'organization' ? 'Наименование' : 'ФИО'"
        :placeholder="party.kind === 'organization' ? 'ООО «Принципал» или ИП Иванов И. И.' : 'Иванов Иван Иванович'"
        :maxlength="300"
        :error="error('name')"
      />
      <TextField
        v-model="party.inn"
        :data-field="`${prefix}.inn`"
        label="ИНН"
        inputmode="numeric"
        :maxlength="12"
        :placeholder="party.kind === 'organization' ? '10 или 12 цифр' : 'Необязательно'"
        :error="error('inn')"
      />
    </div>
  </div>
</template>
