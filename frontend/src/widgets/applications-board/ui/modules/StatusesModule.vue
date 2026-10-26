<script setup lang="ts">
import { computed } from 'vue'

import { DonutChart } from '@/shared/ui'

import { STATUS_GROUPS } from '../../model/status'
import { useBoard } from '../../model/useBoardData'

const { overview } = useBoard()

const segments = computed(() => {
  const statuses = overview.value?.statuses ?? []
  return STATUS_GROUPS.map((group) => ({
    label: group.label,
    color: group.color,
    value: statuses.filter((item) => group.statuses.includes(item.key)).reduce((sum, item) => sum + item.count, 0),
  }))
})
</script>

<template>
  <DonutChart :segments="segments" center-label="заявок" />
</template>
