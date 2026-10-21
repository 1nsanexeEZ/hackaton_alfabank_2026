<script setup lang="ts">
import { ref } from 'vue'

import { identityApi, type AccountDto } from '@/shared/api'
import { errorMessage } from '@/shared/lib'
import { BaseButton, BaseModal } from '@/shared/ui'

/** Мягкое удаление: аккаунт перестаёт входить в систему, запись остаётся для истории */
const props = defineProps<{ account: AccountDto | null; name: string }>()
const open = defineModel<boolean>('open', { required: true })
const emit = defineEmits<{ deleted: [id: string] }>()

const pending = ref(false)
const error = ref<string | null>(null)

async function confirm() {
  if (!props.account) return
  pending.value = true
  error.value = null
  try {
    await identityApi.deleteAccount(props.account.id)
    emit('deleted', props.account.id)
    open.value = false
  } catch (caught) {
    error.value = errorMessage(caught)
  } finally {
    pending.value = false
  }
}
</script>

<template>
  <BaseModal v-model:open="open" title="Удалить пользователя?">
    <p class="text-sm text-ink">
      <b class="font-semibold">{{ name }}</b> больше не сможет войти. Уже выданный токен действует до конца срока — до 30 минут.
    </p>
    <p v-if="error" class="mt-3 text-sm text-brand" role="alert">{{ error }}</p>
    <template #footer>
      <BaseButton variant="secondary" @click="open = false">Отмена</BaseButton>
      <BaseButton :loading="pending" @click="confirm">Удалить</BaseButton>
    </template>
  </BaseModal>
</template>
