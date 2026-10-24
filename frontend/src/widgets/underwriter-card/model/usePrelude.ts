import { computed, shallowRef, watch, type Ref } from 'vue'

import type { PreludeStage } from '@/entities/process'
import {
  ApiError,
  backofficeApi,
  type BusinessPlanDto,
  type FounderPrescreenDto,
  type OrganizationDetailDto,
  type PreApprovedOfferDto,
  type ProjectAssessmentDto,
  type UnderwriterCardDto,
} from '@/shared/api'
import { formatMoneyShort, pluralize } from '@/shared/lib'

/** Что было с компанией до заявки: сверка с реестром, предодобрения, у стартапа — учредитель, бизнес-план и проект */
export interface PreludeData {
  organization: OrganizationDetailDto | null
  offers: PreApprovedOfferDto[]
  prescreen: FounderPrescreenDto | null
  plan: BusinessPlanDto | null
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
 * Этапы до подачи для схемы маршрута — как на схеме «Путь клиента — как будет» (to-be):
 * согласия → сверка с ЕГРЮЛ → предскоринг → предодобрение по продукту; у стартапа — согласия →
 * проверка учредителя → бизнес-план → проектная оценка → предодобрение по проекту.
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
        const [organization, offers, prescreen, plan, project] = await Promise.all([
          backofficeApi.organization(organizationId).catch(() => null),
          backofficeApi.preApprovedOffers(organizationId).catch(() => []),
          startup ? orNull(backofficeApi.founderPrescreen(organizationId)) : null,
          startup ? orNull(backofficeApi.businessPlan(organizationId)) : null,
          startup ? orNull(backofficeApi.projectAssessment(organizationId)) : null,
        ])
        if (organizationId === card.value?.application.organization_id) data.value = { organization, offers, prescreen, plan, project }
      } catch {
        // Этапы до подачи — подсказка к маршруту: не загрузились — показываем, что знаем по заявке
        data.value = { organization: null, offers: [], prescreen: null, plan: null, project: null }
      }
    },
    { immediate: true },
  )

  const stages = computed<PreludeStage[]>(() => {
    const application = card.value?.application
    if (!application) return []
    const draft = application.status === 'draft'
    /** Шага не было: у черновика он впереди, у поданной заявки — пропущен */
    const notYet = (note: string): Pick<PreludeStage, 'state' | 'note'> => (draft ? { state: 'ahead', note: '' } : { state: 'skipped', note })
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
    const offerStage = (fallback: string | null): PreludeStage => ({
      key: 'pre:offer',
      title: 'Предодобрение',
      subtitle: 'Лимит и ставка «от» по продукту',
      at: null,
      ...(offer
        ? { state: 'done', note: `до ${formatMoneyShort(Number(offer.max_amount))}` }
        : fallback
          ? { state: 'done', note: fallback }
          : notYet('нет по продукту')),
    })

    if (isStartup.value) {
      const prescreen = before?.prescreen ?? null
      const plan = before?.plan ?? null
      const project = before?.project ?? null
      list.push({
        key: 'pre:prescreen',
        title: 'Учредитель',
        subtitle: 'Проверка учредителя по личной кредитной истории',
        at: prescreen?.checked_at ?? null,
        ...(prescreen
          ? prescreen.status === 'passed'
            ? { state: 'done', note: 'пройдена' }
            : { state: 'failed', note: 'не пройдена' }
          : notYet('не было')),
      })
      list.push({
        key: 'pre:plan',
        title: 'Бизнес-план',
        subtitle: 'Финмодель в кабинете компании',
        at: plan?.submitted_at ?? null,
        ...(plan ? { state: 'done', note: `редакция ${plan.revision}` } : notYet('не загружен')),
      })
      list.push({
        key: 'pre:project',
        title: 'Проект',
        subtitle: 'Проектная оценка: DSCR, собственные средства, обеспечение',
        at: project?.checked_at ?? null,
        ...(project
          ? project.status === 'passed'
            ? { state: 'done', note: 'пройдена' }
            : { state: 'failed', note: 'не пройдена' }
          : notYet('не было')),
      })
      // Предодобрение стартапа — по проекту: его сумма, пока банк не выпустил предложение
      const byProject = project?.status === 'passed' && project.max_amount ? `до ${formatMoneyShort(Number(project.max_amount))}` : null
      list.push(offerStage(byProject))
    } else {
      const verification = before?.organization?.verification ?? null
      const status = verification?.status ?? application.org_snapshot?.verification_status ?? 'unverified'
      list.push({
        key: 'pre:registry',
        title: 'Сверка с ЕГРЮЛ',
        subtitle: 'Реквизиты и руководитель — по реестру',
        at: verification?.checked_at ?? null,
        ...(status === 'verified'
          ? { state: 'done', note: 'сверено' }
          : status === 'mismatch'
            ? { state: 'failed', note: 'расхождения' }
            : notYet('не сверяли')),
      })
      const offers = before?.offers.length ?? 0
      list.push({
        key: 'pre:prescoring',
        title: 'Предскоринг',
        subtitle: 'Стоп-факторы и модели на данных банка',
        at: null,
        ...(offers
          ? { state: 'done', note: `${offers} ${pluralize(offers, ['предложение', 'предложения', 'предложений'])}` }
          : notYet('без предодобрения')),
      })
      list.push(offerStage(null))
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
