<script setup lang="ts">
import { Download } from 'lucide-vue-next'

import { saveFile } from '@/shared/lib'

import { STATEMENT_COLUMNS, STATEMENT_SAMPLE } from '../model/statement'

/** Что загружать как выписку по счёту: колонки, разделитель, пример и образец файла */
function downloadSample() {
  saveFile(new Blob([STATEMENT_SAMPLE], { type: 'text/csv;charset=utf-8' }), 'vypiska-obrazec.csv')
}
</script>

<template>
  <details class="mt-2 text-xs text-ink-secondary">
    <summary class="cursor-pointer font-medium text-ink-secondary hover:text-ink">Формат выписки</summary>
    <div class="mt-2 space-y-2">
      <p>
        CSV в кодировке UTF-8, колонки через точку с запятой «;», первая строка — названия колонок. Лучше за 6–12 месяцев; можно
        несколько файлов.
      </p>
      <ul class="space-y-0.5">
        <li v-for="column in STATEMENT_COLUMNS" :key="column.name">
          <code class="text-ink">{{ column.name }}</code>{{ column.required ? '' : ' (необязательно)' }} — {{ column.format }}
        </li>
      </ul>
      <pre class="overflow-x-auto rounded-lg bg-white p-2 text-[11px] leading-relaxed text-ink ring-1 ring-line">{{ STATEMENT_SAMPLE }}</pre>
      <button type="button" class="inline-flex items-center gap-1 font-medium text-brand hover:underline" @click="downloadSample">
        <Download class="size-3.5" aria-hidden="true" />
        Скачать образец
      </button>
    </div>
  </details>
</template>
