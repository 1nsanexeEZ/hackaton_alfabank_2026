import { computed, onBeforeUnmount, ref, shallowRef, watch } from 'vue'

import { fileProblem, myApplications, STATEMENT_TYPE, statementProblem, uploadApplicationDocument } from '@/entities/application'
import { liveFeed } from '@/entities/notification'
import {
  ApiError,
  clientApi,
  type ApplicationDto,
  type ClientApplicationCardDto,
  type ContractDto,
  type EsignRulesDto,
} from '@/shared/api'
import { errorMessage, saveFile } from '@/shared/lib'

/** Пока банк думает, без живого потока перечитываем карточку сами */
const POLL_MS = 5_000
const PROCESSING = new Set(['submitted', 'in_review'])
/** С этих клиентских статусов у заявки есть договор */
const WITH_CONTRACT = new Set(['signing', 'issued'])
/** PDF договора бэкенд собирает за 1–3 секунды: опрашиваем чаще, но не дольше минуты */
const DOCUMENT_POLL_MS = 2_000
const DOCUMENT_WAIT_MS = 60_000

/** Ответы API — простой JSON, сравнить его строкой дешевле, чем перерисовать карточку с графиком */
function sameData(previous: unknown, next: unknown): boolean {
  return previous === next || JSON.stringify(previous) === JSON.stringify(next)
}

/** Бэкенд с PDF договора: у старого поля document в ответе нет вовсе */
export function hasContractDocument(contract: ContractDto | null): contract is ContractDto {
  return Boolean(contract && 'document' in contract)
}

/**
 * Ждём ли PDF: проект ещё не начали или формируют, а после подписи клиента — итоговый с подписью банка.
 * Сбой (failed) не ждём — его показываем с кнопкой «Обновить».
 */
function documentWaiting(contract: ContractDto | null): boolean {
  if (!hasContractDocument(contract)) return false
  const document = contract.document
  if (document?.status === 'failed') return false
  if (contract.status === 'unsigned') return !document || document.status === 'pending'
  return !(document?.kind === 'signed' && document.status === 'ready')
}

/**
 * Карточка заявки клиента (GET /bff/applications/{id}) и действия по ней.
 * Кнопки — только из available_actions: бэкенд уже учёл статус и права в компании.
 * Обновляется сама: по событию SSE `application_updated`, а без потока — опросом, пока заявка в работе.
 */
export function useApplicationCard(applicationId: () => string | null) {
  const card = shallowRef<ClientApplicationCardDto | null>(null)
  /** Полная заявка — ради выдачи (disbursement), её нет в карточке BFF */
  const details = shallowRef<ApplicationDto | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)
  /** Какое действие выполняется: accept, decline, sign, answer, cancel, upload:<type> */
  const busy = ref<string | null>(null)
  const actionError = ref<string | null>(null)
  /** Код ошибки действия (details.code): по нему окно показывает ошибку рядом с полем, а не общим текстом */
  const actionErrorCode = ref<string | null>(null)
  const uploadErrors = ref<Record<string, string>>({})
  const signature = shallowRef<{ signed_at: string; edo_document_id: string; simulated: boolean } | null>(null)
  /** Договор: на подписи — что клиент подписывает (и его offer_hash), после — что подписано */
  const contract = shallowRef<ContractDto | null>(null)
  const contractError = ref<string | null>(null)
  /** PDF формируется дольше минуты — перестаём опрашивать и просим нажать «Обновить» */
  const documentSlow = ref(false)
  /** Правила электронного взаимодействия: их редакцию клиент принимает перед подписью */
  const rules = shallowRef<EsignRulesDto | null>(null)
  const rulesError = ref<string | null>(null)

  let requestId = 0

  async function load(quiet = false) {
    const id = applicationId()
    if (!id) return
    const current = ++requestId
    if (!quiet) loading.value = true
    try {
      const next = await clientApi.getApplicationCard(id)
      // Полная заявка нужна выданному кредиту (номер выдачи) и черновику: BFF фиксирует компанию только при подаче
      const full = next.client_status === 'issued' || next.client_status === 'draft' ? await clientApi.getApplication(id) : null
      const nextContract = WITH_CONTRACT.has(next.client_status) ? await loadContract(id) : null
      if (full && !next.organization) {
        const name =
          myApplications.state.items?.find((item) => item.id === id)?.organization_name ??
          (await clientApi.listOrganizations()).find((item) => item.id === full.organization_id)?.name
        next.organization = { id: full.organization_id, name: name ?? 'Компания', inn: '' }
      }
      if (current !== requestId) return
      // Те же данные — тот же объект: опрос и события ленты не перерисовывают договор и график зря
      if (!sameData(card.value, next)) card.value = next
      if (!sameData(details.value, full)) details.value = full
      if (!sameData(contract.value, nextContract)) contract.value = nextContract
      error.value = null
    } catch (caught) {
      if (current === requestId && !quiet) error.value = errorMessage(caught)
    } finally {
      if (current === requestId) loading.value = false
    }
  }

  async function loadContract(id: string) {
    try {
      const value = await clientApi.contract(id)
      contractError.value = null
      return value
    } catch (caught) {
      contractError.value = errorMessage(caught)
      return null
    }
  }

  watch(
    applicationId,
    (id) => {
      card.value = null
      details.value = null
      contract.value = null
      contractError.value = null
      signature.value = null
      actionError.value = null
      uploadErrors.value = {}
      documentSlow.value = false
      if (id) void load()
    },
    { immediate: true },
  )

  const stopLive = liveFeed.onApplication((update) => {
    if (update.application_id === applicationId()) void load(true)
  })

  const timer = setInterval(() => {
    if (card.value && PROCESSING.has(card.value.status) && !liveFeed.state.connected) void load(true)
  }, POLL_MS)

  /*
   * Опрос PDF: каждые 2 секунды, пока документ формируется, но не дольше минуты от начала ожидания.
   * Лента тоже пришлёт «Договор сформирован», но ждать её не обязательно — опрос дешёвый и короткий.
   */
  let documentTimer: ReturnType<typeof setInterval> | undefined
  function stopDocumentPolling() {
    clearInterval(documentTimer)
    documentTimer = undefined
  }
  function startDocumentPolling() {
    stopDocumentPolling()
    documentSlow.value = false
    const startedAt = Date.now()
    documentTimer = setInterval(() => {
      if (Date.now() - startedAt >= DOCUMENT_WAIT_MS) {
        stopDocumentPolling()
        documentSlow.value = true
        return
      }
      void load(true)
    }, DOCUMENT_POLL_MS)
  }
  const waitingDocument = computed(() => documentWaiting(contract.value))
  watch(waitingDocument, (waiting) => (waiting ? startDocumentPolling() : stopDocumentPolling()), { immediate: true })

  /** «Обновить»: перечитать договор и, если он всё ещё формируется, ждать ещё минуту */
  async function refreshDocument() {
    await load(true)
    if (waitingDocument.value) startDocumentPolling()
  }

  async function loadRules() {
    try {
      rules.value = await clientApi.esignRules()
      rulesError.value = null
    } catch (caught) {
      rulesError.value = errorMessage(caught)
    }
  }

  // Правила нужны только перед подписью и только бэкенду с PDF; загружаем один раз
  watch(contract, (value) => {
    if (hasContractDocument(value) && value.status === 'unsigned' && !rules.value) void loadRules()
  })

  onBeforeUnmount(() => {
    stopLive()
    clearInterval(timer)
    stopDocumentPolling()
  })

  const can = (action: string) => card.value?.available_actions.includes(action) ?? false

  async function run(name: string, action: (id: string) => Promise<unknown>) {
    const id = applicationId()
    if (!id) return false
    busy.value = name
    actionError.value = null
    actionErrorCode.value = null
    try {
      await action(id)
      await load(true)
      void myApplications.refresh()
      return true
    } catch (caught) {
      actionError.value = errorMessage(caught)
      actionErrorCode.value = caught instanceof ApiError ? (caught.details.code ?? caught.code) : null
      return false
    } finally {
      busy.value = null
    }
  }

  const accept = () => run('accept', (id) => clientApi.acceptOffer(id))
  const decline = (reason: string) => run('decline', (id) => clientApi.declineOffer(id, reason.trim() || undefined))
  const cancel = (reason: string) => run('cancel', (id) => clientApi.cancelApplication(id, reason.trim() || undefined))
  /** rulesAccepted — клиент отметил согласие с Правилами ЭП; со старым бэкендом правил нет и флаг не нужен */
  const sign = (password: string, rulesAccepted = false) =>
    run('sign', async (id) => {
      const value = contract.value
      if (!value?.offer_hash) throw new Error('Договор ещё не загрузился — откройте заявку заново')
      // Подписываем ровно тот проект PDF, который клиент видел и мог скачать
      const draft = value.document?.kind === 'draft' && value.document.status === 'ready' ? value.document : null
      if (hasContractDocument(value) && !draft?.sha256) throw new Error('Договор ещё формируется — подождите несколько секунд')
      const rulesVersion = rulesAccepted ? rules.value?.version : undefined
      if (hasContractDocument(value) && !rulesVersion) throw new Error('Примите Правила электронного взаимодействия')
      try {
        const result = await clientApi.sign(id, password, value.offer_hash, draft?.sha256 ?? undefined, rulesVersion)
        signature.value = result.signature
      } catch (caught) {
        const code = caught instanceof ApiError ? caught.details.code : undefined
        // Предложение или проект PDF поменялись, пока клиент читал: показываем новый договор, подпись — заново
        if (code === 'offer_changed' || code === 'document_changed' || code === 'document_pending') await load(true)
        // Правила обновились: новая редакция, галочку клиент ставит заново
        if (code === 'rules_outdated') await loadRules()
        throw caught
      }
    })

  /** PDF договора: проект до подписи, подписанный — после */
  async function downloadContract(kind: 'draft' | 'signed') {
    const id = applicationId()
    if (!id) return
    busy.value = `contract:${kind}`
    actionError.value = null
    try {
      const file = await clientApi.downloadContractDocument(id, kind)
      saveFile(file.blob, file.filename ?? contract.value?.document?.filename ?? `Договор ${contract.value?.number ?? ''}.pdf`)
    } catch (caught) {
      actionError.value = errorMessage(caught)
    } finally {
      busy.value = null
    }
  }
  const answer = () =>
    run('answer', (id) => {
      const requestIdToAnswer = card.value?.info_request?.id
      if (!requestIdToAnswer) throw new Error('Запрос банка уже закрыт')
      return clientApi.answerInfoRequest(id, requestIdToAnswer)
    })

  /** Документ по дозапросу: сам привязывается к открытому запросу банка */
  async function upload(type: string, file: File) {
    const id = applicationId()
    if (!id) return
    const problem = fileProblem(type, file) ?? (type === STATEMENT_TYPE ? await statementProblem(file) : null)
    if (problem) {
      uploadErrors.value = { ...uploadErrors.value, [type]: problem }
      return
    }
    busy.value = `upload:${type}`
    uploadErrors.value = { ...uploadErrors.value, [type]: '' }
    try {
      await uploadApplicationDocument(id, type, file)
      await load(true)
    } catch (caught) {
      uploadErrors.value = { ...uploadErrors.value, [type]: errorMessage(caught) }
    } finally {
      busy.value = null
    }
  }

  async function download(documentId: string) {
    const id = applicationId()
    if (!id) return
    try {
      const { url } = await clientApi.downloadDocument(id, documentId)
      window.open(url, '_blank', 'noopener')
    } catch (caught) {
      actionError.value = errorMessage(caught)
    }
  }

  /** Документы, загруженные по открытому запросу банка, — по типам */
  const infoDocuments = computed(() => {
    const request = card.value?.info_request
    const documents = card.value?.documents ?? []
    return Object.fromEntries(
      (request?.requested_documents ?? []).map((type) => [
        type,
        documents.filter((document) => document.type === type && document.info_request_id === request?.id && document.status !== 'pending_upload'),
      ]),
    )
  })

  return {
    card,
    details,
    loading,
    error,
    busy,
    actionError,
    actionErrorCode,
    uploadErrors,
    signature,
    contract,
    contractError,
    documentSlow,
    rules,
    rulesError,
    infoDocuments,
    can,
    reload: () => load(),
    refreshDocument,
    loadRules,
    accept,
    decline,
    cancel,
    sign,
    answer,
    upload,
    download,
    downloadContract,
  }
}

export type ApplicationCard = ReturnType<typeof useApplicationCard>
