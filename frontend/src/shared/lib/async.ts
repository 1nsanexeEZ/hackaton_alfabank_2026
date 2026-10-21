import { ref, shallowRef, type Ref, type ShallowRef } from 'vue'

export interface AsyncData<T> {
  data: ShallowRef<T | null>
  loading: Ref<boolean>
  error: Ref<string | null>
  /** Перезапросить данные; ошибка попадает в error, а не выбрасывается */
  reload: () => Promise<void>
}

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'Что-то пошло не так'
}

/** Загрузка данных с состояниями: при создании сразу запрашивает, повторно — через reload */
export function useAsyncData<T>(load: () => Promise<T>, options: { immediate?: boolean } = {}): AsyncData<T> {
  const data = shallowRef<T | null>(null)
  const loading = ref(options.immediate !== false)
  const error = ref<string | null>(null)
  // Ответ старого запроса не должен перезаписать ответ нового
  let requestId = 0

  async function reload() {
    const current = ++requestId
    loading.value = true
    error.value = null
    try {
      const result = await load()
      if (current === requestId) data.value = result
    } catch (caught) {
      if (current === requestId) error.value = errorMessage(caught)
    } finally {
      if (current === requestId) loading.value = false
    }
  }

  if (options.immediate !== false) void reload()

  return { data, loading, error, reload }
}
