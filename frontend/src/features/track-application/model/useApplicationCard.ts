import { computed, onBeforeUnmount, ref, shallowRef, watch } from 'vue'

import { fileProblem, myApplications, uploadApplicationDocument } from '@/entities/application'
import { liveFeed } from '@/entities/notification'
import { ApiError, clientApi, type ApplicationDto, type ClientApplicationCardDto, type ContractDto } from '@/shared/api'
import { errorMessage } from '@/shared/lib'

/** Пока банк думает, без живого потока перечитываем карточку сами */
const POLL_MS = 5_000
const PROCESSING = new Set(['submitted', 'in_review'])
/** С этих клиентских статусов у заявки есть договор */
const WITH_CONTRACT = new Set(['signing', 'issued'])

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
  const uploadErrors = ref<Record<string, string>>({})
  const signature = shallowRef<{ signed_at: string; edo_document_id: string; simulated: boolean } | null>(null)
  /** Договор: на подписи — что клиент подписывает (и его offer_hash), после — что подписано */
  const contract = shallowRef<ContractDto | null>(null)
  const contractError = ref<string | null>(null)

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
      card.value = next
      details.value = full
      contract.value = nextContract
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

  onBeforeUnmount(() => {
    stopLive()
    clearInterval(timer)
  })

  const can = (action: string) => card.value?.available_actions.includes(action) ?? false

  async function run(name: string, action: (id: string) => Promise<unknown>) {
    const id = applicationId()
    if (!id) return false
    busy.value = name
    actionError.value = null
    try {
      await action(id)
      await load(true)
      void myApplications.refresh()
      return true
    } catch (caught) {
      actionError.value = errorMessage(caught)
      return false
    } finally {
      busy.value = null
    }
  }

  const accept = () => run('accept', (id) => clientApi.acceptOffer(id))
  const decline = (reason: string) => run('decline', (id) => clientApi.declineOffer(id, reason.trim() || undefined))
  const cancel = (reason: string) => run('cancel', (id) => clientApi.cancelApplication(id, reason.trim() || undefined))
  const sign = (password: string) =>
    run('sign', async (id) => {
      const offerHash = contract.value?.offer_hash
      if (!offerHash) throw new Error('Договор ещё не загрузился — откройте заявку заново')
      try {
        const result = await clientApi.sign(id, password, offerHash)
        signature.value = result.signature
      } catch (caught) {
        // Предложение поменялось, пока клиент читал договор: показываем новый договор, подпись — заново
        if (caught instanceof ApiError && caught.details.code === 'offer_changed') await load(true)
        throw caught
      }
    })
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
    const problem = fileProblem(type, file)
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
    uploadErrors,
    signature,
    contract,
    contractError,
    infoDocuments,
    can,
    reload: () => load(),
    accept,
    decline,
    cancel,
    sign,
    answer,
    upload,
    download,
  }
}

export type ApplicationCard = ReturnType<typeof useApplicationCard>
