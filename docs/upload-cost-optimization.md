# Оптимизация минут GeeLark / прокси при публикации

**Статус:** поверх `feature/scheduled-phone-timeout` (2026-08)  
**Репо:** `geelark-publisher` (`publisher/session_runner.py` + helpers в `utils.py`)  
**Вне scope:** сжатие/вес роликов Video Farm **не трогаем**.

## Что уже сделал upstream

Ветка `feature/scheduled-phone-timeout` (+ youtube-reliability):

- телефоны **не** стартуют в начале сессии;
- после create API → `submitted` + sync статусов GeeLark;
- `geelark_watchdog` отменяет зависшие RPA и гасит телефоны;
- YouTube title из колонки F, `profile_number`, proxy rotate, `completed_with_errors`.

Наш PR **не откатывает** это: не стартуем/не стопаем телефоны в воркере (иначе конфликт с RPA/watchdog).

## Что добавляем

| Изменение | Зачем |
|-----------|--------|
| `session_runner`: prepare → publish | параллель 2–3; телефон не нужен на download/PUT |
| Дедуп storage по `video_url` | один PUT на YT+TT одного файла |
| Удаление temp сразу после PUT | меньше диска / orphan |
| Timeout на PUT | против «висит upload» |
| Метрики `t_*_ms`, `file_size_bytes`, `resource_url` | ловить затыки; p50/p95 в status API |
| SLA wall-clock на prepare/publish | abort зависшей задачи |
| Fix `Content-Type` в `check_phone_status` | `'application/json'` без пробелов |

## Поток

```text
prepare (parallel): download → PUT storage → wait resource → delete local mp4
publish (parallel): create RPA task → status=submitted
watchdog/sync: processing → success|error; stop phones при timeout
```

## Конфиг

См. `.env.example`: `GEELARK_MAX_PARALLEL`, `GEELARK_UPLOAD_TIMEOUT_SEC`,
`GEELARK_DOWNLOAD_TIMEOUT_SEC`, `GEELARK_TASK_SLA_SEC` (+ уже существующий
`GEELARK_TASK_TIMEOUT_MINUTES` для watchdog).
