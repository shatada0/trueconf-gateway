# TrueConf Gateway

Тестовое задание. Backend-сервис на FastAPI, который работает с TrueConf API:
ищет пользователей, создаёт видеоконференции и сохраняет их в PostgreSQL.
Токены авторизации сервис получает и обновляет сам.

## Как запустить

1. Сначала поднять мок TrueConf на порту 8080 (в его папке):

```bash
docker compose up -d --build
```

2. Потом поднять сервис (из этой папки):

```bash
docker compose up -d --build
```

Поднимутся два контейнера: API и PostgreSQL.

- API: http://localhost:8000
- Swagger: http://localhost:8000/docs

Все настройки в файле `.env`.

## Примеры запросов

```bash
# поиск пользователей
curl "localhost:8000/users?query=иванов"

# создать конференцию
curl -X POST localhost:8000/conferences \
  -H 'Content-Type: application/json' \
  -d '{"title":"Планёрка","participant_ids":["a.ivanov@company","p.petrov@company"]}'

# список сохранённых конференций
curl localhost:8000/conferences

# одна конференция по id
curl localhost:8000/conferences/<id>
```

## Проверка автообновления токена

```bash
curl "localhost:8000/users?query=иванов"          # обычный запрос
curl -X POST localhost:8080/debug/expire-tokens   # инвалидировать токены на моке
curl "localhost:8000/users?query=иванов"          # сервис сам обновит токен
```

## Тесты

```bash
pip install -r requirements-dev.txt
pytest
```

Внешние сервисы для тестов не нужны, TrueConf в них заменён заглушкой.

## Кратко, как это работает

- Токены хранятся в PostgreSQL, таблица tokens, всегда одна запись.
- Перед запросом сервис проверяет срок жизни access_token и при
  необходимости обновляет его через /refresh. Новый refresh_token
  тоже сохраняется, старый после обмена перестаёт работать.
- Если TrueConf всё равно ответил 401 - сервис обновляет токен и
  повторяет запрос один раз.
- Обновление идёт под asyncio.Lock, чтобы два одновременных запроса
  не потратили один refresh_token дважды.
- Если refresh не сработал, сервис заново авторизуется через /token.
- Таблицы создаются миграцией Alembic при старте.
- При ошибках TrueConf сервис отвечает 502, ошибка 422 про
  несуществующих участников пробрасывается как есть.
