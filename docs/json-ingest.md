# JSON ingest Video Farm → GeeLark Publisher

**Ветка:** `feature/json-ingest` (от `upstream/main` после PR #5)  
**Спека VF:** Video Farm `docs/architecture/geelark-direct-send.md`

## Зачем

Конвейер больше не генерирует Excel как основной путь. Video Farm шлёт JSON задач; publisher скачивает `final.mp4` по HTTP (как уже умеет `download_from_http`) и дальше идёт существующий `session_worker`.

Excel `POST /api/upload/` не удаляем.

## Эндпоинт

`POST /api/ingest/`

Заголовок: `X-Geelark-Ingest-Token` или `X-VideoFarm-Token`.  
Секрет: `VF_INGEST_TOKEN` или, если пусто, `VF_SHARELINK_TOKEN`.

### dryRun

`{"dryRun": true, "items":[...]}` — HEAD каждого `videoUrl`, без сессии и без телефонов.  
Нужен, чтобы проверить, что GeeLark-сервер видит Video Farm, не тратя минуты прокси.

### live

Создаёт `UploadSession` (`document=null`) и `PublicationTask`, стартует `session_worker`.

`publish_time` = сейчас, если не передан.

## YouTube description

`add_youtube_task` должен передавать `description` из `comment` (лимит 5000). Раньше поле было закомментировано — описание из VF на Shorts не уезжало.

## Env

```
VF_INGEST_TOKEN=
# fallback: VF_SHARELINK_TOKEN
```
