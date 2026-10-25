<script setup lang="ts">
import { computed } from 'vue'

import { DonutChart } from '@/shared/ui'

import { STATUS_GROUPS } from '../../model/status'
import { useBoard } from '../../model/useBoardData'

const { applications } = useBoard()

const segments = computed(() =>
  STATUS_GROUPS.map((group) => ({
    label: group.label,
    color: group.color,
    value: applications.value.filter((item) => group.statuses.includes(item.status)).length,
  })),
)
</script>

<template>
  <DonutChart :segments="segments" center-label="заявок" />
</template>
