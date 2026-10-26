# Third-party notices

Сторонние компоненты, модели, данные и сервисы, которые использует решение, и интеграции, которые в нём смоделированы. Требование кейса: «файл THIRD_PARTY_NOTICES с перечнем используемых сторонних компонентов, моделей, датасетов и сервисов, а также указанием смоделированных интеграций».

Версии взяты из lock-файлов (`backend/uv.lock`, `external-mocks/uv.lock`, `frontend/package-lock.json`) и тегов образов в `docker-compose.yml` и Dockerfile. Лицензии — из метаданных установленных пакетов (`License-Expression`, поле `License` или классификаторы PyPI) и `package.json` пакетов npm. При обновлении зависимостей список нужно пересобрать.

## Смоделированные интеграции

Реальных интеграций с банковскими и государственными системами в решении нет (ограничение кейса «Автономность»). Каждая внешняя система воспроизведена локальным моком за настоящей HTTP-границей: backend ходит к ней через адаптер, поэтому замена мока на реальный API — это новый адаптер, а не правка бизнес-логики. Моки живут в отдельном сервисе `external-mocks/` (FastAPI, порт 8100), данные синтетические. Полный список эндпоинтов — в `external-mocks/README.md`.

| Внешняя система | Что делает в процессе | Мок | Адаптер в backend | Пометка |
|---|---|---|---|---|
| ЕГРЮЛ / ЕГРИП (ФНС России) | статус и дата регистрации, ОКВЭД, руководитель, учредители, адрес | `GET /egrul/{inn}` — ключи кириллицей, даты строками | `EgrulHttpSource` (`backend/src/modules/enrichment/infrastructure/adapters/egrul_http.py`) | **смоделировано** |
| ФНС «Прозрачный бизнес» | недоимка, численность, выручка и расходы, налоговый режим, реестр МСП | `GET /fns/{inn}` — суммы в копейках | `FnsHttpSource` (`.../adapters/fns_http.py`) | **смоделировано** |
| Бюро кредитных историй | обязательства, платежи, просрочки, запросы за 30 дней | `POST /bki/report` `{inn, consent_at, request_id}`; без `consent_at` — 400; ИНН из `MOCK_BKI_ALWAYS_FAIL_INNS` — всегда 503 (сценарий S-6) | `BkiHttpSource` (`.../adapters/bki_http.py`), запрос только при согласии клиента | **смоделировано** |
| БКИ руководителя (физлицо) | кредитная история руководителя по реестру | `POST /bki/person-report`; без `consent_at` — 400 (218-ФЗ) | `BkiPersonHttpSource` (`.../adapters/bki_person_http.py`), запрос только при личном согласии руководителя | **смоделировано** |
| ГИР БО (бухотчётность) | бухгалтерская отчётность за два последних года | `GET /gir-bo/{inn}` — суммы в тыс. ₽ | `GirBoHttpSource` (`.../adapters/gir_bo_http.py`) | **смоделировано** |
| Контур.Фокус | арбитраж, исполнительные производства, банкротство, госконтракты, залоги | `GET /kontur/{inn}` | `KonturHttpSource` (`.../adapters/kontur_http.py`) | **смоделировано** |
| Перечни Росфинмониторинга | экстремизм и терроризм, решения МВК о замораживании, ФРОМУ — для проверки по 115-ФЗ | `POST /rfm/screen` — коды перечней строками | `RfmHttpSource` (`.../adapters/aml_http.py`) | **смоделировано**, записи синтетические |
| База публичных должностных лиц | иностранные, российские ПДЛ и должностные лица международных организаций | `POST /pep/screen` | `PepHttpSource` (`.../adapters/aml_http.py`) | **смоделировано**, записи синтетические |
| Платформа «Знай своего клиента» Банка России | уровень риска юрлица или ИП | `GET /zsk/{inn}` | `ZskHttpSource` (`.../adapters/aml_http.py`) | **смоделировано** |
| Реестр лицензий | действующие лицензии компании и лицензируемый вид деятельности | `GET /licenses/{inn}` | `LicensesHttpSource` (`.../adapters/licenses_http.py`) | **смоделировано** |
| АБС банка (клиент банка и обороты) | с какой даты компания клиент банка, помесячные обороты по счёту за 24 месяца | `GET /abs/accounts/{inn}` | `BankTurnoverHttpSource` (`.../adapters/bank_turnover_http.py`) | **смоделировано** |
| Внутренний стоп-лист банка | стоп-фактор решения, согласия клиента не требует | `GET /abs/stop-list/{inn}` | `BankStopListHttpSource` (`.../adapters/bank_stop_list_http.py`) | **смоделировано** |
| ЭДО / электронная подпись | подписание кредитной документации | `POST /edo/sign` → номер документа, `simulated: true` | `HttpEdoClient`; если `APPLICATIONS_EXTERNAL_MOCKS_URL` пуст — `SimulatedEdoClient` внутри backend (`backend/src/modules/applications/infrastructure/adapters/edo_client.py`) | **смоделировано**, ответ API `simulated: true` |
| Электронная подпись банка | подпись PDF кредитного договора после подписи клиента | ключ и сертификат демо-УЦ стенда, метка времени — встроенная служба pyHanko (`DummyTimeStamper`) | `PyHankoContractSealer` (`backend/src/modules/applications/infrastructure/adapters/contract_sealer.py`): настоящая подпись PAdES | **ключ демо-стенда**, не квалифицированный |
| АБС банка (выдача средств) | перевод суммы кредита на счёт клиента | `POST /abs/disbursements` → номер договора, `simulated: true` | `HttpAbsClient`; если `APPLICATIONS_EXTERNAL_MOCKS_URL` пуст — `SimulatedAbsClient` (`backend/src/modules/applications/infrastructure/adapters/abs_client.py`) | **смоделировано** |

Поведение моков: детерминированные ответы для семи демо-компаний (`backend/seed/demo_data.py`) и генерация по хешу для любого другого валидного ИНН; невалидный ИНН — 404. Нестабильность сети имитируется: задержка `MOCK_LATENCY_MS_MIN..MAX` и доля ответов 503 `MOCK_FAILURE_RATE` (в `docker-compose.yml` для демо выключена). Подробно — `external-mocks/README.md`.

Этапы самого кредитного конвейера (подача, проверка данных, подбор продукта, скоринг, решение) не смоделированы — это настоящая логика решения (требование экспертов вебинара 21.10).

## Модели и датасеты

- **Подбор продукта, проверки и решение — детерминированные правила в коде.** Платных API и подписок в проверяемой версии нет.
- **LLM — только в умном помощнике** (модуль backend `assistant`; контейнер `ollama` — профиль compose `ai`, по умолчанию не запускается). Модели с открытыми весами, без дообучения, запускаются локально через Ollama; веса не входят в репозиторий и образы, скачиваются явной командой `backend/scripts/ai-pull-model.sh`. Вместо локальной модели можно подключить любой OpenAI-совместимый API с моделью с открытыми весами (например, OpenRouter) — ключ задаётся в `.env`, в репозитории его нет. Помощник ничего не решает и без модели отвечает по шаблонам. Подробно — [`docs/ai.md`](docs/ai.md).

  | Модель | Где взята | Лицензия | Параметров | Роль |
  |---|---|---|---|---|
  | Qwen3-4B-Instruct-2507 | [huggingface.co/Qwen/Qwen3-4B-Instruct-2507](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507); в Ollama — `qwen3:4b-instruct-2507-q4_K_M` (GGUF Q4_K_M) | Apache-2.0 | 4,0 млрд | основная: формулирует ответ ассистента по фактам |
  | Qwen2.5-1.5B-Instruct | [huggingface.co/Qwen/Qwen2.5-1.5B-Instruct](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct); в Ollama — `qwen2.5:1.5b` (GGUF Q4_K_M) | Apache-2.0 | 1,5 млрд | лёгкая: для машин с 8 ГБ памяти |
  | Qwen2.5-7B-Instruct | [huggingface.co/Qwen/Qwen2.5-7B-Instruct](https://huggingface.co/Qwen/Qwen2.5-7B-Instruct); в Ollama — `qwen2.5:7b` (GGUF Q4_K_M) | Apache-2.0 | 7,6 млрд | необязательная: для машин с 16 ГБ, если нужен русский получше |

- **ML-модель скоринга `ml_logreg_v1` обучена командой** — логистическая регрессия на синтетической популяции заявок (`backend/ml/population.py`, `backend/ml/train.py`); в образ попадают только её коэффициенты (`backend/src/modules/scoring/infrastructure/config/ml_logreg_v1.yaml`), инференс — чистый Python без ML-библиотек. Библиотеки обучения (scikit-learn, numpy, pandas, matplotlib, jupyter, nbconvert) — группа зависимостей `ml` в `backend/pyproject.toml`, ставятся только локально и в образ не входят.
- **Внешних датасетов нет.** Все данные синтетические и созданы командой: компании, люди, финансовые показатели и кредитные истории (`backend/seed/demo_data.py`, `external-mocks/app/data.py`), каталог продуктов (`backend/seed/products.py`), тексты новостей ленты (`backend/seed/notifications.py`), синтетические банковские выписки (`backend/seed/statements/`, генератор `backend/scripts/generate_statements.py`). ИНН и ОГРН собраны с правильными контрольными цифрами; совпадение с реальными субъектами случайно.

## Образы Docker

| Образ | Тег | Где | Лицензия ПО |
|---|---|---|---|
| `postgres` | `16.4-alpine` | `docker-compose.yml`, сервис `db`; CI | PostgreSQL License |
| `soldevelo/minio` | `2026.7.17` | `docker-compose.yml`, сервис `minio` | GNU AGPL v3 (MinIO); используется без изменений как отдельный сервис через S3 API |
| `apache/kafka` | `3.8.0` | `docker-compose.yml`, сервис `kafka` | Apache-2.0 |
| `nginx` | `1.31.7-alpine` | `docker-compose.yml`, сервис `nginx`; база образа `frontend/Dockerfile` (раздача статики) | BSD-2-Clause |
| `node` | `22.23.4-alpine` | стадия сборки `frontend/Dockerfile`, в итоговый образ не входит | MIT (Node.js) |
| `ollama/ollama` | `0.40.0` | `docker-compose.yml`, сервис `ollama` (профиль `ai`): рантайм моделей с OpenAI-совместимым API | MIT |
| `python` | `3.12-slim` | база образов `backend/Dockerfile` и `external-mocks/Dockerfile` | PSF-2.0 (CPython) |
| `ghcr.io/astral-sh/uv` | `0.12.10` (backend), `0.13.4` (external-mocks) | из образа копируются только бинарники `uv` (и `uvx` у external-mocks) для установки зависимостей и запуска | MIT OR Apache-2.0 |

Пакеты базовых ОС (Alpine Linux, Debian) распространяются под собственными лицензиями, их тексты лежат внутри образов.

## Backend: Python-зависимости

Python 3.12 (`backend/.python-version`), менеджер `uv`, lock — `backend/uv.lock`.

### Входят в образ

| Пакет | Версия | Лицензия |
|---|---|---|
| aioboto3 | 15.5.0 | Apache-2.0 |
| aiobotocore | 2.25.1 | Apache-2.0 |
| aiofiles | 25.1.0 | Apache-2.0 |
| aiohappyeyeballs | 2.7.1 | PSF-2.0 |
| aiohttp | 3.14.5 | Apache-2.0 AND MIT |
| aioitertools | 0.13.0 | MIT |
| aiokafka | 0.14.0 | Apache-2.0 |
| aiosignal | 1.4.0 | Apache-2.0 |
| alembic | 1.20.0 | MIT |
| annotated-doc | 0.0.5 | MIT |
| annotated-types | 0.8.0 | MIT |
| anyio | 4.15.1 | MIT |
| argon2-cffi | 25.1.0 | MIT |
| argon2-cffi-bindings | 26.1.0 | MIT |
| asn1crypto | 1.5.1 | MIT |
| async-timeout | 5.0.1 | Apache-2.0 |
| asyncpg | 0.32.0 | Apache-2.0 |
| attrs | 26.1.0 | MIT |
| boto3 | 1.40.61 | Apache-2.0 |
| botocore | 1.40.61 | Apache-2.0 |
| certifi | 2026.10.19 | MPL-2.0 |
| cffi | 2.1.1 | MIT-0 |
| click | 8.5.0 | BSD-3-Clause |
| cryptography | 50.0.2 | Apache-2.0 OR BSD-3-Clause |
| defusedxml | 0.7.1 | PSF-2.0 |
| dnspython | 2.9.0 | ISC |
| email-validator | 2.3.0 | Unlicense |
| fast-depends | 3.0.9 | MIT |
| fastapi | 0.156.4 | MIT |
| faststream | 0.7.7 | Apache-2.0 |
| fonttools | 4.67.0 | MIT |
| fpdf2 | 2.8.9 | LGPL-3.0-only; используется без изменений как библиотека |
| frozenlist | 1.8.0 | Apache-2.0 |
| greenlet | 3.5.6 | MIT AND PSF-2.0 |
| h11 | 0.16.0 | MIT |
| httpcore | 1.0.9 | BSD-3-Clause |
| httptools | 0.9.0 | MIT |
| httpx | 0.28.1 | BSD-3-Clause |
| idna | 3.20 | BSD-3-Clause |
| jmespath | 1.1.0 | MIT |
| lxml | 6.1.3 | BSD-3-Clause |
| mako | 1.4.3 | MIT |
| markupsafe | 3.0.4 | BSD-3-Clause |
| multidict | 6.9.1 | Apache-2.0 |
| nh3 | 0.3.7 | MIT |
| opentelemetry-api | 1.45.1 | Apache-2.0 |
| oscrypto | 1.3.0 | MIT |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause |
| pillow | 13.0.0 | MIT-CMU |
| propcache | 0.5.4 | Apache-2.0 |
| pycparser | 3.11 | BSD-3-Clause |
| pydantic | 2.14.1 | MIT |
| pydantic-core | 2.50.1 | MIT |
| pydantic-settings | 2.16.1 | MIT |
| pyhanko | 0.38.0 | MIT |
| pyhanko-certvalidator | 0.33.0 | MIT |
| pyjwt | 2.15.1 | MIT |
| python-dateutil | 2.9.0.post0 | Apache-2.0 AND BSD-3-Clause |
| python-dotenv | 1.2.4 | BSD-3-Clause |
| python-multipart | 0.0.32 | Apache-2.0 |
| pyyaml | 6.0.3 | MIT |
| qrcode | 8.2 | BSD-3-Clause |
| s3transfer | 0.14.0 | Apache-2.0 |
| six | 1.17.0 | MIT |
| sqlalchemy | 2.1.5 | MIT |
| sse-starlette | 3.5.0 | BSD-3-Clause |
| starlette | 1.9.0 | BSD-3-Clause |
| typing-extensions | 4.16.0 | PSF-2.0 |
| typing-inspection | 0.4.4 | MIT |
| tzlocal | 5.4.5 | MIT |
| uritools | 6.1.3 | MIT |
| urllib3 | 2.8.0 | MIT |
| uvicorn | 0.54.0 | BSD-3-Clause |
| uvloop | 0.23.0 | MIT OR Apache-2.0 |
| watchfiles | 1.3.0 | MIT |
| websockets | 17.3 | BSD-3-Clause |
| wrapt | 1.17.3 | BSD-2-Clause |
| yarl | 1.25.1 | Apache-2.0 |

`uvloop` ставится только на Linux (в образе), лицензия указана по PyPI.

Шрифты PDF договора — PT Sans и PT Mono (ParaType), SIL Open Font License 1.1: `backend/src/modules/applications/infrastructure/contract_pdf/fonts/` вместе с `OFL.txt`, встраиваются в PDF без изменений.

### Только для разработки и тестов

В образ не входят (`uv sync --no-dev`).

| Пакет | Версия | Лицензия |
|---|---|---|
| aiosqlite | 0.22.1 | MIT |
| ast-serialize | 0.13.1 | MIT |
| charset-normalizer | 3.5.2 | MIT |
| colorama | 0.4.6 | BSD-3-Clause |
| docker | 7.2.0 | Apache-2.0 |
| grimp | 3.17 | BSD-2-Clause |
| import-linter | 2.15 | BSD-2-Clause |
| iniconfig | 2.3.1 | MIT |
| librt | 0.16.0 | MIT |
| markdown-it-py | 4.2.0 | MIT |
| mdurl | 0.1.2 | MIT |
| minio | 7.2.20 | Apache-2.0 |
| mypy | 2.4.0 | MIT |
| mypy-extensions | 1.1.0 | MIT |
| pathspec | 1.1.1 | MPL-2.0 |
| pluggy | 1.7.0 | MIT |
| pycryptodome | 4.1.0 | BSD-2-Clause AND Unlicense AND MIT |
| pygments | 2.21.0 | BSD-2-Clause |
| pytest | 9.1.1 | MIT |
| pytest-asyncio | 1.4.0 | Apache-2.0 |
| pywin32 | 312 | PSF-2.0 |
| requests | 2.34.2 | Apache-2.0 |
| rich | 15.0.0 | MIT |
| ruff | 0.17.1 | MIT |
| testcontainers | 4.15.0 | Apache-2.0 |
| types-pyyaml | 6.0.12.20260906 | Apache-2.0 |

## external-mocks: Python-зависимости

Lock — `external-mocks/uv.lock`.

| Пакет | Версия | Лицензия |
|---|---|---|
| annotated-doc | 0.0.5 | MIT |
| annotated-types | 0.8.0 | MIT |
| anyio | 4.15.1 | MIT |
| click | 8.5.0 | BSD-3-Clause |
| fastapi | 0.157.0 | MIT |
| h11 | 0.16.0 | MIT |
| httptools | 0.9.0 | MIT |
| idna | 3.20 | BSD-3-Clause |
| opentelemetry-api | 1.45.1 | Apache-2.0 |
| pydantic | 2.14.1 | MIT |
| pydantic-core | 2.50.1 | MIT |
| python-dotenv | 1.2.4 | BSD-3-Clause |
| pyyaml | 6.0.3 | MIT |
| starlette | 1.9.0 | BSD-3-Clause |
| typing-extensions | 4.16.0 | PSF-2.0 |
| typing-inspection | 0.4.4 | MIT |
| uvicorn | 0.54.0 | BSD-3-Clause |
| uvloop | 0.23.0 | MIT OR Apache-2.0 |
| watchfiles | 1.3.0 | MIT |
| websockets | 17.3 | BSD-3-Clause |

Только для разработки и тестов:

| Пакет | Версия | Лицензия |
|---|---|---|
| certifi | 2026.10.19 | MPL-2.0 |
| colorama | 0.4.6 | BSD-3-Clause |
| httpcore | 1.0.9 | BSD-3-Clause |
| httpx | 0.28.1 | BSD-3-Clause |
| iniconfig | 2.3.1 | MIT |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause |
| pluggy | 1.7.0 | MIT |
| pygments | 2.21.0 | BSD-2-Clause |
| pytest | 9.1.1 | MIT |
| ruff | 0.17.1 | MIT |

## Frontend: npm-зависимости

Node.js 22+, версии зафиксированы точно в `frontend/package.json` и `frontend/package-lock.json`.

| Пакет | Версия | Лицензия | Зачем |
|---|---|---|---|
| `vue` | 3.5.44 | MIT | UI-фреймворк |
| `vue-router` | 5.4.0 | MIT | маршрутизация |
| `lucide-vue-next` | 1.0.0 | ISC | иконки |
| `@fontsource-variable/inter` | 5.3.0 | OFL-1.1 | шрифт Inter (лежит в сборке, внешний CDN шрифтов не нужен) |
| `vite` | 8.3.5 | MIT | сборка и dev-сервер |
| `@vitejs/plugin-vue` | 6.0.10 | MIT | сборка |
| `tailwindcss`, `@tailwindcss/vite` | 4.3.3 | MIT | стили |
| `typescript` | 6.0.3 | Apache-2.0 | типизация |
| `vue-tsc` | 3.3.13 | MIT | проверка типов |
| `@vue/tsconfig` | 0.9.1 | MIT | конфигурация TypeScript |
| `@types/node` | 24.19.2 | MIT | типы Node.js |
| `eslint` | 10.13.0 | MIT | линтер (`npm run lint`) |
| `@eslint/js` | 10.0.1 | MIT | правила ESLint |
| `eslint-plugin-vue` | 10.11.1 | MIT | правила для Vue |
| `typescript-eslint` | 8.72.0 | MIT | разбор TypeScript для ESLint |
| `vue-eslint-parser` | 10.4.1 | MIT | разбор `.vue` для ESLint |
| `globals` | 17.13.0 | MIT | глобальные имена для ESLint |

В браузер попадают только `vue`, `vue-router`, `lucide-vue-next` и шрифт Inter, остальное — инструменты сборки и проверки. Всего в `package-lock.json` 247 пакетов (вместе с транзитивными и платформенными бинарниками); их лицензии: MIT, ISC, Apache-2.0, BSD-2-Clause, BSD-3-Clause, MPL-2.0 (`lightningcss` и его платформенные сборки — обработка CSS при сборке), BlueOak-1.0.0 (`minimatch`, зависимость ESLint) и OFL-1.1 (шрифт Inter).

## Инструменты разработки

Используются только при разработке и в CI, в проверяемую версию не входят.

| Инструмент | Лицензия | Где |
|---|---|---|
| uv | MIT OR Apache-2.0 | установка зависимостей, запуск тестов |
| ruff, mypy, pytest, import-linter, testcontainers | см. таблицы dev-зависимостей | проверки в CI (`.github/workflows/ci.yml`) |
| Playwright (`@playwright/test` 1.64.1, `playwright`, `playwright-core`), `typescript` 6.0.3, `@types/node` 24.19.2 | Apache-2.0, MIT | e2e-тесты кабинета клиента (`e2e/`, [`e2e/README.md`](e2e/README.md)); браузер Chromium скачивается командой `npx playwright install chromium` и в репозиторий не входит |
| GitHub Actions: `actions/checkout`, `actions/setup-node`, `astral-sh/setup-uv` | MIT | CI (`.github/workflows/ci.yml`); деплой стенда (`.github/workflows/deploy.yml`) идёт по SSH обычным `ssh` без сторонних actions |

BPMN-схемы маршрутов — файлы BPMN 2.0 `backend/src/modules/process/workflows/*.bpmn`; их исполняет собственный движок модуля `process` (разбор XML — `lxml`). Редактор схем в поставку не входит.
