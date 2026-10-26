<script setup lang="ts">
import { Trash2 } from 'lucide-vue-next'
import { computed, reactive, ref } from 'vue'

import { useProductCatalog } from '@/entities/credit-product'
import { useSession } from '@/entities/session'
import { backofficeApi, type KeyRateRecordDto, type KeyRateSource } from '@/shared/api'
import { errorMessage, formatDate, formatDateTime, formatPercent, useAsyncData } from '@/shared/lib'
import { AsyncState, BaseBadge, BaseButton, PanelCard, TextField } from '@/shared/ui'
import { AdminPageHeader } from '@/widgets/admin-layout'

/**
 * Ключевая ставка Банка России (/market/key-rates): от неё считаются ставки каталога и предложений,
 * а предодобрения пересчитываются при её смене. Ставка вводится с даты начала действия; удалить можно
 * только ещё не действовавшую. Смотреть — scoring.read, вести — scoring.update
 */
const { can } = useSession()
const canEdit = computed(() => can('scoring.update'))

const history = useAsyncData(() => backofficeApi.keyRates())
// Ставки каталога идут за ключевой: после её смены витрина и калькулятор в этой вкладке должны перечитать каталог
const { reload: reloadCatalog } = useProductCatalog()

const SOURCE_LABEL: Record<KeyRateSource, string> = {
  admin: 'введена в админке',
  cbr: 'с cbr.ru',
  settings: 'из настроек: на эту дату ставки нет',
}

const rate = (value: string) => formatPercent(Number(value))

const form = reactive({ value: '', effectiveFrom: '', decidedOn: '', note: '' })
const errors = reactive<{ value?: string; effectiveFrom?: string; decidedOn?: string }>({})
const saving = ref(false)
const saveError = ref<string | null>(null)

const percent = (value: string) => Number(value.trim().replace(',', '.'))

function validate() {
  errors.value = undefined
  errors.effectiveFrom = undefined
  errors.decidedOn = undefined
  const value = percent(form.value)
  if (!form.value.trim() || !(value >= 0 && value <= 100)) errors.value = 'От 0 до 100%'
  if (!form.effectiveFrom) errors.effectiveFrom = 'Укажите дату'
  if (form.decidedOn && form.effectiveFrom && form.decidedOn > form.effectiveFrom) errors.decidedOn = 'Не позже даты начала действия'
  return !errors.value && !errors.effectiveFrom && !errors.decidedOn
}

async function add() {
  saveError.value = null
  // Незаполненные поля трясёт общий обработчик отправки форм (shared/lib/shake)
  if (!validate()) return
  saving.value = true
  try {
    await backofficeApi.addKeyRate({
      value: percent(form.value).toFixed(2),
      effective_from: form.effectiveFrom,
      decided_on: form.decidedOn || null,
      note: form.note.trim() || null,
    })
    Object.assign(form, { value: '', effectiveFrom: '', decidedOn: '', note: '' })
    await history.reload()
    void reloadCatalog()
  } catch (caught) {
    saveError.value = errorMessage(caught)
  } finally {
    saving.value = false
  }
}

const removing = ref<string | null>(null)
const removeError = ref<string | null>(null)

async function remove(item: KeyRateRecordDto) {
  removeError.value = null
  removing.value = item.effective_from
  try {
    await backofficeApi.removeKeyRate(item.effective_from)
    await history.reload()
    void reloadCatalog()
  } catch (caught) {
    removeError.value = errorMessage(caught)
  } finally {
    removing.value = null
  }
}
</script>

<template>
  <AdminPageHeader
    title="Ключевая ставка"
    description="Ставка Банка России, от которой считаются ставки продуктов и предложений. Смена ставки пересчитывает предодобрения"
  />

  <AsyncState :loading="history.loading.value && !history.data.value" :error="history.data.value ? null : history.error.value" @retry="history.reload">
    <div v-if="history.data.value" class="space-y-4">
      <div class="grid gap-4 lg:grid-cols-[minmax(0,20rem)_minmax(0,1fr)]">
        <PanelCard title="Действует сегодня">
          <p class="text-4xl font-bold text-ink tabular-nums">{{ rate(history.data.value.current.value) }}</p>
          <p class="mt-2 text-sm text-ink-secondary">
            <template v-if="history.data.value.current.effective_from">с {{ formatDate(history.data.value.current.effective_from) }} · </template>
            {{ SOURCE_LABEL[history.data.value.current.source] }}
          </p>
        </PanelCard>

        <PanelCard v-if="canEdit" title="Новая ставка" description="Ставка ЦБ начинает действовать на следующий рабочий день после решения совета директоров">
          <form class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" novalidate @submit.prevent="add">
            <TextField v-model="form.value" filter="decimal" label="Ставка, % годовых" placeholder="14,00" dense :error="errors.value" required />
            <TextField v-model="form.effectiveFrom" type="date" label="Действует с" dense :error="errors.effectiveFrom" required />
            <TextField v-model="form.decidedOn" type="date" label="Решение совета от" dense hint="Необязательно" :error="errors.decidedOn" />
            <TextField v-model="form.note" label="Комментарий" dense :maxlength="500" placeholder="Пресс-релиз от 23.10" />
            <div class="flex items-center gap-3 sm:col-span-2 xl:col-span-4">
              <BaseButton type="submit" size="s" :loading="saving">Добавить</BaseButton>
              <p v-if="saveError" class="text-sm text-brand" role="alert">{{ saveError }}</p>
            </div>
          </form>
        </PanelCard>
      </div>

      <PanelCard title="История" flush>
        <p v-if="removeError" class="px-5 pb-3 text-sm text-brand" role="alert">{{ removeError }}</p>
        <p v-if="!history.data.value.items.length" class="px-5 pb-5 text-sm text-ink-secondary">
          Ставок ещё не вводили — действует значение из настроек
        </p>
        <div v-else class="overflow-x-auto">
          <table class="w-full min-w-[40rem] text-left text-sm">
            <thead class="text-xs text-ink-secondary">
              <tr class="border-y border-line">
                <th class="px-5 py-3 font-medium">Ставка</th>
                <th class="px-5 py-3 font-medium">Действует с</th>
                <th class="px-5 py-3 font-medium">Решение совета</th>
                <th class="px-5 py-3 font-medium">Кто ввёл</th>
                <th class="px-5 py-3 font-medium">Комментарий</th>
                <th v-if="canEdit" class="w-12 px-5 py-3" />
              </tr>
            </thead>
            <tbody class="divide-y divide-line">
              <tr v-for="item in history.data.value.items" :key="item.effective_from" :class="item.in_force && 'bg-success-soft/40'">
                <td class="px-5 py-3">
                  <span class="font-semibold text-ink tabular-nums">{{ rate(item.value) }}</span>
                  <BaseBadge v-if="item.in_force" tone="success" class="ml-2">действует</BaseBadge>
                  <BaseBadge v-else-if="item.removable" tone="info" class="ml-2">ещё не действует</BaseBadge>
                </td>
                <td class="px-5 py-3 text-ink">{{ formatDate(item.effective_from) }}</td>
                <td class="px-5 py-3 text-ink-secondary">{{ item.decided_on ? formatDate(item.decided_on) : '—' }}</td>
                <td class="px-5 py-3 text-ink-secondary">
                  {{ item.source === 'cbr' ? 'cbr.ru' : 'админка' }}
                  <p v-if="item.created_at" class="text-xs">{{ formatDateTime(item.created_at) }}</p>
                </td>
                <td class="px-5 py-3 text-ink-secondary">{{ item.note ?? '' }}</td>
                <td v-if="canEdit" class="px-5 py-3">
                  <button
                    v-if="item.removable"
                    type="button"
                    class="flex size-8 items-center justify-center rounded-lg text-ink-secondary hover:bg-surface hover:text-brand disabled:opacity-50"
                    :disabled="removing !== null"
                    :aria-label="`Удалить ставку с ${formatDate(item.effective_from)}`"
                    @click="remove(item)"
                  >
                    <Trash2 class="size-4" aria-hidden="true" />
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </PanelCard>
    </div>
  </AsyncState>
</template>
