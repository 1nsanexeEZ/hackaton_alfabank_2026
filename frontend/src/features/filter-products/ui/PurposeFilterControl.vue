<script setup lang="ts">
import { SelectField } from '@/shared/ui'

import { PURPOSE_FILTER_OPTIONS, type PurposeFilter } from '../model/useProductFilter'

const purpose = defineModel<PurposeFilter>({ required: true })
</script>

<template>
  <SelectField v-model="purpose" label="Цель кредита" hide-label :options="PURPOSE_FILTER_OPTIONS" dense />
</template>
