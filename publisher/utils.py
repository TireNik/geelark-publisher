import os
import requests
import openpyxl
import time
import uuid
import random
from config import settings
from .models import UploadSession
from datetime import datetime, timedelta
from django.utils import timezone
from django.utils.timezone import make_aware
from django.core.exceptions import ValidationError


def session_worker(session_id):
    """
    Один воркер на сессию.
    Обрабатывает задачи синхронно, по одной.
    """
    session = UploadSession.objects.get(id=session_id)
    tasks = session.tasks.filter(status='pending').order_by('id')
    video_cache = {} # КЭШ
    downloaded_files = [] # Для очистки в конце
    started_phones = []  # Список телефонов, которые мы запустили

    # Получаем уникальные env_id из задач
    env_ids = set(validate_profile_id(task.profile_id) for task in tasks)
    # Запускаем каждый уникальный телефон перед началом работы
    for env_id in env_ids:
        try:
            print(f"\n!!!!!!! Проверяем статус телефона {env_id}... !!!!!!!")
            phone_status = check_phone_status(env_id)

            if phone_status['is_running']:
                print(f"Телефон {env_id} уже запущен")
            else:
                print(f"Телефон {env_id} выключен, запускаем...")
                start_cloud_phone(env_id)
                started_phones.append(env_id)
                # Даем время на запуск
                time.sleep(8)
        except Exception as e:
            print(f"  ❌ Ошибка с телефоном {env_id}: {e}")
            # Помечаем все задачи этого телефона как ошибки
            for task in tasks:
                if task.profile_id == env_id:
                    task.status = 'error'
                    task.error_message = f"Не удалось запустить телефон: {e}"
                    task.processed_at = datetime.now() #timezone.now()
                    task.save()
            # Пропускаем обработку задач этого телефона
            tasks = tasks.exclude(profile_id=env_id)

    for task in tasks:
        video = None

        try:
            print(f'начало task')
            # Обрабатываем одну задачу
            task.status = 'processing'
            task.save()

            # 1. Скачать видео (Яндекс.Диск или прямая HTTP/HTTPS ссылка), с проверкой КЭШа
            if task.video_url in video_cache:
                video_path = video_cache[task.video_url]
                print(f'видео взято из кэша')
            else:
                print(f'качаем видео')
                video_path = download_video(task)
                print(f'скачали видео')
                video_cache[task.video_url] = video_path
                downloaded_files.append(video_path)
                print(f'записали в кэш')

            task.status = 'sending'
            task.save()
            # 2. Отправить в Geelark
            result = send_to_geelark(
                profile_id=task.profile_id,
                video_path=video_path,
                #title=task.title, Больше без названия
                comment=task.comment,
                publish_time=task.publish_time,
                social_network=task.social_network
            )
            print(f'отправили geelark')

            # 3. Успех
            task.status = 'success'
            task.processed_at = datetime.now() #timezone.now()
            print(f'установили статус, сохранили')
            task.save()
            session.save()

        except Exception as e:
            # Ошибка
            task.status = 'error'
            task.error_message = str(e)
            task.processed_at = datetime.now()
            task.save()
            session.save()

        time.sleep(1)  # Пауза между задачами

    # КОНЕЦ СЕССИИ - выключаем все запущенные телефоны
    if started_phones:
        print(f"\n📞 Останавливаем телефоны, запущенные этой сессией...")
        for env_id in started_phones:
            try:
                stop_cloud_phone(env_id)
            except Exception as e:
                print(f"  ❌ Ошибка при остановке телефона {env_id}: {e}")

    # КОНЕЦ СЕССИИ - удаляем все скачанные файлы
    for video_path in downloaded_files:
        try:
            if os.path.exists(video_path):
                os.remove(video_path)
                print(f'Удален файл: {video_path}')
        except Exception as e:
            print(f'Ошибка при удалении: {e}')

    video_cache.clear()
    session.status = 'completed'
    session.save()
    print(f'Сессия ID:{session.id} завершена')

def parse_excel_file(file):
    """
    Парсит Excel файл и возвращает список словарей с данными.
    ВСЕ ПОЛЯ ОБЯЗАТЕЛЬНЫ ДЛЯ ЗАПОЛНЕНИЯ!
    Если хоть одно поле пустое - строка пропускается с ошибкой.

    Структура Excel:
    A: Номер профиля (обязательно) - может быть в формате "1/605043047633256588" или просто "605043047633256588"
    B: Название соц. сети (обязательно)
    C: Ссылка на видео (обязательно)
    D: Комментарий к видео (обязательно) РАНЬШЕ БЫЛО НАЗВАНИЕ, ТЕПЕРЬ ТОЛЬКО КОММЕНТАРИЙ
    E: Время выкладывания (обязательно)
    """
    print(">>> parse_excel_file вызвана")
    wb = openpyxl.load_workbook(file)
    ws = wb.active

    rows_data = []
    errors = []

    # Маппинг колонок (индекс -> английское название)
    column_map = {
        1: 'profile_id',
        2: 'social_network',
        3: 'video_url',
        #4: 'title', Больше неактивно
        4: 'comment',
        5: 'publish_time',
    }

    # Проходим по строкам (начинаем с 2, т.к. 1-я строка - заголовки)
    for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        if not any(row):
            continue

        row_dict = {}
        row_errors = []

        # Парсим все поля
        for col_idx, field_name in column_map.items():
            value = row[col_idx - 1]

            # Пропускаем проверку на пустоту для publish_time (обработаем позже рандомом)
            if field_name == 'publish_time':
                row_dict[field_name] = value if value is not None else None
                continue

            if value is None or (isinstance(value, str) and not value.strip()):
                row_errors.append(f"Поле '{field_name}' обязательно для заполнения")
                row_dict[field_name] = None
            else:
                if isinstance(value, str):
                    value = value.strip()
                row_dict[field_name] = value

        if row_errors:
            errors.append({
                'row': row_idx,
                'errors': row_errors,
                'data': row_dict
            })
            continue

        # Обработка profile_id: из "1/605043047633256588" достаем "605043047633256588"
        print(f"row dict profile id -> {row_dict['profile_id']}")
        profile_id = validate_profile_id(row_dict['profile_id'])
        if not profile_id:
            errors.append({
                'row': row_idx,
                'errors': [f'Номер профиля должен содержать только цифры. Получено: {profile_id}'],
                'data': row_dict
            })
            continue

        social_network = convert_social_networks(row_dict['social_network'])
        if not social_network:
            errors.append({
                'row': row_idx,
                'errors': [f"Неподдерживаемая соцсеть: {row_dict['social_network']}"],
                'data': row_dict
            })
            continue

        video_url = row_dict['video_url']
        if not validate_video_url(video_url):
            errors.append({
                'row': row_idx,
                'errors': [
                    f"Невалидная ссылка на видео (нужен Яндекс.Диск или HTTP/HTTPS URL): {video_url}"
                ],
                'data': row_dict
            })
            continue

        try:
            print(f"Перед вызовом parse_publish_time, значение publish_time: {row_dict['publish_time']}")
            publish_time = parse_publish_time(row_dict['publish_time'])
            if publish_time < datetime.now(): #timezone.now():
                errors.append({
                    'row': row_idx,
                    'errors': [
                        f"Время публикации уже прошло: {publish_time.strftime('%d.%m.%Y %H:%M')}. Текущее время: {datetime.now().strftime('%d.%m.%Y %H:%M')}"],
                    'data': row_dict
                })
                continue
        except Exception as e:
            errors.append({
                'row': row_idx,
                'errors': [f"Ошибка парсинга времени: {str(e)}"],
                'data': row_dict
            })
            continue

        comment = row_dict['comment']
        if not comment or not str(comment).strip():
            errors.append({
                'row': row_idx,
                'errors': ["comment не может быть пустым"],
                'data': row_dict
            })
            continue

        # Всё ок
        rows_data.append({
            'profile_id': profile_id,
            'social_network': social_network,
            'video_url': video_url,
            #'title': row_dict['title'], Больше нет названия
            'comment': str(comment).strip(),
            'publish_time': publish_time,
            'raw_row': row_idx,
        })

    #if errors and not rows_data:
    #    error_messages = [f"Строка {err['row']}: {', '.join(err['errors'])}" for err in errors[:10]]
    #    raise ValidationError("Нет валидных строк в файле:\n" + "\n".join(error_messages))
    #
    #if errors:
    #    print(f"Внимание: {len(errors)} строк пропущено")
    if errors and not rows_data:
        print(f"ВНИМАНИЕ: Нет валидных строк. {len(errors)} строк с ошибками")

    if errors:
        print(f"Внимание: {len(errors)} строк пропущено")

    return rows_data, errors


def validate_profile_id(value):
    """
    Парсит номер профиля и приводит его к адекватному виду
    """
    profile_id = str(value).strip()
    if '/' in profile_id:
        print(f' if /')
        # Берем часть после слеша
        profile_id = profile_id.split('/')[-1].strip()
        print(f'взяли часть после слеша -> {profile_id}')
    else:
        print(f' не вошли в if / ')
        profile_id = profile_id
    return profile_id


def parse_publish_time(value):
    """
    Парсит время публикации.
    Поддерживает:
    - time объект из Excel (10:10:00)
    - строка с временем "10:10:00" или "10:10"
    - None или пустая строка — тогда генерируется рандомное время > сейчас

    Время привязывается к сегодняшней дате.
    """
    print(">>> parse_publish_time вызвана")
    today = datetime.now().date()
    now = datetime.now()
    print(f'зашло value - {value}')
    # Если значения нет - генерируем рандомное время в будущем
    if value is None or value == "":
        print(f'value is None or value == "" ')
        random_minutes = random.randint(1, 180)  # от 1 до 180 минут вперёд
        random_dt = now + timedelta(minutes=random_minutes)
        return random_dt

    # Проверяем, есть ли у объекта атрибуты hour и minute (это time object)
    if hasattr(value, 'hour') and hasattr(value, 'minute'):
        dt = datetime.combine(today, value)
        return dt #make_aware(dt)

    # Если строка с временем
    if isinstance(value, str):
        value = value.strip()

        # Формат "10:10:00" или "10:10"
        if ':' in value:
            parts = value.split(':')
            hour = int(parts[0])
            minute = int(parts[1])
            second = int(parts[2]) if len(parts) > 2 else 0
            dt = datetime.combine(today, time(hour, minute, second))
            return dt #make_aware(dt)

    raise ValueError(f"Не удалось распарсить время: {value}. Используйте формат ЧЧ:ММ:СС")


def convert_social_networks(network_name):
    """
    Функция конвертации наименований социальных сетей
    """
    network_map = {
        'инстаграм': 'Instagram',
        'instagram': 'Instagram',
        'inst': 'Instagram',
        'ig': 'Instagram',

        'ютуб': 'YouTube',
        'youtube': 'YouTube',
        'yt': 'YouTube',
        'yT': 'YouTube',
        'Ютуб': 'YouTube',

        'тикток': 'TikTok',
        'tiktok': 'TikTok',
        'tt': 'TikTok',
        'TikTok': 'TikTok',
        'ТикТок': 'TikTok',
    }

    normalized = network_name.lower().strip()
    return network_map.get(normalized)


def validate_yandex_disk_url(url):
    """Проверяет, что ссылка ведет на Яндекс Диск."""
    return is_yandex_disk_url(url)


def is_yandex_disk_url(url):
    """True, если URL — публичная ссылка Яндекс.Диска."""
    if not url:
        return False
    text = str(url).strip().lower()
    return 'disk.yandex.ru' in text or 'yadi.sk' in text


def is_direct_http_video_url(url):
    """
    True для прямой HTTP(S) ссылки на файл (например Video Farm signed URL).
    Яндекс.Диск сюда не входит — для него отдельный путь через API.
    """
    if not url:
        return False
    text = str(url).strip()
    if is_yandex_disk_url(text):
        return False
    lower = text.lower()
    return lower.startswith('https://') or lower.startswith('http://')


def validate_video_url(url):
    """Принимает Яндекс.Диск или прямой HTTP(S) URL."""
    return is_yandex_disk_url(url) or is_direct_http_video_url(url)


def get_yandex_direct_download_url(public_url):
    """
    Получает прямую ссылку для скачивания с Яндекс Диска.
    Нужно для скачивания видео.
    """

    params = {
        'public_key': public_url
    }
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = requests.get(settings.YANDEX_URL, params=params, timeout=30)
            response.raise_for_status()

            data = response.json()

            # Прямая ссылка на скачивание
            download_url = data.get('file')

            if not download_url:
                raise Exception("Не удалось получить прямую ссылку на файл")

            return download_url

        except requests.exceptions.RequestException as e:
            if attempt == max_retries - 1:
                raise Exception(f"Ошибка при запросе к Яндекс Диску после {max_retries} попыток: {str(e)}")

            print(f"Попытка {attempt + 1} не удалась, повтор через 2 секунды...")
            import time
            time.sleep(2)


def _task_save_path(task) -> str:
    temp_dir = settings.TEMP_VIDEO_DIR
    os.makedirs(temp_dir, exist_ok=True)
    return os.path.join(temp_dir, f'task_{task.id}.mp4')


def _stream_download_to_file(url: str, save_path: str, timeout: int = 120) -> str:
    """Скачивает URL потоком на диск. Возвращает save_path."""
    response = requests.get(url, stream=True, timeout=timeout, allow_redirects=True)
    response.raise_for_status()
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    with open(save_path, 'wb') as f:
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)
    if not os.path.isfile(save_path) or os.path.getsize(save_path) == 0:
        raise Exception(f"Скачанный файл пуст или отсутствует: {save_path}")
    return save_path


def download_from_yandex(task) -> str:
    """
    Функция загрузки видео с Яндекс-диска.
    Скачивает видео по URL во временную папку.
    Возвращает путь к скачанному файлу.
    """

    task.status = 'downloading'
    task.save()
    public_url = task.video_url
    # 1. Получаем прямую ссылку
    print(f'получаем прямую ссылку. Task ID{task.id}')
    direct_url = get_yandex_direct_download_url(public_url)
    print(f'получили прямую ссылку, начинаем скачивание.')
    save_path = _task_save_path(task)
    # 2. Скачиваем файл
    try:
        result = _stream_download_to_file(direct_url, save_path, timeout=60)
        print(f'скачали файл. path - {result}')
        return result
    except requests.exceptions.RequestException as e:
        raise Exception(f"Ошибка при скачивании видео: {str(e)}")


def download_from_http(task) -> str:
    """
    Скачивает видео по прямой HTTP(S) ссылке (Video Farm signed URL и т.п.).
    Возвращает путь к скачанному файлу.
    """
    task.status = 'downloading'
    task.save()
    url = str(task.video_url).strip()
    print(f'скачиваем HTTP видео. Task ID={task.id} url={url[:120]}')
    save_path = _task_save_path(task)
    try:
        result = _stream_download_to_file(url, save_path, timeout=180)
        print(f'скачали HTTP файл. path - {result}')
        return result
    except requests.exceptions.RequestException as e:
        raise Exception(f"Ошибка при HTTP-скачивании видео: {str(e)}")


def download_video(task) -> str:
    """Диспетчер: Яндекс.Диск или прямой HTTP(S)."""
    url = task.video_url
    if is_yandex_disk_url(url):
        return download_from_yandex(task)
    if is_direct_http_video_url(url):
        return download_from_http(task)
    raise Exception(
        f"Неподдерживаемый URL видео (нужен Яндекс.Диск или HTTP/HTTPS): {url}"
    )


def delete_video(file_path: str) -> bool:
    """Удаляет временный видеофайл"""
    if os.path.exists(file_path):
        os.remove(file_path)
        return True
    return False


def get_upload_url(file_type: str = "mp4") -> dict:
    """Шаг 1: Получаем uploadUrl и resourceUrl от Geelark"""
    api_url = "https://openapi.geelark.com/open/v1/upload/getUrl"

    trace_id = str(uuid.uuid4()).upper()
    token = settings.GEELARK_TOKEN

    headers = {
        'Content-Type': 'application/json',
        'traceId': trace_id,
        'Authorization': f'Bearer {token}'
    }

    payload = {'fileType': file_type}

    response = requests.post(api_url, json=payload, headers=headers, timeout=30)
    response.raise_for_status()

    result = response.json()

    if result.get('code') != 0:
        raise Exception(f"Ошибка получения uploadUrl: {result.get('msg')}")

    upl = result['data']['uploadUrl']
    rurl = result['data']['resourceUrl']
    print(f'uploadUrl: {upl}')
    print(f'resourceUrl: {rurl}')
    return {
        'uploadUrl': result['data']['uploadUrl'],
        'resourceUrl': result['data']['resourceUrl']
    }


def upload_video_to_storage(video_path: str, upload_url: str) -> None:
    """Шаг 2: Загружаем видео в хранилище Geelark (PUT запрос)"""
    with open(video_path, 'rb') as f:
        # ВАЖНО: НИКАКИХ ДОПОЛНИТЕЛЬНЫХ ЗАГОЛОВКОВ!
        response = requests.put(upload_url, data=f)

    if response.status_code != 200:
        print(f"  ❌ Ошибка загрузки!")
        print(f"  Status code: {response.status_code}")
        print(f"  Response: {response.text[:500]}")
        raise Exception(f"Ошибка загрузки видео в хранилище: {response.status_code} - {response.text}")


def add_publish_task(env_id: str, resource_url: str, schedule_at: int, comment: str = None, description: str = None,
                     social_network: str = None) -> str:
    """Универсальная задача для любой соцсети через /task/add"""

    api_url = "https://openapi.geelark.com/open/v1/task/add"
    trace_id = str(uuid.uuid4()).upper()
    token = settings.GEELARK_TOKEN

    headers = {
        'Content-Type': 'application/json',
        'traceId': trace_id,
        'Authorization': f'Bearer {token}'
    }

    # Формируем базовую задачу
    task_data = {
        "scheduleAt": schedule_at,
        "envId": str(env_id),
        "video": resource_url
    }

    # Добавляем описание (для всех соцсетей)
    if description and len(description) <= 4000:
        task_data["videoDesc"] = description
    elif description:
        print(f"  ⚠️ Описание слишком длинное ({len(description)} > 4000), не будет отправлено")

    # Для YouTube добавляем comment
    if social_network and social_network.lower() == 'youtube' and comment:
        task_data["comment"] = comment[:100]

    payload = {
        "taskType": 1,
        "list": [task_data],
        "planName": f"Auto publish {social_network or 'video'} {int(time.time())}"
    }

    # Отправляем запрос
    response = requests.post(api_url, json=payload, headers=headers, timeout=60)
    response.raise_for_status()

    result = response.json()

    if result.get('code') != 0:
        raise Exception(f"Ошибка создания задачи: {result.get('msg')}")

    task_ids = result.get('data', {}).get('taskIds', [])
    if not task_ids:
        raise Exception("Не получен taskId от Geelark")

    return task_ids[0]


def add_tiktok_task(env_id: str, resource_url: str, schedule_at: int, description: str = None) -> str:
    """Создание задачи для TikTok (через универсальный /task/add)"""
    api_url = "https://openapi.geelark.com/open/v1/task/add"
    print(f'api url completed')
    trace_id = str(uuid.uuid4()).upper()
    token = settings.GEELARK_TOKEN
    print(f'token + id = {token}, {trace_id}')
    headers = {
        'Content-Type': 'application/json',
        'traceId': trace_id,
        'Authorization': f'Bearer {token}'
    }
    print(f'headers? {headers}')
    # Формируем задачу строго по документации
    task_data = {
        "scheduleAt": schedule_at,
        "envId": str(env_id),
        "video": resource_url
    }
    print(f'Имеется описание description.')
    print(f'DESCRIPTION TIKTOK -> {description}')
    # Добавляем описание, ТОЛЬКО если оно есть и проходит валидацию
    if description and len(description) <= 4000:
        print(f'description подходит под параметры TikTok - направляем')
        task_data["videoDesc"] = description
    elif description:
        print(f"  ⚠️ Описание ({len(description)} > 4000), не будет отправлено")

    payload = {
        "taskType": 1,
        "list": [task_data]
    }

    print(f'description completed')
    # Добавляем planName (опционально)
    payload["planName"] = f"Auto publish {int(time.time())}"
    print(f'payload oke - {payload}')
    response = requests.post(api_url, json=payload, headers=headers, timeout=60)
    response.raise_for_status()
    print(f'response - {response}')
    result = response.json()
    print(f'result - {result}')
    if result.get('code') != 0:
        raise Exception(f"Ошибка создания задачи: {result.get('msg')}")

    task_ids = result.get('data', {}).get('taskIds', [])
    if not task_ids:
        raise Exception("Не получен taskId от Geelark")

    return task_ids[0]


def add_instagram_task(env_id: str, resource_url: str, schedule_at: int, description: str = None) -> str:
    """Создание задачи для Instagram Reels"""
    api_url = "https://openapi.geelark.com/open/v1/rpa/task/instagramPubReels"
    trace_id = str(uuid.uuid4()).upper()
    token = settings.GEELARK_TOKEN

    headers = {
        'Content-Type': 'application/json',
        'traceId': trace_id,
        'Authorization': f'Bearer {token}'
    }

    # Проверка на пустое описание
    if not description or not description.strip():
        description = "#reels #instagram"
        print("⚠️ Описание Instagram пустое, установлено значение по умолчанию")
    # Обрезка до лимита 2200 символов
    if len(description) > 2200:
        print(f"⚠️ Описание Instagram слишком длинное ({len(description)} > 2200), будет обрезано")
        description = description[:2200]
    print(f'DESCRIPTION INSTAGRAM - {description}')
    # По документации: video - это массив строк, даже если одно видео
    payload = {
        "scheduleAt": schedule_at,
        "id": str(env_id),
        "description": description,
        "video": [resource_url]  # Массив, даже если одно видео!
    }
    print(f'payload okey -> {payload}')
    # Добавляем опциональные поля
    #payload["name"] = f"Auto publish Instagram {int(time.time())}"

    response = requests.post(api_url, json=payload, headers=headers, timeout=60)
    print(f'response instagramm - {response}')
    response.raise_for_status()
    result = response.json()
    print(f'result? instagramm {result}')
    if result.get('code') != 0:
        raise Exception(f"Ошибка создания Instagram задачи: {result.get('msg')}")

    task_id = result.get('data', {}).get('taskId')
    if not task_id:
        raise Exception("Не получен taskId от Geelark")

    return task_id


def add_youtube_task(env_id: str, resource_url: str, schedule_at: int, comment: str) -> str:
    """Создание задачи для YouTube Video"""
    api_url = "https://openapi.geelark.com/open/v1/rpa/task/youtubePubShort"
    trace_id = str(uuid.uuid4()).upper()
    token = settings.GEELARK_TOKEN

    headers = {
        'Content-Type': 'application/json',
        'traceId': trace_id,
        'Authorization': f'Bearer {token}'
    }
    safe_title = comment if comment and comment.strip() else "Auto publish"

    payload = {
        "scheduleAt": schedule_at,
        "id": str(env_id),
        "title": safe_title,  # Лимит 100 символов
        #"description": description[:5000] if description else "",  # Лимит 5000 символов
        "video": resource_url,
        "sameStyleVoice": 0,
        "originalVoice": 0
    }

    # Добавляем опциональные поля
    #payload["name"] = f"Auto publish YouTube {int(time.time())}"

    response = requests.post(api_url, json=payload, headers=headers, timeout=60)
    response.raise_for_status()
    result = response.json()
    print(f'result?? {result}')

    if result.get('code') != 0:
        raise Exception(f"Ошибка создания YouTube задачи: {result.get('msg')}")

    task_id = result.get('data', {}).get('taskId')
    if not task_id:
        raise Exception("Не получен taskId от Geelark")

    return task_id


#def add_publish_task(env_id: str, resource_url: str, schedule_at: int, description: str = None) -> str:
#    """
#    Шаг 3: Создаем задачу на публикацию видео
#    taskType: 1 - Publish video
#    """
#    api_url = "https://openapi.geelark.com/open/v1/task/add"
#    print(f'api url completed')
#    trace_id = str(uuid.uuid4()).upper()
#    token = settings.GEELARK_TOKEN
#    print(f'token + id = {token}, {trace_id}')
#    headers = {
#        'Content-Type': 'application/json',
#        'traceId': trace_id,
#        'Authorization': f'Bearer {token}'
#    }
#    print(f'headers? {headers}')
#    # Формируем задачу строго по документации
#    task_data = {
#        "scheduleAt": schedule_at,
#        "envId": str(env_id),  # <-- ПРИВОДИМ К СТРОКЕ! ЭТО ВАЖНО!
#        "video": resource_url
#    }
#
#    # Добавляем описание, ТОЛЬКО если оно есть и проходит валидацию
#    if description and len(description) <= 4000:
#        task_data["videoDesc"] = description
#    elif description:
#        print(f"  ⚠️ Описание太长 ({len(description)} > 4000), не будет отправлено")
#
#    payload = {
#        "taskType": 1,
#        "list": [task_data]
#    }
#
#    print(f'description completed')
#    # Добавляем planName (опционально)
#    payload["planName"] = f"Auto publish {int(time.time())}"
#    print(f'payload oke - {payload}')
#    response = requests.post(api_url, json=payload, headers=headers, timeout=60)
#    response.raise_for_status()
#    print(f'response - {response}')
#    result = response.json()
#    print(f'result - {result}')
#    if result.get('code') != 0:
#        raise Exception(f"Ошибка создания задачи: {result.get('msg')}")
#
#    task_ids = result.get('data', {}).get('taskIds', [])
#    if not task_ids:
#        raise Exception("Не получен taskId от Geelark")
#
#    return task_ids[0]


def send_to_geelark(profile_id: str, video_path: str, comment: str, publish_time, social_network: str):
    """
    Полный цикл отправки в Geelark
    profile_id - это envId (ID облачного телефона)
    social_network - Instagram, YouTube, TikTok
    """
    # 1. Получаем uploadUrl
    print(f"Получаем uploadUrl от Geelark...")
    urls = get_upload_url('mp4')

    # 2. Загружаем видео в хранилище
    print(f"Загружаем видео в хранилище Geelark...")
    upload_video_to_storage(video_path, urls['uploadUrl'])
    print(f" >>>> Видео загружено в хранилище")

    # Ждем, пока файл станет доступен
    print(f" >>>> Ожидаем доступности файла...")
    time.sleep(3)

    # 3. Создаем задачу на публикацию в зависимости от соцсети
    print(f" >>> Создаем задачу публикации в Geelark для {social_network}...")
    schedule_timestamp = int(publish_time.timestamp()) if publish_time else int(time.time())
    print(f' >>> получили таймстамп - {schedule_timestamp}')


    # Маршрутизация по соцсетям
    if social_network.lower() == 'instagram':
        print(f'Instagramm task, lets Go')
        task_id = add_instagram_task(
            env_id=profile_id,
            resource_url=urls['resourceUrl'],
            schedule_at=schedule_timestamp,
            description=comment
        )
    elif social_network.lower() == 'youtube':
        print(f'Получили данные. ПИШУ ИХ:')
        print(f'TITLE - {comment}')
        print(f'EVN ID - {profile_id}')
        if len(str(comment)) > 100:
            comment = str(comment)[:99]  # Берём первые 99 символов
            print(f"⚠️ YouTube: комментарий был сокращён с {len(str(comment))} до 100 символов")
            #raise ValueError(
            #    f"YouTube: название видео слишком длинное ({len(str(comment))} > 100 символов). Сократите название до 100 символов.")
        task_id = add_youtube_task(
            env_id=profile_id,
            resource_url=urls['resourceUrl'],
            schedule_at=schedule_timestamp,
            comment=comment,
            #description=title
            #description=comment
        )
    else:  # TikTok (по умолчанию)
        print(f'TikTok task lets GO')
        task_id = add_tiktok_task(
            env_id=profile_id,
            resource_url=urls['resourceUrl'],
            schedule_at=schedule_timestamp,
            description=comment
        )

    #task_id = add_publish_task(
    #    env_id=profile_id,
    #    resource_url=urls['resourceUrl'],
    #    schedule_at=schedule_timestamp,
    #    title=title,
    #    description=comment,
    #    social_network=social_network
    #)
    print(f"✅ Задача создана, taskId: {task_id}")

    return {
        'success': True,
        'task_id': task_id,
        'resource_url': urls['resourceUrl']
    }


def start_cloud_phone(env_id: str) -> bool:
    """
    Запускает облачный телефон по ID
    """
    api_url = "https://openapi.geelark.com/open/v1/phone/start"
    trace_id = str(uuid.uuid4()).upper()
    token = settings.GEELARK_TOKEN

    headers = {
        'Content-Type': 'application/json',
        'traceId': trace_id,
        'Authorization': f'Bearer {token}'
    }

    payload = {
        "ids": [str(env_id)]
    }

    print(f"  Запускаем облачный телефон {env_id}...")
    response = requests.post(api_url, json=payload, headers=headers, timeout=30)
    response.raise_for_status()

    result = response.json()

    if result.get('code') != 0:
        raise Exception(f"  Ошибка запуска телефона: {result.get('msg')}")

    data = result.get('data', {})
    success_amount = data.get('successAmount', 0)

    if success_amount > 0:
        print(f"  Телефон {env_id} успешно запущен")
        return True
    else:
        fail_details = data.get('failDetails', [])
        if fail_details:
            raise Exception(f"  Не удалось запустить телефон: {fail_details[0].get('msg')}")
        return False


def check_phone_status(env_id: str) -> dict:
    """
    Проверяет статус облачного телефона
    """
    api_url = "https://openapi.geelark.com/open/v1/phone/list"
    trace_id = str(uuid.uuid4()).upper()
    token = settings.GEELARK_TOKEN

    headers = {
        'Content-Type': 'application / json',
        'traceId': trace_id,
        'Authorization': f'Bearer {token}'
    }

    payload = {
        "ids": [str(env_id)]
    }

    response = requests.post(api_url, json=payload, headers=headers, timeout=30)
    response.raise_for_status()

    result = response.json()

    if result.get('code') != 0:
        raise Exception(f"  Ошибка проверки статуса: {result.get('msg')}")

    items = result.get('data', {}).get('items', [])
    if not items:
        raise Exception(f"  Телефон {env_id} не найден")

    phone = items[0]
    status = phone.get('status')  # 0 - Started, 1 - Starting, 2 - Shut down

    return {
        'id': phone.get('id'),
        'status': status,
        'status_text': ['Запущен', 'Запускается', 'Выключен'][status] if status in [0, 1, 2] else 'Неизвестно',
        'serial_name': phone.get('serialName'),
        'is_running': status == 0
    }


def stop_cloud_phone(env_id: str) -> bool:
    """
    Останавливает облачный телефон по ID
    """
    api_url = "https://openapi.geelark.com/open/v1/phone/stop"
    trace_id = str(uuid.uuid4()).upper()
    token = settings.GEELARK_TOKEN

    headers = {
        'Content-Type': 'application/json',
        'traceId': trace_id,
        'Authorization': f'Bearer {token}'
    }

    payload = {
        "ids": [str(env_id)]
    }

    print(f"  📞 Останавливаем облачный телефон {env_id}...")
    response = requests.post(api_url, json=payload, headers=headers, timeout=30)
    response.raise_for_status()

    result = response.json()

    if result.get('code') != 0:
        raise Exception(f"Ошибка остановки телефона: {result.get('msg')}")

    data = result.get('data', {})
    success_amount = data.get('successAmount', 0)

    if success_amount > 0:
        print(f"  ✅ Телефон {env_id} успешно остановлен")
        return True
    else:
        fail_details = data.get('failDetails', [])
        if fail_details:
            print(f"  ⚠️ Не удалось остановить телефон: {fail_details[0].get('msg')}")
        return False


def stop_cloud_phones(env_ids: list) -> None:
    """
    Останавливает несколько облачных телефонов
    """
    for env_id in env_ids:
        try:
            stop_cloud_phone(env_id)
        except Exception as e:
            print(f"  ❌ Ошибка при остановке телефона {env_id}: {e}")