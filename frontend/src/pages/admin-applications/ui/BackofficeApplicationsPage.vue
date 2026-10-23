<script setup lang="ts">
import { AdminPageHeader } from '@/widgets/admin-layout'
import { UnderwriterQueue } from '@/widgets/underwriter-queue'

/** Заявки в режиме real: очередь андеррайтера с бэкенда — то, что не решилось автоматически */
</script>

<template>
  <AdminPageHeader title="Заявки" description="Очередь специалиста: заявки, которые конвейер передал на ручное рассмотрение" />
  <UnderwriterQueue />
</template>
