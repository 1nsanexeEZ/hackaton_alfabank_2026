<script setup lang="ts">
import { computed, ref } from 'vue'

import { getAt, pathKey, setAt } from '@/entities/scoring-version'
import type { PolicyCatalogDto, VersionBody } from '@/shared/api'

/**
 * Тексты причин для клиента в черновике политики: reason_texts — код → { text, hint } поверх текстов
 * по умолчанию из каталога. Пустой текст — своего нет, клиент видит текст по умолчанию; ключ из документа
 * убираем, чтобы версия не тащила копии стандартных текстов.
 */
const props = defineProps<{
  body: VersionBody
  catalog: PolicyCatalogDto | null
  errors: Record<string, string>
  readonly: boolean
}>()

type ReasonText = { text: string; hint?: string | null }

const own = computed(() => (getAt(props.body, ['reason_texts']) as Record<string, ReasonText> | null | undefined) ?? {})
const changed = computed(() => Object.keys(own.value).length)

const query = ref('')
const reasons = computed(() => {
  const needle = query.value.trim().toLowerCase()
  const list = props.catalog?.reasons ?? []
  return needle ? list.filter((item) => `${item.code} ${item.text}`.toLowerCase().includes(needle)) : list
})

function update(code: string, field: 'text' | 'hint', value: string) {
  if (props.readonly) return
  const texts = { ...own.value }
  const current = { text: texts[code]?.text ?? '', hint: texts[code]?.hint ?? null }
  const next = { ...current, [field]: field === 'hint' ? value.trim() || null : value }
  // Без своего текста подсказка одна не живёт: бэкенду нужен text, а пустая пара — значит «по умолчанию»
  if (!next.text.trim()) delete texts[code]
  else texts[code] = next.hint ? { text: next.text, hint: next.hint } : { text: next.text }
  setAt(props.body, ['reason_texts'], Object.keys(texts).length ? texts : null)
}

const errorOf = (code: string, field: 'text' | 'hint') => props.errors[pathKey(['reason_texts', code, field])] ?? props.errors[pathKey(['reason_texts', code])]
</script>

<template>
  <details class="group rounded-xl ring-1 ring-line">
    <summary class="flex cursor-pointer items-center justify-between gap-3 px-4 py-3 text-sm font-semibold text-ink">
      Тексты причин для клиента
      <span class="text-xs font-normal text-ink-secondary">
        {{ changed ? `своих — ${changed}` : 'все по умолчанию' }}
      </span>
    </summary>
    <div class="space-y-3 border-t border-line p-4">
      <p class="text-xs text-ink-secondary">
        Что клиент увидит в решении и что ему сделать. Пустое поле — текст по умолчанию из каталога. Текст — до 500 знаков.
      </p>
      <input
        v-model="query"
        type="search"
        placeholder="Найти код или текст"
        aria-label="Найти причину"
        class="h-9 w-full max-w-xs rounded-lg bg-surface px-3 text-sm text-ink outline-none focus:bg-surface-strong"
      />
      <p v-if="errors[pathKey(['reason_texts'])]" class="text-xs text-brand">{{ errors[pathKey(['reason_texts'])] }}</p>
      <p v-if="!catalog" class="text-sm text-ink-secondary">Каталог причин не загрузился — тексты можно править во вкладке JSON</p>
      <ul v-else class="divide-y divide-line">
        <li v-for="reason in reasons" :key="reason.code" class="grid gap-2 py-3 lg:grid-cols-[minmax(0,14rem)_minmax(0,1fr)]">
          <div class="min-w-0">
            <code class="text-xs break-all text-ink">{{ reason.code }}</code>
            <p class="mt-1 text-xs text-ink-secondary">{{ reason.text }}</p>
          </div>
          <div class="grid gap-2 sm:grid-cols-2">
            <label class="block">
              <span class="sr-only">Свой текст для {{ reason.code }}</span>
              <textarea
                :value="own[reason.code]?.text ?? ''"
                :placeholder="reason.text"
                :readonly="readonly"
                :aria-invalid="errorOf(reason.code, 'text') ? 'true' : undefined"
                maxlength="500"
                rows="2"
                class="w-full resize-y rounded-lg bg-surface px-3 py-2 text-sm text-ink outline-none placeholder:text-ink-muted focus:bg-surface-strong"
                @change="update(reason.code, 'text', ($event.target as HTMLTextAreaElement).value)"
              />
              <span v-if="errorOf(reason.code, 'text')" class="text-xs text-brand">{{ errorOf(reason.code, 'text') }}</span>
            </label>
            <label class="block">
              <span class="sr-only">Своя подсказка для {{ reason.code }}</span>
              <textarea
                :value="own[reason.code]?.hint ?? ''"
                :placeholder="reason.hint ?? 'Подсказка: что клиенту сделать'"
                :readonly="readonly || !own[reason.code]"
                :title="own[reason.code] ? undefined : 'Сначала задайте свой текст'"
                maxlength="500"
                rows="2"
                class="w-full resize-y rounded-lg bg-surface px-3 py-2 text-sm text-ink outline-none placeholder:text-ink-muted focus:bg-surface-strong disabled:opacity-60"
                @change="update(reason.code, 'hint', ($event.target as HTMLTextAreaElement).value)"
              />
            </label>
          </div>
        </li>
        <li v-if="!reasons.length" class="py-3 text-sm text-ink-secondary">Ничего не нашлось</li>
      </ul>
    </div>
  </details>
</template>
