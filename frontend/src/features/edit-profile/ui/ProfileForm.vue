<script setup lang="ts">
import { reactive, ref } from 'vue'

import { session } from '@/entities/session'
import { identityApi, type MeDto } from '@/shared/api'
import { errorMessage } from '@/shared/lib'
import { BaseButton, TextField } from '@/shared/ui'

/** Правка своего профиля (PATCH /me/profile) */
const props = defineProps<{ me: MeDto }>()

const form = reactive({
  lastName: props.me.profile?.last_name ?? '',
  firstName: props.me.profile?.first_name ?? '',
  middleName: props.me.profile?.middle_name ?? '',
  position: props.me.profile?.position ?? '',
})
const errors = reactive<{ lastName?: string; firstName?: string }>({})
const pending = ref(false)
const message = ref<{ text: string; ok: boolean } | null>(null)

async function submit() {
  errors.lastName = form.lastName.trim() ? undefined : 'Укажите фамилию'
  errors.firstName = form.firstName.trim() ? undefined : 'Укажите имя'
  if (errors.lastName || errors.firstName) return
  pending.value = true
  message.value = null
  try {
    const me = await identityApi.updateProfile({
      last_name: form.lastName.trim(),
      first_name: form.firstName.trim(),
      middle_name: form.middleName.trim() || null,
      position: form.position.trim() || null,
    })
    session.setMe(me)
    message.value = { text: 'Сохранено', ok: true }
  } catch (caught) {
    message.value = { text: errorMessage(caught), ok: false }
  } finally {
    pending.value = false
  }
}
</script>

<template>
  <form class="space-y-4" novalidate @submit.prevent="submit">
    <fieldset :disabled="!session.can('profile.update')" class="grid gap-3 sm:grid-cols-2">
      <TextField v-model="form.lastName" label="Фамилия" dense :error="errors.lastName" />
      <TextField v-model="form.firstName" label="Имя" dense :error="errors.firstName" />
      <TextField v-model="form.middleName" label="Отчество" dense />
      <TextField v-model="form.position" label="Должность" dense />
    </fieldset>
    <div class="flex items-center gap-3">
      <BaseButton v-if="session.can('profile.update')" type="submit" size="s" :loading="pending">Сохранить</BaseButton>
      <p v-else class="text-sm text-ink-secondary">У вашей роли нет права менять профиль.</p>
      <p v-if="message" class="text-sm" :class="message.ok ? 'text-success' : 'text-brand'" role="status">{{ message.text }}</p>
    </div>
  </form>
</template>
