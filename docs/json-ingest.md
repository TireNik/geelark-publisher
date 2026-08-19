# JSON ingest Video Farm → GeeLark Publisher

**Ветка:** `feature/json-ingest` (от `upstream/main` после PR #5)  
**Спека VF:** Video Farm `docs/architecture/geelark-direct-send.md`

## Зачем

Конвейер Video Farm шлёт JSON задач; publisher скачивает `final.mp4` по HTTP и дальше идёт существующий `session_worker`.

Страница загрузки Excel **не меняется**: операторы по-прежнему грузят таблицу через `POST /api/upload/`. JSON — отдельный вход только для Video Farm.

## Эндпоинты

`POST /api/ingest/` — live (создаёт сессию).  
`POST /api/ingest/test/` — только проверка URL, **всегда** dry-run, сессию не создаёт. Не показан в HTML. Без заголовка токена — 401.

Заголовок: `X-Geelark-Ingest-Token` или `X-VideoFarm-Token`.  
Секрет: `VF_INGEST_TOKEN` или, если пусто, `VF_SHARELINK_TOKEN`. Пусто оба → 503.

### test / dryRun

HEAD каждого `videoUrl`, без сессии и без телефонов.  
Нужен, чтобы проверить, что GeeLark-сервер видит Video Farm, не тратя минуты прокси. На публичной странице загрузки кнопки нет.

После публикации sync статусов берёт ссылку из GeeLark `POST /open/v1/task/query` (`shareLink`). Если поле пустое при status=3 — смотрит логи `POST /open/v1/task/detail`. URL сохраняется в `PublicationTask.share_link` и уходит в VF `POST /api/public/publish/share-link` (тот же токен). Watchdog синкает ещё `submitted` и success без ссылки (6 часов).

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
