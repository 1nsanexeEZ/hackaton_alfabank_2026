<script setup lang="ts">
import { computed, ref } from 'vue'

import { backofficeApi, type ProductDto } from '@/shared/api'
import { errorMessage } from '@/shared/lib'
import { BaseButton, BaseModal } from '@/shared/ui'

/**
 * Выпустить черновик в продажу (POST /products/{code}/activate) или снять с продажи (DELETE):
 * продукт в продаже уходит в архив — старые заявки на него ссылаются, — черновик удаляется совсем
 */
const props = defineProps<{ product: ProductDto | null; action: 'activate' | 'withdraw' }>()
const open = defineModel<boolean>('open', { required: true })
const emit = defineEmits<{ changed: [code: string, product: ProductDto | null] }>()

const pending = ref(false)
const error = ref<string | null>(null)

const isDraft = computed(() => props.product?.status === 'draft')

const text = computed(() => {
  if (props.action === 'activate') {
    return {
      title: 'Выпустить в продажу?',
      body: 'Продукт появится на сайте и в подборе, по нему можно будет подавать заявки.',
      button: 'Выпустить',
    }
  }
  return isDraft.value
    ? { title: 'Удалить черновик?', body: 'Черновик удалится, его код снова станет свободным.', button: 'Удалить' }
    : {
        title: 'Снять с продажи?',
        body: 'Новые заявки на продукт подать будет нельзя. Поданные заявки рассматриваются на своих условиях, вернуть продукт можно, сохранив его условия.',
        button: 'Снять с продажи',
      }
})

async function confirm() {
  if (!props.product) return
  pending.value = true
  error.value = null
  try {
    const code = props.product.code
    if (props.action === 'activate') {
      emit('changed', code, await backofficeApi.activateProduct(code))
    } else {
      await backofficeApi.withdrawProduct(code)
      emit('changed', code, isDraft.value ? null : { ...props.product, status: 'archived' })
    }
    open.value = false
  } catch (caught) {
    error.value = errorMessage(caught)
  } finally {
    pending.value = false
  }
}
</script>

<template>
  <BaseModal v-model:open="open" :title="text.title">
    <p class="text-sm text-ink">
      <b class="font-semibold">{{ product?.name }}</b> · {{ product?.code }}
    </p>
    <p class="mt-2 text-sm text-ink-secondary">{{ text.body }}</p>
    <p v-if="error" class="mt-3 text-sm text-brand" role="alert">{{ error }}</p>
    <template #footer>
      <BaseButton variant="secondary" @click="open = false">Отмена</BaseButton>
      <BaseButton :loading="pending" @click="confirm">{{ text.button }}</BaseButton>
    </template>
  </BaseModal>
</template>
