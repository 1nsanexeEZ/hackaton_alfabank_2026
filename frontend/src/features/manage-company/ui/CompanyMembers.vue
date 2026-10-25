<script setup lang="ts">
import { UserPlus } from 'lucide-vue-next'
import { reactive, ref } from 'vue'

import { customer } from '@/entities/customer'
import type { MemberDto, MemberRole, PowerOfAttorneyInput } from '@/shared/api'
import { formatDate } from '@/shared/lib'
import { BaseButton, CheckboxField, SelectField, TextField } from '@/shared/ui'

/**
 * Кто в компании и что может: подать заявку, подписать. Бухгалтер готовит заявку,
 * подписывает руководитель по реестру или сотрудник с доверенностью на подпись.
 */
defineProps<{ members: MemberDto[]; canManage: boolean; busy: string | null }>()

const emit = defineEmits<{
  add: [login: string, role: MemberRole, done: () => void]
  grant: [accountId: string, input: PowerOfAttorneyInput, done: () => void]
  changeRole: [accountId: string, role: MemberRole]
  remove: [accountId: string]
}>()

/** Себя не меняем и не удаляем: так легко потерять доступ к компании */
const isMe = (member: MemberDto) => member.account_id === customer.state.me?.id
const removing = ref<string | null>(null)

const ROLE: Record<MemberRole, string> = { owner: 'Собственник', director: 'Руководитель', accountant: 'Бухгалтер', employee: 'Сотрудник' }
const ROLE_OPTIONS = (Object.keys(ROLE) as MemberRole[]).map((value) => ({ value, label: ROLE[value] }))
const PERMISSION: Record<string, string> = {
  view: 'просмотр',
  submit_application: 'подача заявок',
  sign: 'подпись',
  manage_members: 'участники',
  edit_financials: 'отчётность',
}

const name = (member: MemberDto) =>
  [member.last_name, member.first_name, member.middle_name].filter(Boolean).join(' ') || 'Без имени'

const adding = ref(false)
const newMember = reactive({ login: '', role: 'employee' as MemberRole })

function add() {
  if (!newMember.login.trim()) return
  emit('add', newMember.login, newMember.role, () => {
    adding.value = false
    newMember.login = ''
  })
}

const today = () => new Date().toISOString().slice(0, 10)
const inYear = () => new Date(Date.now() + 365 * 24 * 3600 * 1000).toISOString().slice(0, 10)

const granting = ref<string | null>(null)
const poa = reactive({ number: '', issuedAt: today(), validUntil: inYear(), submit: true, sign: true })

function openGrant(accountId: string) {
  granting.value = accountId
  Object.assign(poa, { number: '', issuedAt: today(), validUntil: inYear(), submit: true, sign: true })
}

function grant(accountId: string) {
  const scope: PowerOfAttorneyInput['scope'] = []
  if (poa.submit) scope.push('submit_application')
  if (poa.sign) scope.push('sign')
  if (!poa.number.trim() || !scope.length) return
  emit('grant', accountId, { number: poa.number.trim(), issued_at: poa.issuedAt, valid_until: poa.validUntil, scope }, () => (granting.value = null))
}
</script>

<template>
  <section>
    <div class="flex flex-wrap items-end justify-between gap-3">
      <div>
        <h3 class="text-base font-bold text-ink">Участники и полномочия</h3>
        <p class="mt-0.5 text-sm text-ink-secondary">Подписать договор может руководитель компании или сотрудник с доверенностью</p>
      </div>
      <BaseButton v-if="canManage && !adding" size="s" variant="secondary" @click="adding = true">
        <UserPlus class="size-4" aria-hidden="true" />
        Добавить
      </BaseButton>
    </div>

    <form v-if="adding" class="mt-4 space-y-3 rounded-2xl bg-surface-soft p-4" @submit.prevent="add">
      <div class="grid gap-3 sm:grid-cols-2">
        <TextField v-model="newMember.login" label="Email или телефон" placeholder="Учётная запись уже есть в банке" dense />
        <SelectField v-model="newMember.role" label="Роль" :options="ROLE_OPTIONS" dense />
      </div>
      <div class="flex flex-wrap gap-3">
        <BaseButton type="submit" size="s" :loading="busy === 'member'" :disabled="!newMember.login.trim()">Добавить</BaseButton>
        <BaseButton size="s" variant="ghost" :disabled="busy === 'member'" @click="adding = false">Отмена</BaseButton>
      </div>
    </form>

    <ul class="mt-3 space-y-2">
      <li v-for="member in members" :key="member.account_id" class="rounded-2xl bg-surface-soft p-4">
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div class="min-w-0">
            <p class="font-semibold text-ink">{{ name(member) }}</p>
            <p class="text-sm text-ink-secondary">
              {{ member.position && member.position.toLowerCase() !== ROLE[member.role].toLowerCase() ? `${ROLE[member.role]} · ${member.position}` : ROLE[member.role] }}
            </p>
            <p class="mt-1 text-xs text-ink-secondary">
              <template v-if="member.authority === 'registry'">Руководитель компании, право подписи</template>
              <template v-else-if="member.power_of_attorney">
                Доверенность № {{ member.power_of_attorney.number }} до {{ formatDate(member.power_of_attorney.valid_until) }}
                <span v-if="!member.power_of_attorney.is_valid" class="text-brand"> — недействительна</span>
              </template>
              <template v-else>Полномочия не подтверждены</template>
            </p>
            <p class="mt-1 text-xs text-ink-muted">Может: {{ member.permissions.map((item) => PERMISSION[item] ?? item).join(', ') }}</p>
          </div>
          <div v-if="canManage && !isMe(member)" class="flex flex-wrap items-center gap-2">
            <SelectField
              :model-value="member.role"
              :label="`Роль: ${name(member)}`"
              :options="ROLE_OPTIONS"
              dense
              hide-label
              @update:model-value="(role: MemberRole) => role !== member.role && emit('changeRole', member.account_id, role)"
            />
            <BaseButton
              v-if="member.authority !== 'registry' && granting !== member.account_id"
              size="s"
              variant="ghost"
              @click="openGrant(member.account_id)"
            >
              Выдать доверенность
            </BaseButton>
            <BaseButton v-if="removing !== member.account_id" size="s" variant="ghost" @click="removing = member.account_id">Удалить</BaseButton>
          </div>
          <span v-else-if="isMe(member)" class="text-xs text-ink-muted">Это вы</span>
        </div>

        <div v-if="removing === member.account_id" class="mt-3 space-y-2 border-t border-line pt-3">
          <p class="text-sm text-ink">Удалить участника «{{ name(member) }}» из компании? Он больше не увидит заявки компании и не сможет действовать от её имени.</p>
          <div class="flex flex-wrap gap-3">
            <BaseButton size="s" variant="secondary" :loading="busy === `remove:${member.account_id}`" @click="emit('remove', member.account_id)">
              Удалить
            </BaseButton>
            <BaseButton size="s" variant="ghost" :disabled="Boolean(busy)" @click="removing = null">Отмена</BaseButton>
          </div>
        </div>

        <form v-if="granting === member.account_id" class="mt-3 space-y-3 border-t border-line pt-3" @submit.prevent="grant(member.account_id)">
          <div class="grid gap-3 sm:grid-cols-3">
            <TextField v-model="poa.number" label="Номер доверенности" dense />
            <TextField v-model="poa.issuedAt" label="Выдана" type="date" dense />
            <TextField v-model="poa.validUntil" label="Действует до" type="date" dense />
          </div>
          <div class="flex flex-wrap gap-4">
            <CheckboxField v-model="poa.submit">Подавать заявки</CheckboxField>
            <CheckboxField v-model="poa.sign">Подписывать договоры</CheckboxField>
          </div>
          <div class="flex flex-wrap gap-3">
            <BaseButton type="submit" size="s" :loading="busy === `poa:${member.account_id}`" :disabled="!poa.number.trim()">
              Выдать
            </BaseButton>
            <BaseButton size="s" variant="ghost" @click="granting = null">Отмена</BaseButton>
          </div>
        </form>
      </li>
    </ul>
  </section>
</template>
