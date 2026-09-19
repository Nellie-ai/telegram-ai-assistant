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
