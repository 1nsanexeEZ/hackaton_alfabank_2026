<script setup lang="ts">
import { AlertTriangle } from 'lucide-vue-next'
import { computed, ref, watch } from 'vue'

import { useProductCatalog } from '@/entities/credit-product'
import { ProcessMap } from '@/entities/process'
import { amlRiskGroup, reviewReasonText, TASK_TYPE_LABEL } from '@/entities/underwriting'
import { TaskDecisionForm } from '@/features/complete-underwriter-task'
import { backofficeApi } from '@/shared/api'
import { formatDate, formatDateTime, formatMoney, formatPercent, formatTerm, useAsyncData } from '@/shared/lib'
import { AsyncState, PanelCard } from '@/shared/ui'

import { usePrelude } from '../model/usePrelude'
import ApplicationPanel from './ApplicationPanel.vue'
import CompanyPanel from './CompanyPanel.vue'
import DecisionPanel from './DecisionPanel.vue'
import ExternalSourcesPanel from './ExternalSourcesPanel.vue'
import ProcessStageDetails from './ProcessStageDetails.vue'
import ProductFitPanel from './ProductFitPanel.vue'
import ScoringPanel from './ScoringPanel.vue'
import StartupProjectPanel from './StartupProjectPanel.vue'
import TaskDeadline from './TaskDeadline.vue'

/**
 * Карточка заявки для андеррайтера (GET /bff/backoffice/applications/{id}): что просит клиент,
 * что ответили внешние источники, как посчитал скоринг и почему движок принял такое решение.
 * Если заявка ждёт специалиста — здесь же задача и форма решения. Сверху — маршрут заявки
 * в реальном времени: продвинулся процесс — карточку перечитываем, чтобы подробности этапов были свежими.
 * Номер заявки отдаём странице (loaded) — он в её заголовке.
 */
const props = defineProps<{ applicationId: string }>()
const emit = defineEmits<{ loaded: [number: string] }>()

const card = useAsyncData(() => backofficeApi.card(props.applicationId))
const data = computed(() => card.data.value)
const processMap = ref<{ refresh: () => Promise<void> } | null>(null)

watch(
  () => data.value?.application.number,
  (number) => number && emit('loaded', number),
  { immediate: true },
)

const { products } = useProductCatalog()
const productTitle = (code: string) => products.value?.find((product) => product.code === code)?.title ?? code

/** Этапы до подачи на схеме маршрута: согласия и предскоринг, у стартапа — проверка учредителя и проектная оценка */
const isStartup = computed(() => Boolean(products.value?.find((product) => product.code === data.value?.application.product_code)?.startupOnly))
const prelude = usePrelude(data, isStartup)
const money = (value: string | null | undefined) => (value === null || value === undefined ? '—' : formatMoney(Number(value)))

/** Решение по задаче процесс применяет асинхронно — перечитываем, пока задача не закроется */
async function refreshAfterDecision() {
  void processMap.value?.refresh()
  for (let attempt = 0; attempt < 8; attempt++) {
    await card.reload()
    const task = card.data.value?.task
    if (!task || task.status === 'done' || task.status === 'cancelled') return
    await new Promise((resolve) => setTimeout(resolve, 1000))
  }
}
</script>

<template>
  <AsyncState :loading="card.loading.value && !data" :error="data ? null : card.error.value" @retry="card.reload">
    <div v-if="data" class="space-y-4">
      <ProcessMap
        ref="processMap"
        :application-id="applicationId"
        :prelude="prelude.stages.value"
        :fallback-workflow="data.application.product_terms.workflow_code ?? null"
        :policy-version="data.decision?.policy_version ?? null"
        @advance="card.reload"
      >
        <template #details="stage">
          <ProcessStageDetails v-bind="stage" :card="data" :pre="prelude.data.value" />
        </template>
        <template v-if="data.timeline.length" #footer>
          <details class="mt-4 text-sm">
            <summary class="cursor-pointer font-medium text-ink-secondary hover:text-ink">Все события заявки ({{ data.timeline.length }})</summary>
            <ol class="relative mt-3 space-y-3 border-l border-line pl-5">
              <li v-for="entry in data.timeline" :key="entry.id" class="relative">
                <span
                  class="absolute top-1.5 -left-[1.625rem] size-2.5 rounded-full ring-4 ring-white"
                  :class="entry.audience === 'bank' ? 'bg-info' : 'bg-ink-muted'"
                  aria-hidden="true"
                />
                <p class="text-sm text-ink">{{ entry.title }}</p>
                <p class="text-xs text-ink-secondary">{{ formatDateTime(entry.at) }} · {{ entry.audience === 'bank' ? 'банк' : 'клиент' }}</p>
              </li>
            </ol>
          </details>
        </template>
      </ProcessMap>

      <div class="grid grid-cols-[minmax(0,1fr)] gap-4 xl:grid-cols-[minmax(0,1fr)_24rem]">
        <!-- Порядок блоков прежний; @container — блоки раскладываются по ширине колонки, а не окна -->
        <div class="@container min-w-0 space-y-4">
          <ApplicationPanel :card="data" :product-title="productTitle(data.application.product_code)" />
          <CompanyPanel v-if="data.application.org_snapshot" :snapshot="data.application.org_snapshot" />
          <ExternalSourcesPanel
            v-if="data.enrichment"
            :enrichment="data.enrichment"
            :snapshot="data.application.org_snapshot"
            :risk-group="amlRiskGroup(data.decision)"
          />
        </div>

        <div class="min-w-0 space-y-4">
          <PanelCard
            v-if="data.task"
            :title="TASK_TYPE_LABEL[data.task.type] ?? 'Задача андеррайтера'"
            :description="data.task.type === 'project_assessment' ? 'Стартап: бизнес-план, финмодель, обеспечение и господдержка' : undefined"
          >
            <p
              v-if="data.task.reason || data.process?.manual_review_reason"
              class="mb-4 flex items-start gap-2 rounded-lg bg-warning-soft p-3 text-sm text-ink"
              role="note"
            >
              <AlertTriangle class="mt-0.5 size-4 shrink-0 text-warning" aria-hidden="true" />
              <span>
                <span class="block font-semibold">Почему задача вернулась</span>
                {{ reviewReasonText(data.task.reason ?? data.process?.manual_review_reason ?? '') }}
              </span>
            </p>
            <TaskDeadline v-if="data.task.due_at && (data.task.status === 'open' || data.task.status === 'in_progress')" :created-at="data.task.created_at" :due-at="data.task.due_at" />
            <TaskDecisionForm :task="data.task" :card="data" @claimed="card.reload" @decided="refreshAfterDecision" />
          </PanelCard>
          <!-- Задачи нет, а причина есть: решение андеррайтера не принято и шаг остановился — видно, почему -->
          <PanelCard v-else-if="data.process?.manual_review_reason" title="Почему заявка у специалиста">
            <p class="flex items-start gap-2 rounded-lg bg-warning-soft p-3 text-sm text-ink" role="note">
              <AlertTriangle class="mt-0.5 size-4 shrink-0 text-warning" aria-hidden="true" />
              {{ reviewReasonText(data.process.manual_review_reason) }}
            </p>
            <p v-if="data.process.status === 'failed'" class="mt-2 text-xs text-ink-secondary">
              Процесс по заявке остановлен, задачи для решения нет — нужен разбор на стороне банка.
            </p>
          </PanelCard>

          <StartupProjectPanel v-if="data.startup" :project="data.startup" />

          <ScoringPanel v-if="data.scoring" :scoring="data.scoring" />
          <DecisionPanel v-if="data.decision" :decision="data.decision" :application="data.application" />
          <ProductFitPanel v-if="data.product_fit" :fit="data.product_fit" />

          <p v-if="data.degraded.length" class="text-xs text-ink-secondary">Часть данных недоступна: {{ data.degraded.join(', ') }}</p>
          <p v-if="data.application.offer" class="text-xs text-ink-secondary">
            Предложение клиенту: {{ money(data.application.offer.amount) }} на {{ formatTerm(data.application.offer.term_months) }} под
            {{ formatPercent(Number(data.application.offer.rate)) }}, до {{ formatDate(data.application.offer.expires_at) }}
          </p>
        </div>
      </div>
    </div>
  </AsyncState>
</template>
