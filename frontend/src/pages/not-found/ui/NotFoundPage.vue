<script setup lang="ts">
import { ROUTE_PATH } from '@/shared/config'
import { BaseButton, BaseContainer } from '@/shared/ui'
</script>

<template>
  <BaseContainer as="section" class="flex flex-col items-center py-24 text-center lg:py-32">
    <p class="text-6xl font-bold text-brand lg:text-8xl">404</p>
    <h1 class="text-title mt-6">Страница не найдена</h1>
    <p class="text-lead mt-4 max-w-md text-ink-secondary">
      Возможно, раздел ещё в разработке. Вернитесь на главную, чтобы подобрать кредит.
    </p>
    <BaseButton class="mt-8" size="l" :to="ROUTE_PATH.home">На главную</BaseButton>
  </BaseContainer>
</template>
