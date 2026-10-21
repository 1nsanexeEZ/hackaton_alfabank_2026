import { createApp } from 'vue'

import App from './App.vue'
import './providers/credit-mock'
import { router } from './router'
import './styles/index.css'

const app = createApp(App).use(router)

// Ждём первый маршрут: по нему App решает, нужен ли каркас сайта или админки
void router.isReady().then(() => app.mount('#app'))
