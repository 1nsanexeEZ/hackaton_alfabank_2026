<script setup lang="ts">
import { shallowRef } from 'vue'

import { InnCheckForm } from '@/features/check-inn'
import type { InnCheckDto } from '@/shared/api'
import { PanelCard } from '@/shared/ui'
import { AdminPageHeader } from '@/widgets/admin-layout'
import { InnCheckReport } from '@/widgets/inn-check-report'

const result = shallowRef<InnCheckDto | null>(null)
</script>

<template>
  <AdminPageHeader
    title="Проверка по ИНН"
    description="Компания до заявки, даже если её нет в системе: ЕГРЮЛ / ЕГРИП, ФНС, Контур и стоп-лист банка, сверка с реквизитами из документов. Скоринг считается только по заявке"
  />

  <PanelCard>
    <InnCheckForm @checked="(value) => (result = value)" />
  </PanelCard>

  <InnCheckReport v-if="result" :result="result" class="mt-6" />
</template>
