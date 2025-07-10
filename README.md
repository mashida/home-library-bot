# Home Library Bot

Home Library Bot — это Telegram-бот, который считывает сведения о книге по фотографии первой страницы и сохраняет их в базу данных SQLite. Для распознавания текста используется сервис GigaChat, а для временного хранения данных — Redis.

## Переменные окружения

Для работы бота необходимы следующие переменные окружения:

- `GREEDY_BOOK_TG_TOKEN` — токен бота Telegram
- `GIGACHAT_AUTH_KEY` — ключ API GigaChat
- `ADMIN_USER_ID` — идентификатор Telegram‑пользователя, которому разрешено добавлять ключи баз данных
- `REDIS_HOST` — адрес Redis (по умолчанию `localhost`)
- `REDIS_PORT` — порт Redis (по умолчанию `6379`)
- `REDIS_DB` — номер базы Redis (по умолчанию `0`)

## Запуск локально

Установите зависимости и запустите Redis и бот:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r book_bot/requirements.txt
export GREEDY_BOOK_TG_TOKEN=<ваш токен>
export GIGACHAT_AUTH_KEY=<ваш ключ gigachat>
export ADMIN_USER_ID=<ваш telegram id>
redis-server book_bot/redis.conf &
python book_bot/telegram_bot_with_db.py
```

## Запуск в Docker

Соберите образ и запустите сервисы:

```bash
docker build -t book-bot book_bot
docker run -d --name redis -v "$PWD/book_bot/redis.conf:/usr/local/etc/redis/redis.conf" -p 6379:6379 redis:7 redis-server /usr/local/etc/redis/redis.conf
docker run -d --name book-bot --link redis:redis -e GREEDY_BOOK_TG_TOKEN=$GREEDY_BOOK_TG_TOKEN -e GIGACHAT_AUTH_KEY=$GIGACHAT_AUTH_KEY -e ADMIN_USER_ID=$ADMIN_USER_ID -e REDIS_HOST=redis -e REDIS_PORT=6379 -e REDIS_DB=0 -v "$PWD/book_bot/db:/app/db" book-bot
```

Либо запустите всё через Compose:

```bash
docker compose -f book_bot/podman-compose.yml up --build
```
