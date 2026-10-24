import { computed, shallowRef, watch, type Ref } from 'vue'

import type { PreludeStage } from '@/entities/process'
import {
  ApiError,
  backofficeApi,
  type FounderPrescreenDto,
  type PreApprovedOfferDto,
  type ProjectAssessmentDto,
  type UnderwriterCardDto,
} from '@/shared/api'
import { formatMoneyShort } from '@/shared/lib'

/** Что было с компанией до заявки: предодобрение, у стартапа — проверка учредителя и проектная оценка */
export interface PreludeData {
  offers: PreApprovedOfferDto[]
  prescreen: FounderPrescreenDto | null
  project: ProjectAssessmentDto | null
}

/** 404 — шага не было */
const orNull = <T>(request: Promise<T>) =>
  request.catch((caught) => {
    if (caught instanceof ApiError && caught.status === 404) return null
    throw caught
  })

const latest = (...dates: (string | null | undefined)[]) =>
  dates.filter((date): date is string => Boolean(date)).sort().at(-1) ?? null

/**
 * Этапы до подачи для схемы маршрута — как на общей схеме банка: согласия → предскоринг (сверка с
 * ЕГРЮЛ и предодобрение по продукту); у стартапа — согласия → проверка учредителя → проектная оценка.
 * У черновика клиент сейчас на первом незавершённом из них (или на последнем, если всё пройдено:
 * выбирает условия); у поданной заявки — пройдены или не было.
 */
export function usePrelude(card: Ref<UnderwriterCardDto | null>, isStartup: Ref<boolean>) {
  const data = shallowRef<PreludeData | null>(null)

  // Источники по отдельности: перечитанная карточка с той же компанией не перезагружает данные
  watch(
    [() => card.value?.application.organization_id, isStartup],
    async ([organizationId, startup]) => {
      data.value = null
      if (!organizationId) return
      try {
        const [offers, prescreen, project] = await Promise.all([
          backofficeApi.preApprovedOffers(organizationId).catch(() => []),
          startup ? orNull(backofficeApi.founderPrescreen(organizationId)) : null,
          startup ? orNull(backofficeApi.projectAssessment(organizationId)) : null,
        ])
        if (organizationId === card.value?.application.organization_id) data.value = { offers, prescreen, project }
      } catch {
        // Этапы до подачи — подсказка к маршруту: не загрузились — показываем, что знаем по заявке
        data.value = { offers: [], prescreen: null, project: null }
      }
    },
    { immediate: true },
  )

  const stages = computed<PreludeStage[]>(() => {
    const application = card.value?.application
    if (!application) return []
    const draft = application.status === 'draft'
    const consents = application.consents
    const consentsGiven = Boolean(consents?.personal_data_at && consents?.credit_bureau_at)
    const fromProfile = consents?.personal_data_source === 'profile' || consents?.credit_bureau_source === 'profile'

    const list: PreludeStage[] = [
      {
        key: 'pre:consents',
        title: 'Согласия',
        subtitle: 'Обработка ПДн и запрос в БКИ',
        state: consentsGiven || !draft ? 'done' : 'current',
        at: latest(consents?.personal_data_at, consents?.credit_bureau_at),
        note: consentsGiven ? (fromProfile ? 'из профиля' : 'в заявке') : draft ? 'ещё не даны' : '',
      },
    ]
    const before = data.value
    const offer = before?.offers.find((item) => item.product_code === application.product_code) ?? null

    if (isStartup.value) {
      const prescreen = before?.prescreen ?? null
      const project = before?.project ?? null
      const prescreenOk = prescreen?.status === 'passed'
      list.push({
        key: 'pre:prescreen',
        title: 'Учредитель',
        subtitle: 'Проверка учредителя по личной кредитной истории',
        state: prescreen ? (prescreenOk ? 'done' : 'failed') : draft ? 'ahead' : 'skipped',
        at: prescreen?.checked_at ?? null,
        note: prescreen ? (prescreenOk ? 'пройдена' : 'не пройдена') : draft ? '' : 'не было',
      })
      list.push({
        key: 'pre:project',
        title: 'Проект',
        subtitle: 'Проектная оценка по бизнес-плану и финмодели',
        state: project ? (project.status === 'passed' ? 'done' : 'failed') : draft ? 'ahead' : 'skipped',
        at: project?.checked_at ?? null,
        note: project
          ? project.status === 'passed' && project.max_amount
            ? `до ${formatMoneyShort(Number(project.max_amount))}`
            : 'не пройдена'
          : draft
            ? ''
            : 'не было',
      })
    } else {
      list.push({
        key: 'pre:prescoring',
        title: 'Предскоринг',
        subtitle: 'Сверка с ЕГРЮЛ и предодобрение по продукту',
        state: offer ? 'done' : draft ? 'ahead' : 'skipped',
        at: null,
        note: offer
          ? `до ${formatMoneyShort(Number(offer.max_amount))}`
          : application.org_snapshot && application.org_snapshot.verification_status !== 'verified'
            ? 'нет сверки'
            : 'без предодобрения',
      })
    }

    // Черновик: клиент на первом незавершённом этапе после согласий, а всё пройдено — на последнем.
    // Что после него — впереди, даже если банк уже посчитал (предодобрение есть и без согласий)
    if (draft) {
      const current = consentsGiven ? (list.slice(1).find((item) => item.state !== 'done') ?? list.at(-1)!) : list[0]!
      current.state = 'current'
      for (const item of list.slice(list.indexOf(current) + 1)) item.state = 'ahead'
    }
    return list
  })

  return { stages, data }
}
