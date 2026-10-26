import { versionsApi, type VersionKind } from '@/entities/scoring-version'
import type { VersionSummaryDto } from '@/shared/api'

/**
 * «Изменить» версию. Действующую и архивную бэкенд на месте не правит — правка идёт в черновике на её
 * основе, а в работу его выпускает «Активировать». Черновик на этой основе уже есть — открываем самый
 * свежий, а не плодим копии; нет — создаём. Возвращает код черновика.
 */
export async function draftToEdit(kind: VersionKind, base: string, versions: readonly VersionSummaryDto[]): Promise<string> {
  const existing = versions
    .filter((item) => item.status === 'draft' && item.based_on === base)
    .sort((a, b) => (b.updated_at ?? '').localeCompare(a.updated_at ?? ''))[0]
  if (existing) return existing.version
  return (await versionsApi(kind).createDraft({ based_on: base })).version
}
