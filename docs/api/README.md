# Описание API: путеводитель

Что лежит в `docs/api`, как открыть Swagger, как загрузить коллекцию Yaak и как её дополнить. Контракт ведёт бэкенд: схема и коллекция собираются из кода, руками их не правят.

## Что лежит в `docs/api`

| Что | Откуда берётся | Зачем |
|---|---|---|
| [`openapi.json`](openapi.json) | выгрузка схемы из `create_app()`: `backend/scripts/export_openapi.py` | схема всех ручек (136 операций, 108 путей) для генераторов клиентов и сверки |
| [`yaak.json`](yaak.json) | `backend/scripts/export_yaak.py` | коллекция Yaak одним файлом, для **Import** |
| [`yaak/`](yaak/) | он же | та же коллекция по файлам (`yaak.wk_*`, `yaak.ev_*`, `yaak.fl_*`, `yaak.rq_*`), для **Open Folder** с синхронизацией |
| [`client-journey.md`](../../settings/client-journey.md) | вручную | путь клиента по ручкам: что вызывать на каждом шаге, поля экранов, коды ошибок |

`openapi.json`, `yaak.json` и `yaak/` генерируются. Свежесть проверяют из `backend/`:

```bash
uv run python -m scripts.export_openapi --check   # код 1 — схема устарела
uv run python -m scripts.export_yaak --check      # код 1 — коллекция устарела
```

После изменения API или сценария: `uv run python -m scripts.export_openapi`, затем `uv run python -m scripts.export_yaak` (коллекция читает `openapi.json`, поэтому порядок такой) и закоммитить результат.

## Swagger

Запущенный стенд отдаёт Swagger UI по адресу `http://localhost:8080/api/docs`, схему — `http://localhost:8080/api/openapi.json`. Без Docker (`uv run uvicorn src.main:app` из `backend/`) — `http://localhost:8000/docs`. Кнопка **Authorize**: вставить `access_token` из `POST /auth/login` или `POST /auth/demo-login`.

## Коллекция Yaak

Установить [Yaak](https://yaak.app), затем один из двух способов:

1. **New Workspace → Open Folder** → `docs/api/yaak`. Yaak держит папку в синхронизации, правки видны в git.
2. **Import** → `docs/api/yaak.json`. Копия без синхронизации.

Выбрать окружение и отправлять запросы. Токены ролей брать не нужно: переменные `token_*` сами входят под демо-учётками (раз в 25 минут, токен живёт 30).

### Окружения

| Окружение | Где | `base_url` |
|---|---|---|
| `Общие` | корневое, наследуется остальными | — (переменные `admin_login`, `demo_password`, `admin_password` и `token_<роль>` для каждой роли) |
| `local` | поверх «Общие» | `http://localhost:8080/api` |
| `stand` | поверх «Общие» | `https://alfa-hack.ru/api` |
| `Переменные S-1` … `Переменные S-10`, `Переменные справочника` | привязаны к своим папкам | id компании, заявки, документа, задачи и т. п. — берутся из ответов предыдущих запросов |

Пароли демо-учёток — из сидов (`backend/seed/demo_data.py`, настройка `DEMO_PASSWORD`), в коллекцию они попадают как переменные базового окружения. После смены окружения отправьте заново вход нужных ролей из папки «Токены ролей»: иначе до 25 минут будут уходить токены прошлого стенда. На `stand` всю папку разом не отправляйте: nginx пускает на вход 10 запросов в минуту.

### Структура коллекции

В коллекции 345 запросов в трёх корневых папках.

| Папка | Запросов | Что |
|---|---|---|
| `Токены ролей` | 10 | вход под каждой демо-учёткой: «Ромашка» (директор и бухгалтер), ИП Иванов, «Вектор», «Закат», «Прогресс», «Сбой», «Старт», андеррайтер, администратор. Руками не отправляются: из ответов берутся `token_*` |
| `Сценарии S-1…S-10` | 198 | проверки из [README](../../README.md#сценарии-проверки-s-1s-10), шаги нумерованы и отправляются сверху вниз |
| `Справочник API` | 137 | все ручки схемы по разделам (136 операций и загрузка файла по presigned URL) |

**Сценарии.** Каждый сценарий — вложенная папка; id заявки, документа, задачи и хеш оферты шаги берут из ответов прошлых шагов. Решение банк принимает асинхронно: если шаг «Карточка» показывает ещё не тот статус, подождите пару секунд и отправьте его снова. Сценарий доводит заявку до финального статуса, поэтому его можно пройти заново: у компании не бывает двух активных заявок на один продукт (409 `duplicate_active`).

| Папка | Запросов | Что проверяет |
|---|---|---|
| `S-1. Ромашка: автоматическое одобрение` | 15 | типовая заявка, решение автоматикой, подпись, выдача |
| `S-2. ИП Иванов: андеррайтер снижает сумму` | 24 | модели расходятся, ручная проверка, встречное предложение |
| `S-3. Вектор: руководитель не совпадает с ЕГРЮЛ` | 13 | расхождение с реестром, ручная проверка |
| `S-4. Закат: отказ по стоп-факторам` | 6 | отказ до скоринга |
| `S-5. Прогресс: запрос выписки, затем андеррайтер` | 26 | дозапрос выписки, ответ клиента, ручная проверка |
| `S-6. Сбой: бюро кредитных историй недоступно` | 9 | сбой источника, заявка уходит человеку |
| `S-7. Ромашка: бизнес-ипотека всегда у человека` | 31 | ипотека: оценка залога, андеррайтер, подпись |
| `S-8. Бухгалтер подаёт, подписывает директор` | 16 | права в компании: бухгалтер без доверенности подписать не может |
| `S-9. Старт: предскрин учредителя и проектная оценка` | 28 | стартап: заявка с бизнес-планом, оценка андеррайтером |
| `S-10. Старт: бизнес-план в кабинете и предодобрение` | 30 | стартап: план и оценка до заявки, предложение «предодобрено до N» |

**Справочник.** Подпапки по разделам; запрос идёт с токеном роли, которой ручка доступна, и с примером тела.

| Папка | Запросов |
|---|---|
| `Служебные` | 2 |
| `Вход` | 4 |
| `Профиль и согласия` | 5 |
| `Компании` | 17 |
| `Продукты` | 11 |
| `Заявки` | 18 |
| `Договор: правила и проверка` | 3 |
| `Процесс и задачи` | 7 |
| `Предодобрение и стартапы` | 5 |
| `Модель скоринга` | 8 |
| `Политика решения` | 8 |
| `Ключевая ставка` | 4 |
| `Лента и новости` | 8 |
| `Техподдержка` | 12 |
| `Умный помощник` | 5 |
| `BFF клиента` | 5 |
| `BFF бэк-офиса` | 5 |
| `Администрирование` | 10 |

Запросы к аккаунтам и ролям работают с записями, которые коллекция создаёт для себя, а не с демо-данными; для остальных — компании и заявка «Ромашки» из последних ответов.

### Как собирается и как дополнить

Сборка — `backend/scripts/export_yaak.py`; идентификаторы стабильны (считаются от имени запроса), поэтому повторная выгрузка не плодит правок в git.

| Файл | За что отвечает |
|---|---|
| `backend/scripts/export_yaak.py` | окружения, папка «Токены ролей», порядок сборки, `--check` |
| `backend/scripts/yaak/collection.py` | модель коллекции: папки, запросы, окружения, переменные-ответы |
| `backend/scripts/yaak/accounts.py` | демо-учётки и переменные `token_*` |
| `backend/scripts/yaak/reference.py` | справочник: разделы (`FOLDERS`), названия (`NAMES`), примеры тел, примечания (`NOTES`), роль запроса |
| `backend/scripts/yaak/scenarios.py` | сценарии S-1…S-10: класс `Scenario`, функции `_s1` … `_s10` |

**Новая ручка.** Добавить её в код, выгрузить `openapi.json` и затем коллекцию — запрос появится в справочнике сам: раздел определяется по тегу (`_folder`), роль — по требованию безопасности ручки (`_role`). Для понятного названия — строка в `NAMES`, для примера тела — запись в `_bodies()`, для пояснения — в `NOTES`; новый раздел — строка в `FOLDERS`.

**Новый шаг сценария.** В функции сценария (`_sN` в `scenarios.py`) вызвать `s.step(key, name, method, path, who=…, note=…, body=…, params=…, query=…)`. Значения, которые шаг берёт из прошлых ответов, задаются через `s.answer(ключ_шага, "$.путь")`. Готовые части — `s.draft`, `s.document`, `s.submit`, `s.card`, `s.underwriter`, `s.accept_and_sign`, `s.disbursed`. Сценарий должен заканчиваться финальным статусом заявки.

**Новый сценарий.** Функция `_s11(collection, root)` с объектом `Scenario(...)` и добавление её в кортеж в `add_scenarios`.

После правки: `uv run python -m scripts.export_yaak`, затем `uv run python -m scripts.export_yaak --check` (должен вернуть 0) и коммит `docs/api/yaak/` с `docs/api/yaak.json`.

## Группы ручек по модулям

По `openapi.json`: префикс пути → тег → модуль, который отвечает. Подробности по каждой группе — в документе модуля.

| Префикс пути | Тег | Модуль | Документ |
|---|---|---|---|
| `/auth/*`, `/.well-known/jwks.json` | `auth` | identity | [identity.md](../identity.md) |
| `/me`, `/me/consents` | `me` | identity | [identity.md](../identity.md) |
| `/accounts` | `accounts` | identity | [identity.md](../identity.md) |
| `/roles` | `roles` | identity | [identity.md](../identity.md) |
| `/organizations/{id}/consents` | `organizations` | identity | [identity.md](../identity.md#согласия-компании) |
| `/organizations`, `/organizations/{id}/…` (участники, доверенности, отчётность, бизнес-план, сверка, `inn-check`) | `organizations` | clients | [clients.md](../modules/clients.md) |
| `/organizations/{id}/pre-approved-offers`, `…/founder-prescreen`, `…/project-assessment` | `decision` | decision | [decision.md](../modules/decision.md) |
| `/decision/policies*` | `decision` | decision | [decision.md](../modules/decision.md) |
| `/scoring/models*` | `scoring` | scoring | [scoring.md](../modules/scoring.md) |
| `/products*` | `products` | products | [products.md](../modules/products.md) |
| `/applications*` | `applications` | applications | [applications.md](../modules/applications.md) |
| `/esign/rules`, `/contracts/verify*` | `contracts` | applications | [contract-signing.md](../contract-signing.md) |
| `/tasks*`, `/processes/{id}`, `/workflows*` | `process` | process | [process.md](../modules/process.md) |
| `/market/*` | `market` | market | [market.md](../modules/market.md) |
| `/feed*`, `/news*` | `feed`, `news` | notifications | [notifications.md](../modules/notifications.md) |
| `/support/*` | `support` | support | [support.md](../modules/support.md) |
| `/assistant/*` | `assistant` | assistant | [assistant-api.md](../assistant-api.md), [ai.md](../ai.md) |
| `/bff/*`, `/bff/backoffice/*` | `bff` | bff | [bff.md](../modules/bff.md) |
| `/health`, `/ready` | `service` | платформа (`src/main.py`) | [platform.md](../platform.md) |

Своих HTTP-ручек нет у модулей `enrichment` ([enrichment.md](../modules/enrichment.md)) и `projector` ([projector.md](../modules/projector.md)): они работают через Kafka и фасады, а экраны читают их через BFF.

Общие правила (авторизация, формат ошибок, деньги, даты, списки с `X-Total-Count`) — в разделе 1 [client-journey.md](../../settings/client-journey.md#1-общие-правила).
