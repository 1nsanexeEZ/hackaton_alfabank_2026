<script setup lang="ts">
import { SegmentedControl } from '@/shared/ui'

import { PRODUCT_FILTER_OPTIONS, type ProductFilter } from '../model/useProductFilter'

const filter = defineModel<ProductFilter>({ required: true })
</script>

<template>
  <SegmentedControl v-model="filter" :options="PRODUCT_FILTER_OPTIONS" label="Как получить деньги" />
</template>
