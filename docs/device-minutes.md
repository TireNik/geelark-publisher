# Минуты облачного телефона

Ветка влита в `main` (`c5c0cf5`). Прод 77.222 выкатили 2026-08-20 аддитивно (бэкап `.bak-device-minutes-20260820-121041`, rebuild `app`+`watchdog`, миграции 0011/0012).

Полный разбор и чеклист: Video Farm `docs/architecture/geelark-device-minutes.md`.

Сделано в этом репо и на проде 77.222:

- Excel (`POST /api/upload/`) и VF (`POST /api/ingest/`) → один `session_worker`: один PUT OSS на `video_url`.
- `phone_guard`: не `stop`, пока на том же `profile_id` есть running RPA или `prepared`/`pending` с `publish_time` в окне `GEELARK_DISPATCH_LEAD_SECONDS` (две сети на одном устройстве без второго boot).
- Watchdog синкает только живые задачи; success без ссылки 6 часов не крутим.
- `geelark_rpa_cost_sec` из `task/query.cost`.
- GeeLark `shareLink` из контура убран: не резолвим, не отдаём в API, не POST в VF. Статистика — harvest `#vf_` / ig-stats.
- `geelark_dispatch`: один RPA на `profile_id` (вторая сеть ждёт `prepared`).
- Ingest сохраняет `externalId` (`vf-entry-…`) для статусов в VF.
