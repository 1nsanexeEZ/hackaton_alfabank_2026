import { createApp } from 'vue'

import { shakeInvalidOnSubmit } from '@/shared/lib'

import App from './App.vue'
import { router } from './router'
import './styles/index.css'

const app = createApp(App).use(router)

// Любая форма: отправили с незаполненным обязательным — помеченные поля вздрагивают красным
shakeInvalidOnSubmit()

// Ждём первый маршрут: по нему App решает, нужен ли каркас сайта или админки
void router.isReady().then(() => app.mount('#app'))
