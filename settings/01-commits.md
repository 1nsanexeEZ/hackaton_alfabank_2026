# 01. Коммиты: никаких следов агентов

Правило для всех, кто коммитит в репу — и людей, и агентов (Claude Code, Cursor, Copilot и т.д.).

## Правило

В истории git не должно быть видно, что коммит сделал агент.

- **Автор и коммиттер** — всегда человек из команды, под своим git-аккаунтом. Не `Claude`, не `noreply@anthropic.com`, не `copilot` и т.п.
- **Никаких трейлеров** в сообщении коммита:
  - `Co-Authored-By: Claude ...`
  - `Claude-Session: ...`
  - `Generated with ...`, `🤖 Generated with [Claude Code]` и любые аналоги
- **В описании PR** — то же самое, без подписей агента.
- **Имена веток** — без префиксов агентов (`claude/...`, `copilot/...`). Ветки называем по задаче: `feat/scoring-model`, `fix/deploy`.

## Как это обеспечено

- В [.claude/settings.json](../.claude/settings.json) отключена атрибуция Claude Code (`attribution.commit` и `attribution.pr` пустые) — это применяется автоматически для всех, кто запускает Claude Code в этой репе.
- Если работаешь с агентом через веб (claude.ai/code и т.п.) или другим инструментом — проверь `git log` перед пушем и, если что-то пролезло, поправь:
  ```bash
  git commit --amend --reset-author   # последний коммит
  ```
  Для нескольких коммитов — `git rebase` с правкой сообщений до пуша.

## Проверка перед пушем

```bash
git log --format='%an <%ae> | %cn <%ce>%n%b' origin/main..HEAD | grep -iE 'claude|anthropic|co-authored|generated with'
```

Пустой вывод — можно пушить.
