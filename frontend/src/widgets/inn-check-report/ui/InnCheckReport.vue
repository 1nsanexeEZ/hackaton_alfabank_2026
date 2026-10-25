<script setup lang="ts">
import { CircleAlert, CircleCheck, CircleDashed, CircleX, SearchX } from 'lucide-vue-next'
import { computed, ref, watch, type Component } from 'vue'

import { LEGAL_FORM_LABEL } from '@/entities/credit-product'
import { label, REGISTRY_STATUS_LABEL, RELIABILITY, UNRELIABLE_LABEL } from '@/entities/underwriting'
import type { InnCheckDto, InnCheckSource, InnCheckStatus, InnCheckVerdict } from '@/shared/api'
import { formatDate, formatDateTime, formatMoney } from '@/shared/lib'
import { BaseBadge, BaseButton, PanelCard } from '@/shared/ui'

/**
 * Итог проверки компании по ИНН до заявки: вердикт с текстом бэкенда, несовпадение с реквизитами
 * из документов клиента, проверки по источникам и что ответили ЕГРЮЛ / ЕГРИП, ФНС и Контур
 */
const props = defineProps<{ result: InnCheckDto }>()

const VERDICT_TONE: Record<InnCheckVerdict, { tone: string; icon: Component }> = {
  ok: { tone: 'bg-success-soft text-success', icon: CircleCheck },
  warning: { tone: 'bg-warning-soft text-warning', icon: CircleAlert },
  fail: { tone: 'bg-brand-soft text-brand', icon: CircleX },
  not_found: { tone: 'bg-surface text-ink', icon: SearchX },
}

const CHECK: Record<InnCheckStatus, { icon: Component; tone: string }> = {
  passed: { icon: CircleCheck, tone: 'text-success' },
  warning: { icon: CircleAlert, tone: 'text-warning' },
  failed: { icon: CircleX, tone: 'text-brand' },
  skipped: { icon: CircleDashed, tone: 'text-ink-muted' },
}

const SOURCE_TITLE: Record<InnCheckSource, string> = {
  input: 'Сверка с документами',
  egrul: 'ЕГРЮЛ / ЕГРИП',
  fns: 'ФНС',
  kontur: 'Контур',
  bank: 'Банк',
}
const SOURCES: readonly InnCheckSource[] = ['input', 'egrul', 'fns', 'kontur', 'bank']

/** Реквизиты из документов клиента, с которыми ИНН не сошёлся */
const MATCH_CODES = ['ogrn_match', 'kpp_match', 'name_match']
const mismatches = computed(() => props.result.checks.filter((check) => MATCH_CODES.includes(check.code) && check.status !== 'passed'))

/** Есть замечания — пройденные проверки свёрнуты, чтобы сразу было видно, что не так */
const showPassed = ref(false)
watch(
  () => props.result,
  (result) => (showPassed.value = result.checks.every((check) => check.status === 'passed')),
  { immediate: true },
)
const passedCount = computed(() => props.result.checks.filter((check) => check.status === 'passed').length)

const groups = computed(() =>
  SOURCES.map((source) => ({
    source,
    checks: props.result.checks.filter((check) => check.source === source && (showPassed.value || check.status !== 'passed')),
  })).filter((group) => group.checks.length),
)

/** Ошибка в контрольной цифре: источники не спрашивали, единственная проверка — inn_checksum */
const typo = computed(() => props.result.verdict === 'fail' && !props.result.company)
const checkTitle = (check: InnCheckDto['checks'][number]) =>
  check.code === 'bank_client' && check.status === 'warning' ? 'Карточка клиента расходится с реестром' : check.title

const money = (value: string | null) => (value === null ? '—' : formatMoney(Number(value)))
</script>

<template>
  <div class="space-y-6">
    <div class="flex items-start gap-3 rounded-2xl p-4" :class="VERDICT_TONE[result.verdict].tone" role="status">
      <component :is="VERDICT_TONE[result.verdict].icon" class="mt-0.5 size-6 shrink-0" aria-hidden="true" />
      <div class="min-w-0 flex-1">
        <p class="font-semibold">
          <template v-if="result.verdict === 'not_found'">ИНН {{ result.inn }} не найден</template>
          <template v-else-if="typo">В ИНН ошибка — проверьте номер</template>
          <template v-else>{{ result.summary }}</template>
        </p>
        <p class="mt-0.5 text-sm text-ink">
          <template v-if="result.verdict === 'not_found'">В ЕГРЮЛ и ЕГРИП такого ИНН нет. Проверьте номер или запросите документы у клиента.</template>
          <template v-else-if="typo">{{ result.inn }}: контрольная цифра не сходится, источники не запрашивали.</template>
          <template v-else>ИНН {{ result.inn }}{{ result.company ? ` · ${result.company.name}` : '' }}</template>
        </p>
        <p class="mt-1 text-xs text-ink-secondary">Проверено {{ formatDateTime(result.checked_at) }}</p>
      </div>
      <BaseBadge v-if="result.organization_id" tone="info" class="shrink-0">Клиент банка</BaseBadge>
    </div>

    <div v-if="mismatches.length" class="rounded-2xl bg-brand-soft p-4 text-sm" role="alert">
      <p class="font-semibold text-brand">ИНН не сходится с реквизитами из документов</p>
      <ul class="mt-1 space-y-0.5 text-ink">
        <li v-for="check in mismatches" :key="check.code">{{ check.title }}: {{ check.message }}</li>
      </ul>
    </div>

    <PanelCard v-if="result.company" title="Проверки" :description="`${result.checks.length} по источникам, пройдено ${passedCount}`">
      <template v-if="passedCount && passedCount < result.checks.length" #actions>
        <BaseButton size="s" variant="ghost" @click="showPassed = !showPassed">
          {{ showPassed ? 'Только замечания' : `Показать пройденные (${passedCount})` }}
        </BaseButton>
      </template>
      <div class="space-y-5">
        <section v-for="group in groups" :key="group.source">
          <p class="text-xs font-semibold tracking-wide text-ink-secondary uppercase">{{ SOURCE_TITLE[group.source] }}</p>
          <ul class="mt-2 divide-y divide-line">
            <li v-for="check in group.checks" :key="check.code" class="flex items-start gap-3 py-2 first:pt-0 last:pb-0">
              <component :is="CHECK[check.status].icon" class="mt-0.5 size-5 shrink-0" :class="CHECK[check.status].tone" aria-hidden="true" />
              <div class="min-w-0 text-sm">
                <p class="font-medium text-ink">{{ checkTitle(check) }}</p>
                <p class="text-ink-secondary">{{ check.message }}</p>
              </div>
            </li>
          </ul>
        </section>
      </div>
    </PanelCard>

    <div v-if="result.company" class="grid items-start gap-6 xl:grid-cols-2">
      <PanelCard title="ЕГРЮЛ / ЕГРИП" class="xl:row-span-2">
        <dl class="space-y-3 text-sm">
          <div>
            <dt class="text-ink-secondary">Наименование</dt>
            <dd class="text-ink">{{ result.company.name }}</dd>
            <dd class="text-xs text-ink-secondary">{{ result.company.full_name }} · {{ LEGAL_FORM_LABEL[result.company.legal_form] }}</dd>
          </div>
          <div>
            <dt class="text-ink-secondary">ИНН · ОГРН{{ result.company.kpp ? ' · КПП' : '' }}</dt>
            <dd class="text-ink tabular-nums">
              {{ result.company.inn }} · {{ result.company.ogrn }}{{ result.company.kpp ? ` · ${result.company.kpp}` : '' }}
            </dd>
          </div>
          <div>
            <dt class="text-ink-secondary">Статус</dt>
            <dd :class="result.company.registry_status === 'active' ? 'text-ink' : 'text-brand'">
              {{ REGISTRY_STATUS_LABEL[result.company.registry_status] ?? result.company.registry_status }}, регистрация
              {{ formatDate(result.company.registered_at) }}
            </dd>
          </div>
          <div>
            <dt class="text-ink-secondary">Адрес</dt>
            <dd :class="result.company.mass_address ? 'text-brand' : 'text-ink'">
              {{ result.company.address.full }}{{ result.company.mass_address ? ' — массовый' : '' }}
            </dd>
          </div>
          <div>
            <dt class="text-ink-secondary">ОКВЭД</dt>
            <dd class="text-ink">
              {{ result.company.okved_main
              }}<span v-if="result.company.okved_extra.length" class="text-ink-secondary"> · ещё {{ result.company.okved_extra.join(', ') }}</span>
            </dd>
          </div>
          <div>
            <dt class="text-ink-secondary">Руководитель</dt>
            <dd class="text-ink">
              {{ result.company.head_name }}, {{ result.company.head_position
              }}{{ result.company.head_since ? `, в реестре с ${formatDate(result.company.head_since)}` : '' }}
            </dd>
          </div>
          <div v-if="result.company.founders.length">
            <dt class="text-ink-secondary">Учредители</dt>
            <dd v-for="founder in result.company.founders" :key="founder.name" class="text-ink">
              {{ founder.name }}{{ founder.inn ? `, ИНН ${founder.inn}` : '' }} — {{ Number(founder.share_percent) }}%
            </dd>
          </div>
          <div v-if="result.company.unreliable.length">
            <dt class="text-ink-secondary">Отметки о недостоверности</dt>
            <dd class="text-brand">{{ result.company.unreliable.map((item) => label(UNRELIABLE_LABEL, item)).join(', ') }}</dd>
          </div>
        </dl>
      </PanelCard>

      <PanelCard title="ФНС">
        <dl v-if="result.tax" class="grid gap-x-6 gap-y-3 text-sm sm:grid-cols-2">
          <div>
            <dt class="text-ink-secondary">Режим и численность</dt>
            <dd class="text-ink">{{ result.tax.tax_regime }} · {{ result.tax.avg_headcount }} чел.</dd>
          </div>
          <div>
            <dt class="text-ink-secondary">Выручка{{ result.tax.report_year ? ` за ${result.tax.report_year}` : '' }}</dt>
            <dd class="text-ink">{{ money(result.tax.reported_revenue) }}</dd>
          </div>
          <div>
            <dt class="text-ink-secondary">Недоимка</dt>
            <dd :class="Number(result.tax.tax_arrears) > 0 ? 'text-warning' : 'text-ink'">{{ money(result.tax.tax_arrears) }}</dd>
          </div>
          <div>
            <dt class="text-ink-secondary">Реестр МСП</dt>
            <dd class="text-ink">{{ result.tax.in_msp_registry ? 'есть' : 'нет' }}</dd>
          </div>
          <p v-if="result.tax.disqualified_head || result.tax.mass_head" class="text-brand sm:col-span-2">
            {{ [result.tax.disqualified_head && 'Руководитель дисквалифицирован', result.tax.mass_head && 'массовый руководитель'].filter(Boolean).join(', ') }}
          </p>
          <div class="sm:col-span-2">
            <dt class="text-ink-secondary">Блокировки счетов</dt>
            <dd v-if="!result.tax.account_blocks.length" class="text-ink">нет</dd>
            <dd v-for="block in result.tax.account_blocks" :key="block.decision_number" class="text-brand">
              № {{ block.decision_number }} от {{ formatDate(block.date) }} — {{ block.reason }}
            </dd>
          </div>
        </dl>
        <p v-else class="text-sm text-ink-secondary">ФНС не ответила — эти проверки не выполнены.</p>
      </PanelCard>

      <PanelCard title="Контур">
        <template v-if="result.counterparty" #actions>
          <BaseBadge :tone="RELIABILITY[result.counterparty.reliability]?.tone ?? 'neutral'">
            {{ RELIABILITY[result.counterparty.reliability]?.label ?? result.counterparty.reliability }}
          </BaseBadge>
        </template>
        <ul v-if="result.counterparty" class="space-y-1 text-sm text-ink">
          <li :class="result.counterparty.arbitration_as_defendant > 0 && 'text-warning'">
            Иски к компании: {{ result.counterparty.arbitration_as_defendant }} на {{ money(result.counterparty.arbitration_defendant_sum) }}
          </li>
          <li :class="result.counterparty.enforcement_active > 0 && 'text-warning'">
            Исполнительные производства: {{ result.counterparty.enforcement_active }} на {{ money(result.counterparty.enforcement_sum) }}
          </li>
          <li v-if="!result.counterparty.bankruptcy_messages.length">Сообщений о банкротстве нет</li>
          <li v-for="message in result.counterparty.bankruptcy_messages" :key="message.case" class="text-brand">
            {{ message.type }} — дело {{ message.case }} от {{ formatDate(message.date) }}
          </li>
          <li v-for="note in result.counterparty.notes" :key="note" class="text-xs text-ink-secondary">{{ note }}</li>
        </ul>
        <p v-else class="text-sm text-ink-secondary">Контур не ответил — суды, приставы и банкротство не проверены.</p>
      </PanelCard>
    </div>
  </div>
</template>
