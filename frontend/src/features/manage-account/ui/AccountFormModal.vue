<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'

import { roleTitle } from '@/entities/role'
import { identityApi, type AccountDto } from '@/shared/api'
import { errorMessage } from '@/shared/lib'
import { BaseButton, BaseModal, SelectField, TextField } from '@/shared/ui'

/** Создание и правка аккаунта сотрудника или клиента (POST/PATCH /accounts) */
const props = defineProps<{
  /** null — создаём новый аккаунт */
  account: AccountDto | null
  roles: readonly { id: string; name: string }[]
}>()
const open = defineModel<boolean>('open', { required: true })
const emit = defineEmits<{ saved: [account: AccountDto] }>()

const isEdit = computed(() => Boolean(props.account))

function emptyForm() {
  const account = props.account
  return {
    lastName: account?.profile?.last_name ?? '',
    firstName: account?.profile?.first_name ?? '',
    middleName: account?.profile?.middle_name ?? '',
    position: account?.profile?.position ?? '',
    email: account?.email ?? '',
    phone: account?.phone ?? '',
    password: '',
    roleId: account?.role.id ?? props.roles[0]?.id ?? '',
  }
}

const form = reactive(emptyForm())
const errors = reactive<Record<string, string | undefined>>({})
const formError = ref<string | null>(null)
const pending = ref(false)

watch(open, (isOpen) => {
  if (!isOpen) return
  Object.assign(form, emptyForm())
  Object.keys(errors).forEach((key) => (errors[key] = undefined))
  formError.value = null
})

const roleOptions = computed(() => props.roles.map((role) => ({ value: role.id, label: roleTitle(role.name) })))

/** Телефон к формату бэкенда: 8 (999) 123-45-67 → +79991234567 */
function normalizePhone(value: string): string {
  let digits = value.replace(/\D/g, '')
  if (digits.length === 11 && digits.startsWith('8')) digits = `7${digits.slice(1)}`
  return digits ? `+${digits}` : ''
}

function validate(): boolean {
  const phone = normalizePhone(form.phone)
  errors.lastName = form.lastName.trim() ? undefined : 'Укажите фамилию'
  errors.firstName = form.firstName.trim() ? undefined : 'Укажите имя'
  errors.email = form.email && !/^\S+@\S+\.\S+$/.test(form.email.trim()) ? 'Проверьте email' : undefined
  errors.phone = phone && !/^\+\d{10,15}$/.test(phone) ? 'От 10 до 15 цифр' : undefined
  if (!form.email.trim() && !phone) errors.email = 'Нужен email или телефон'
  errors.password =
    (!isEdit.value || form.password) && form.password.length < 8 ? 'Минимум 8 символов' : undefined
  errors.roleId = form.roleId ? undefined : 'Выберите роль'
  return Object.values(errors).every((value) => !value)
}

async function submit() {
  formError.value = null
  if (!validate()) return
  pending.value = true
  const profile = {
    last_name: form.lastName.trim(),
    first_name: form.firstName.trim(),
    middle_name: form.middleName.trim() || null,
    position: form.position.trim() || null,
  }
  const email = form.email.trim().toLowerCase() || undefined
  const phone = normalizePhone(form.phone) || undefined
  try {
    const saved = props.account
      ? await identityApi.updateAccount(props.account.id, {
          email,
          phone,
          role_id: form.roleId,
          profile,
          ...(form.password ? { password: form.password } : {}),
        })
      : await identityApi.createAccount({ email, phone, password: form.password, role_id: form.roleId, profile })
    emit('saved', saved)
    open.value = false
  } catch (caught) {
    formError.value = errorMessage(caught)
  } finally {
    pending.value = false
  }
}
</script>

<template>
  <BaseModal v-model:open="open" :title="isEdit ? 'Изменить пользователя' : 'Новый пользователь'" wide>
    <form id="account-form" class="grid gap-3 sm:grid-cols-2" novalidate @submit.prevent="submit">
      <TextField v-model="form.lastName" label="Фамилия" dense :error="errors.lastName" />
      <TextField v-model="form.firstName" label="Имя" dense :error="errors.firstName" />
      <TextField v-model="form.middleName" label="Отчество" dense />
      <TextField v-model="form.position" label="Должность" dense />
      <TextField v-model="form.email" label="Email" type="email" dense :error="errors.email" />
      <TextField v-model="form.phone" filter="phone" label="Телефон" dense :error="errors.phone" placeholder="+7 999 123-45-67" />
      <TextField
        v-model="form.password"
        label="Пароль"
        type="password"
        autocomplete="new-password"
        dense
        :error="errors.password"
        :hint="isEdit ? 'Оставьте пустым, чтобы не менять' : 'Минимум 8 символов'"
      />
      <SelectField v-if="roleOptions.length" v-model="form.roleId" label="Роль" :options="roleOptions" dense />
    </form>
    <p v-if="formError" class="mt-4 rounded-xl bg-brand-soft px-4 py-3 text-sm text-brand" role="alert">{{ formError }}</p>
    <template #footer>
      <BaseButton variant="secondary" @click="open = false">Отмена</BaseButton>
      <BaseButton type="submit" form="account-form" :loading="pending">{{ isEdit ? 'Сохранить' : 'Создать' }}</BaseButton>
    </template>
  </BaseModal>
</template>
