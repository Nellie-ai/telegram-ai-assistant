# Telegram LLM Bot MVP

Демонстрационный Telegram-бот на Python 3.12 и aiogram 3. Входящие сообщения из личных чатов маршрутизируются по `user_id` в профиль поведения, затем (кроме `IGNORE`) отправляются в OpenAI-compatible Chat Completions API.

## Архитектура

- `handlers.py` — Telegram transport и разбиение ответов длиннее 4096 символов.
- `bot_service.py` — сценарий обработки сообщения и безопасные пользовательские ошибки.
- `profile_router.py` — выбор профиля по отправителю.
- `llm.py` — изолированный HTTP-клиент LLM.
- `memory.py` — отдельная in-memory история для каждого пользователя.
- `config.py` — настройки и prompts; handler конфигурацию не содержит.

## Принятые MVP-решения

- Неизвестный `user_id` получает профиль `DEFAULT`.
- `IGNORE_SILENT=true` включает молчаливый режим; иначе возвращается `IGNORE_REPLY`.
- Память хранит не более 10 сообщений (реплики user и assistant считаются отдельно) на процесс. `MEMORY_LIMIT` принимает значения от 1 до 10. После перезапуска история теряется.
- Неуспешный запрос к LLM в память не записывается, чтобы временная ошибка не загрязняла контекст.
- Реплики user и assistant записываются только после успешной отправки всех частей ответа в Telegram.
- Сообщения одного пользователя обрабатываются последовательно; разные пользователи не блокируют друг друга.
- Ответ длиннее лимита Telegram режется на последовательные части по 4096 символов. Семантическое разбиение абзацев сознательно не добавлено в MVP.
- Профили расширяются значениями `ProfileName`, prompts — словарём `DEFAULT_PROMPTS` или JSON override `PROFILE_PROMPTS`; привязки пользователей задаются JSON в `USER_PROFILES`.
- Используется OpenAI-compatible endpoint `POST /chat/completions`. Токены и полные тексты сообщений не логируются.
- При Telegram rate limit выполняется одна повторная попытка после указанной сервером задержки. Другие ожидаемые ошибки отправки безопасно логируются без текста сообщения.

## Запуск

Требуется Python 3.12+.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

Заполните `TELEGRAM_BOT_TOKEN`, `LLM_API_KEY` и JSON-карту `USER_PROFILES` в `.env`, затем:

```powershell
python -m telegram_llm_bot
```

Пример переопределения prompt в `.env`:

```dotenv
PROFILE_PROMPTS={"OWNER":"Answer the owner briefly and precisely."}
```

## Тесты

```powershell
pytest
```

## Stage 2: user-account listener

Stage 2 запускается отдельным процессом через Telethon и не использует BotFather token. Listener принимает только входящие личные сообщения обычного Telegram-аккаунта. Группы, каналы, service messages, исходящие сообщения, сообщения владельца и события без `sender_id` отбрасываются до policy router.

Текущая реализация принудительно работает только при `DRY_RUN=true`: она вычисляет `PASS_THROUGH`, `WOULD_REPLY` или `WOULD_BLOCK` и пишет безопасные метаданные решения в лог. Текст сообщения, полный `sender_id`, API hash и session credentials не логируются. LLM, отправка сообщений и блокировка пользователей на Stage 2 не вызываются.

Настройки listener находятся в отдельной секции `.env.example`. Списки ID задаются JSON-массивами. После заполнения тестовыми или рабочими значениями запуск выполняется отдельно:

```powershell
telegram-user-listener
```

При первом физическом запуске listener запросит телефон, код и при необходимости 2FA через скрытый ввод, затем создаст локальный session-файл. Авторизация требует интерактивного терминала. До регистрации обработчика listener проверяет, что сессия принадлежит `OWNER_USER_ID` и не является bot account. Файлы `*.session` и `*.session-journal` исключены из Git.

Матрица policy:

| Sender | Action | Profile |
|---|---|---|
| владелец / собственное сообщение | событие игнорируется | — |
| `CLOSE_RELATIVE_IDS` | `PASS_THROUGH` | `CLOSE_RELATIVE` |
| `DINESH_DOMESTIC_ID` | `WOULD_REPLY` | `DINESH_DOMESTIC` |
| `DINESH_DEBT_ID`, долг не оплачен | `WOULD_BLOCK` | `DINESH_DEBT` |
| `DINESH_DEBT_ID`, долг оплачен | `WOULD_REPLY` | `DINESH_DEBT_PAID_PROFILE` |
| `BLOCKLIST_IDS` | `WOULD_BLOCK` | `BLOCKLIST` |
| остальные | `WOULD_REPLY` | `DEFAULT` |
