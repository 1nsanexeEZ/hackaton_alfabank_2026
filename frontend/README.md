# Frontend — кредитный кабинет

Vue 3 (Composition API, `<script setup>`), TypeScript, Tailwind CSS 4, Vite. Архитектура — [Feature-Sliced Design](https://feature-sliced.design/ru/).

## Запуск

Нужен Node.js 22+.

```bash
npm ci
npm run dev        # http://localhost:5173
npm run build      # проверка типов + сборка в dist/
npm run typecheck  # только проверка типов
```

Версии зависимостей зафиксированы точно в `package.json` и `package-lock.json`.

## Структура

```
src/
  app/        инициализация: main.ts, App.vue, роутер, глобальные стили и дизайн-токены
  pages/      страницы: landing, not-found
  widgets/    крупные блоки страницы: шапка, hero, каталог, калькулятор, форма, FAQ, футер
  features/   пользовательские действия: фильтр продуктов, расчёт платежа, отправка заявки
  entities/   бизнес-сущности: credit-product (каталог, карточка), application (статусы, карточка заявки)
  shared/     переиспользуемое без бизнес-логики: ui-кит, lib (форматирование, финансы, ИНН), config
```

Внутри слайса — сегменты `ui/`, `model/`, `api/`, `lib/`. Наружу слайс отдаёт только то, что есть в его `index.ts`.

### Правила импортов

- Слой импортирует только из слоёв ниже: `app → pages → widgets → features → entities → shared`.
- Слайсы одного слоя не импортируют друг друга. Если двум фичам нужны общие данные — их поднимает страница (пример: параметры кредита в `pages/landing` общие для каталога, калькулятора и формы).
- Из чужого слайса импортируем только через публичный API: `@/entities/credit-product`, а не `@/entities/credit-product/ui/ProductCard.vue`.

## Дизайн

Цвета, скругления и типографика сняты с лендинга кредитов для бизнеса Альфа-Банка и заведены токенами в `src/app/styles/index.css` (`@theme`). В вёрстке используем токены (`bg-brand`, `text-ink-secondary`, `rounded-card`, `text-title`), а не произвольные hex-значения.

Фирменный шрифт закрытый, вместо него Inter (OFL), подключён локально через `@fontsource-variable/inter` — сайт не зависит от внешних CDN.

Вёрстка mobile-first, проверена на 375, 768, 1024 и 1440 px.

## Что пока замокано

| Что | Где | Чем заменить |
|---|---|---|
| Каталог продуктов | `entities/credit-product/model/catalog.ts` | `GET /api/products` из BFF |
| Отправка заявки | `features/submit-application/api/submitApplication.ts` | `POST /api/applications` |
| Карточка заявки в hero | `widgets/hero/model/content.ts` | демо-данные, остаются на лендинге |
| Вход в кабинет | `/login` ведёт на страницу 404 | страница входа и кабинет клиента |

Статусы заявки в `entities/application/model/types.ts` — черновик, их нужно сверить со стейт-машиной бэкенда.
