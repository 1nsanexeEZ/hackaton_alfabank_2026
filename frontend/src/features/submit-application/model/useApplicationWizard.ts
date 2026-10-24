import { computed, reactive, ref, shallowRef, watch } from 'vue'

import {
  APPLICATION_STATUS_META,
  fileProblem,
  loanDraft,
  toClientStatus,
  uploadApplicationDocument,
} from '@/entities/application'
import {
  findProduct,
  hasProductFields,
  isAvailableFor,
  needsCollateral,
  requiredDocumentsFor,
  type ProductCatalog,
} from '@/entities/credit-product'
import { customer, founderPrescreen, personalConsents, prescreenPassed, type CompanyStartupInfo } from '@/entities/customer'
import {
  ApiError,
  clientApi,
  eligibilityMessage,
  type ApplicationDto,
  type ApplicationUpdateInput,
  type CollateralType,
  type DocumentDto,
  type LoanPurpose,
  type OrganizationSummaryDto,
} from '@/shared/api'
import { clamp, errorMessage } from '@/shared/lib'

import { fieldTitle, parseNumber, toFormValues, toPayload, validateFieldValues, type FieldValues } from './productFields'
import { describeViolations, type ViolationView, type WizardStep } from './violations'

export interface CollateralForm {
  type: string
  description: string
  declaredValue: string
  owner: 'self' | 'third_party'
}

export interface DocumentSlot {
  type: string
  title: string
  files: DocumentDto[]
  uploading: boolean
  error: string | null
}

/**
 * Заявка по контракту docs/api/client-journey.md §3.5:
 * черновик (POST /applications) → автосохранение (PATCH с version) → документы → комплектность → submit.
 * Состояние живёт, пока жива модалка: закрыл и открыл снова — продолжаешь с того же места.
 * После перезагрузки страницы черновик находится по 409 duplicate_active и продолжается (resume).
 */
export function useApplicationWizard(products: () => ProductCatalog) {
  const step = ref<WizardStep>('terms')
  const organizations = shallowRef<OrganizationSummaryDto[] | null>(null)
  const organizationsLoading = ref(false)
  const organizationsError = ref<string | null>(null)
  /** Для кого загружены компании: сменился пользователь — начинаем заново */
  let loadedFor: string | null = null

  const terms = reactive({
    organizationId: '',
    productId: '',
    amount: 0,
    termMonths: 0,
    purpose: '' as LoanPurpose | '',
    purposeComment: '',
  })
  const collateral = reactive<CollateralForm>({ type: '', description: '', declaredValue: '', owner: 'self' })
  const productFields = ref<FieldValues>({})
  /**
   * Галочки согласий. Действующие согласия из профиля (ПДн — личное, БКИ — компании) черновик берёт сам
   * (consents.*_source = profile) — тогда галочка уже стоит. automatedDecision — согласие на решение только
   * автоматикой (ст. 16 152-ФЗ): необязательное и важно только у ИП, без него отказ и встречное предложение
   * принимает специалист.
   */
  const consents = reactive({ personalData: false, creditBureau: false, automatedDecision: false })
  /**
   * Личное согласие руководителя по реестру на запрос его кредитной истории (БКИ физлица). Не обязательно:
   * без него банк оценит заявку по данным компании. Даёт только сам руководитель — бухгалтеру видно пояснение.
   */
  const headConsent = reactive({ isHead: false, alreadyGiven: false, validUntil: null as string | null, give: false })

  const application = shallowRef<ApplicationDto | null>(null)
  const busy = ref(false)
  const error = ref<string | null>(null)
  const violations = ref<ViolationView[]>([])
  /** Ошибки полей до отправки на бэкенд — по пути поля, как в нарушениях API */
  const fieldErrors = ref<Record<string, string>>({})
  const uploads = reactive<Record<string, { uploading: boolean; error: string | null }>>({})

  const product = computed(() => findProduct(products(), terms.productId))
  const organization = computed(() => organizations.value?.find((item) => item.id === terms.organizationId) ?? null)
  const legalForm = computed(() => organization.value?.legal_form ?? 'LLC')
  const isEntrepreneur = computed(() => legalForm.value === 'IE')

  // Согласия, которые уже есть в черновике (из профиля или отмеченные раньше), — сразу отмечены
  watch(application, (current) => {
    if (!current || current.status !== 'draft') return
    if (current.consents.personal_data_at) consents.personalData = true
    if (current.consents.credit_bureau_at) consents.creditBureau = true
    if (current.consents.automated_decision_at) consents.automatedDecision = true
  })
  const collateralNeeded = computed(() => needsCollateral(product.value, terms.amount))
  const withFields = computed(() => hasProductFields(product.value))

  /*
   * Подходит ли компания под продукт (форма бизнеса, возраст, выручка) — спрашиваем бэкенд сразу
   * при выборе, чтобы не узнавать об отказе после «Далее». Ответ кешируем по паре компания + продукт.
   */
  const eligibilityByKey = reactive<Record<string, { eligible: boolean; message: string | null }>>({})
  const eligibilityKey = computed(() =>
    terms.organizationId ? `${terms.organizationId}:${product.value.code}` : null,
  )
  /** Почему компания не подходит; null — подходит или проверить не удалось (тогда решит бэкенд при создании) */
  const ineligibleReason = computed(() =>
    eligibilityKey.value ? (eligibilityByKey[eligibilityKey.value]?.message ?? null) : null,
  )

  watch(
    eligibilityKey,
    async (key) => {
      delete fieldErrors.value['request.product']
      if (!key || key in eligibilityByKey) return
      const [organizationId, code] = key.split(':') as [string, string]
      try {
        const result = await clientApi.eligibility(code, organizationId)
        eligibilityByKey[key] = {
          eligible: result.eligible,
          message: result.eligible ? null : eligibilityMessage(result.reasons),
        }
      } catch {
        eligibilityByKey[key] = { eligible: true, message: null }
      }
    },
    { immediate: true },
  )

  /** Стартап или действующий бизнес: стартапу — только продукты для стартапа и сначала проверка учредителя */
  const companyInfo = shallowRef<CompanyStartupInfo | null>(null)
  watch(
    () => terms.organizationId,
    async (organizationId) => {
      companyInfo.value = null
      if (!organizationId) return
      const info = await founderPrescreen.load(organizationId)
      if (organizationId === terms.organizationId) companyInfo.value = info
    },
    { immediate: true },
  )
  const isStartup = computed(() => companyInfo.value?.segment === 'startup')

  /** Продукты, доступные выбранной компании: стартапу — только для стартапа, остальным — без них */
  const allowedProducts = computed(() => {
    const all = products()
    if (!companyInfo.value) return all.filter((item) => !item.startupOnly)
    return all.filter((item) => Boolean(item.startupOnly) === isStartup.value)
  })

  /**
   * Заявку на продукт для стартапа без пройденной проверки учредителя бэкенд отклонит (STOP_FOUNDER_PRESCREEN) —
   * не пускаем дальше «Условий», пока проверка не пройдена
   */
  const startupBlock = computed(() => {
    if (!product.value.startupOnly || !isStartup.value) return null
    const prescreen = founderPrescreen.state[terms.organizationId]?.prescreen
    return prescreenPassed(prescreen) ? null : 'Сначала пройдите проверку учредителя — без неё заявку на запуск бизнеса отклонят'
  })

  watch(
    () => terms.organizationId,
    async (organizationId) => {
      Object.assign(headConsent, { isHead: false, alreadyGiven: false, validUntil: null, give: false })
      if (!organizationId) return
      const [isHead] = await Promise.all([personalConsents.isRegistryHead(organizationId), personalConsents.load()])
      if (organizationId !== terms.organizationId) return
      const current = personalConsents.active('credit_bureau_personal')
      Object.assign(headConsent, { isHead, alreadyGiven: Boolean(current), validUntil: current?.valid_until ?? null })
    },
    { immediate: true },
  )

  const documents = computed<DocumentSlot[]>(() =>
    requiredDocumentsFor(product.value, terms.amount, legalForm.value).map((required) => ({
      type: required.type,
      title: required.title,
      files: (application.value?.documents ?? []).filter(
        (document) => document.type === required.type && document.status === 'uploaded',
      ),
      uploading: uploads[required.type]?.uploading ?? false,
      error: uploads[required.type]?.error ?? null,
    })),
  )

  const hasDetails = computed(() => collateralNeeded.value || withFields.value || documents.value.length > 0)
  const steps = computed<Exclude<WizardStep, 'done'>[]>(() =>
    hasDetails.value ? ['terms', 'details', 'consents'] : ['terms', 'consents'],
  )

  // Новый продукт — свои цели, виды залога и поля анкеты
  watch(
    () => terms.productId,
    () => {
      const current = product.value
      if (!terms.purpose || !current.purposes.includes(terms.purpose)) terms.purpose = current.purposes[0] ?? ''
      if (!current.collateralTypes.includes(collateral.type)) collateral.type = current.collateralTypes[0] ?? ''
      productFields.value = toFormValues(current.fieldsSchema)
      terms.amount = clamp(terms.amount, current.amount.min, current.amount.max)
      terms.termMonths = clamp(terms.termMonths, current.termMonths.min, current.termMonths.max)
    },
  )

  function reset() {
    step.value = 'terms'
    application.value = null
    violations.value = []
    fieldErrors.value = {}
    error.value = null
    consents.personalData = false
    consents.creditBureau = false
    consents.automatedDecision = false
    headConsent.give = false
    Object.assign(collateral, { description: '', declaredValue: '', owner: 'self' })
    terms.purposeComment = ''
    for (const key of Object.keys(uploads)) delete uploads[key]
  }

  async function loadOrganizations() {
    organizationsLoading.value = true
    organizationsError.value = null
    try {
      // Сотрудник банка видит все компании, но не участник ни одной (my_role = null) — подать заявку не может
      const list = (await clientApi.listOrganizations()).filter((item) => item.my_role !== null)
      organizations.value = list
      const preferred = list.find((item) => item.my_permissions.includes('submit_application')) ?? list[0]
      terms.organizationId = takeRequestedOrganization(list) ?? preferred?.id ?? ''
    } catch (caught) {
      organizationsError.value = errorMessage(caught)
    } finally {
      organizationsLoading.value = false
    }
  }

  /** Компания черновика, который клиент продолжает с первого экрана; берём один раз */
  function takeRequestedOrganization(list: OrganizationSummaryDto[]): string | undefined {
    const requested = loanDraft.organizationId
    loanDraft.organizationId = undefined
    return list.some((item) => item.id === requested) ? requested : undefined
  }

  /** Модалка открылась: подхватываем то, что клиент выбрал в каталоге, калькуляторе или на карточке заявки */
  function prepare() {
    const me = customer.state.me?.id ?? null
    if (me !== loadedFor) {
      loadedFor = me
      reset()
      organizations.value = null
    }
    if (step.value === 'done') reset()

    const requested = organizations.value ? takeRequestedOrganization(organizations.value) : undefined
    if (requested && requested !== terms.organizationId) {
      terms.organizationId = requested
      step.value = 'terms'
    }

    const fromSite = findProduct(products(), loanDraft.productId)
    if (step.value === 'terms' || fromSite.id !== terms.productId) {
      step.value = 'terms'
      terms.amount = loanDraft.amount || fromSite.amount.min
      terms.termMonths = loanDraft.termMonths || fromSite.termMonths.min
      if (terms.productId === fromSite.id) {
        terms.amount = clamp(terms.amount, fromSite.amount.min, fromSite.amount.max)
        terms.termMonths = clamp(terms.termMonths, fromSite.termMonths.min, fromSite.termMonths.max)
      }
      terms.productId = fromSite.id
    }
    if (!Object.keys(productFields.value).length) productFields.value = toFormValues(product.value.fieldsSchema)
    // Цель черновика, который продолжают с карточки заявки; берём один раз
    if (loanDraft.purpose && product.value.purposes.includes(loanDraft.purpose)) terms.purpose = loanDraft.purpose
    loanDraft.purpose = undefined
    if (!terms.purpose) terms.purpose = product.value.purposes[0] ?? ''
    if (!collateral.type) collateral.type = product.value.collateralTypes[0] ?? ''
    if (!organizations.value && !organizationsLoading.value) void loadOrganizations()
  }

  function documentTitle(type: string) {
    return product.value.requiredDocuments.find((item) => item.type === type)?.title ?? type
  }

  function showError(caught: unknown) {
    if (caught instanceof ApiError && caught.details.violations?.length) {
      violations.value = describeViolations(caught.details.violations, {
        documentTitle,
        fieldTitle: (path) => fieldTitle(product.value.fieldsSchema, path.replace(/^product_fields\.?/, '')),
      })
      error.value = violations.value.length ? null : caught.message
    } else {
      error.value = errorMessage(caught)
    }
  }

  async function run(action: () => Promise<void>) {
    busy.value = true
    error.value = null
    violations.value = []
    try {
      await action()
    } catch (caught) {
      showError(caught)
    } finally {
      busy.value = false
    }
  }

  /** PATCH с текущей версией; если черновик успели изменить — перечитываем и повторяем один раз */
  async function patch(input: Omit<ApplicationUpdateInput, 'version'>) {
    const current = application.value!
    try {
      application.value = await clientApi.updateApplication(current.id, { ...input, version: current.version })
    } catch (caught) {
      if (!(caught instanceof ApiError && caught.status === 409 && caught.details.code === 'version_conflict')) throw caught
      const fresh = await clientApi.getApplication(current.id)
      application.value = await clientApi.updateApplication(current.id, { ...input, version: fresh.version })
    }
  }

  /** Черновик под выбранные компанию и продукт; сменили их — старый черновик отменяем */
  async function ensureDraft() {
    const current = application.value
    if (
      current?.status === 'draft' &&
      current.organization_id === terms.organizationId &&
      current.product_code === product.value.code
    ) {
      return
    }
    try {
      application.value = await clientApi.createApplication(terms.organizationId, product.value.code)
    } catch (caught) {
      const existingId = duplicateOf(caught)
      if (!existingId) throw caught
      await resume(existingId)
    }
    // Старый черновик отменяем, только когда новый уже есть: иначе при отказе клиент потерял бы оба
    if (current?.status === 'draft') await clientApi.cancelApplication(current.id).catch(() => undefined)
  }

  /** Бэкенд не даёт вторую активную заявку по продукту и отдаёт id той, что уже есть */
  function duplicateOf(caught: unknown): string | null {
    if (!(caught instanceof ApiError) || caught.status !== 409 || caught.details.code !== 'duplicate_active') return null
    return typeof caught.details.application_id === 'string' ? caught.details.application_id : null
  }

  /**
   * Заявка по продукту уже есть. Черновик (например, начатый до перезагрузки страницы) продолжаем:
   * условия перезапишутся тем, что клиент ввёл сейчас, а залог, анкета и документы подтянутся из него.
   * Заявку, которая уже в работе, не трогаем — объясняем, почему новую подать нельзя.
   */
  async function resume(id: string) {
    const existing = await clientApi.getApplication(id)
    if (existing.status !== 'draft') {
      const status = toClientStatus(existing.status, existing.client_stage)
      const state = status ? ` в статусе «${APPLICATION_STATUS_META[status].label}»` : ''
      throw new ApiError(
        409,
        'conflict',
        `По этому продукту у компании уже есть заявка № ${existing.number}${state}. Новую можно подать, когда по ней будет решение`,
      )
    }
    application.value = existing
    if (existing.collateral) {
      Object.assign(collateral, {
        type: existing.collateral.type,
        description: existing.collateral.description,
        declaredValue: String(Number(existing.collateral.declared_value)),
        owner: existing.collateral.owner,
      })
    }
    if (Object.keys(existing.product_fields).length) {
      productFields.value = toFormValues(product.value.fieldsSchema, existing.product_fields)
    }
  }

  function validateStartup(): boolean {
    if (!startupBlock.value) return true
    fieldErrors.value = { ...fieldErrors.value, 'request.product': startupBlock.value }
    return false
  }

  function validateTerms(): boolean {
    const errors: Record<string, string> = {}
    if (!organization.value) errors.organization = 'Выберите компанию'
    else if (!organization.value.my_permissions.includes('submit_application')) {
      errors.organization = 'У вас нет права подавать заявки от этой компании'
    } else if (ineligibleReason.value) {
      errors['request.product'] = ineligibleReason.value
    } else if (!isAvailableFor(product.value, organization.value.legal_form)) {
      errors['request.product'] = 'Продукт недоступен для этой формы бизнеса'
    }
    if (!terms.purpose) errors['request.purpose'] = 'Выберите цель кредита'
    else if (!product.value.purposes.includes(terms.purpose)) {
      errors['request.purpose'] = 'Этот продукт не для такой цели — выберите один из подходящих выше'
    }
    fieldErrors.value = errors
    return Object.keys(errors).length === 0
  }

  async function submitTerms() {
    if (!validateTerms() || !validateStartup()) return
    await run(async () => {
      await ensureDraft()
      await patch({
        request: {
          amount: terms.amount,
          term_months: terms.termMonths,
          purpose: terms.purpose,
          purpose_comment: terms.purposeComment.trim() || null,
        },
      })
      Object.assign(loanDraft, { productId: terms.productId, amount: terms.amount, termMonths: terms.termMonths })
      step.value = hasDetails.value ? 'details' : 'consents'
    })
  }

  function validateDetails(): boolean {
    const errors: Record<string, string> = {}
    if (collateralNeeded.value) {
      if (!collateral.type) errors['collateral.type'] = 'Выберите, что даёте в залог'
      if (!collateral.description.trim()) errors['collateral.description'] = 'Опишите залог'
      const value = parseNumber(collateral.declaredValue)
      if (!(value > 0)) errors['collateral.declared_value'] = 'Укажите стоимость залога'
    }
    if (withFields.value) Object.assign(errors, validateFieldValues(product.value.fieldsSchema, productFields.value))
    for (const slot of documents.value) {
      if (!slot.files.length) errors[`documents.${slot.type}`] = 'Загрузите документ'
    }
    fieldErrors.value = errors
    return Object.keys(errors).length === 0
  }

  async function submitDetails() {
    if (!validateDetails()) return
    await run(async () => {
      const input: Omit<ApplicationUpdateInput, 'version'> = {}
      if (collateralNeeded.value) {
        input.collateral = {
          type: collateral.type as CollateralType,
          description: collateral.description.trim(),
          declared_value: parseNumber(collateral.declaredValue),
          owner: collateral.owner,
        }
      } else if (application.value?.collateral) {
        input.collateral = null
      }
      if (withFields.value) input.product_fields = toPayload(product.value.fieldsSchema, productFields.value)
      if (Object.keys(input).length) await patch(input)
      step.value = 'consents'
    })
  }

  async function submit() {
    const errors: Record<string, string> = {}
    if (!consents.personalData) errors['consents.personal_data'] = 'Без этого согласия заявку не рассмотреть'
    if (!consents.creditBureau) errors['consents.credit_bureau'] = 'Без этого согласия заявку не рассмотреть'
    fieldErrors.value = errors
    if (Object.keys(errors).length) return

    await run(async () => {
      // Уже данные согласия бэкенд не перезаписывает: момент и ссылка на профиль сохраняются
      await patch({
        consents: { personal_data: true, credit_bureau: true, automated_decision: isEntrepreneur.value && consents.automatedDecision },
      })
      // Согласие руководителя — до подачи: проверка данных банком начнётся сразу после неё
      if (headConsent.isHead && !headConsent.alreadyGiven && headConsent.give) {
        await personalConsents.give(['credit_bureau_personal'])
        headConsent.alreadyGiven = true
      }
      const id = application.value!.id
      const check = await clientApi.completeness(id)
      if (!check.complete) {
        throw new ApiError(422, 'validation_error', 'Заявка заполнена не полностью', { violations: check.violations })
      }
      application.value = await clientApi.submitApplication(id)
      step.value = 'done'
    })
  }

  async function uploadDocument(type: string, file: File) {
    const current = application.value
    if (!current) return
    const problem = fileProblem(type, file)
    if (problem) {
      uploads[type] = { uploading: false, error: problem }
      return
    }
    uploads[type] = { uploading: true, error: null }
    try {
      await uploadApplicationDocument(current.id, type, file)
      // Документы меняют версию черновика — перечитываем заявку целиком
      application.value = await clientApi.getApplication(current.id)
      delete uploads[type]
      delete fieldErrors.value[`documents.${type}`]
    } catch (caught) {
      uploads[type] = { uploading: false, error: errorMessage(caught) }
    }
  }

  async function removeDocument(documentId: string) {
    const current = application.value
    if (!current) return
    await run(async () => {
      await clientApi.deleteDocument(current.id, documentId)
      application.value = await clientApi.getApplication(current.id)
    })
  }

  function back() {
    const index = steps.value.indexOf(step.value as Exclude<WizardStep, 'done'>)
    const previous = steps.value[index - 1]
    if (previous) {
      step.value = previous
      error.value = null
      violations.value = []
      fieldErrors.value = {}
    }
  }

  function goTo(target: Exclude<WizardStep, 'done'>) {
    if (steps.value.includes(target)) step.value = target
  }

  return {
    step,
    steps,
    organizations,
    organizationsLoading,
    organizationsError,
    organization,
    terms,
    collateral,
    productFields,
    consents,
    isEntrepreneur,
    headConsent,
    companyInfo,
    isStartup,
    allowedProducts,
    startupBlock,
    application,
    product,
    collateralNeeded,
    withFields,
    ineligibleReason,
    documents,
    busy,
    error,
    violations,
    fieldErrors,
    prepare,
    loadOrganizations,
    submitTerms,
    submitDetails,
    submit,
    uploadDocument,
    removeDocument,
    back,
    goTo,
  }
}

export type ApplicationWizard = ReturnType<typeof useApplicationWizard>
