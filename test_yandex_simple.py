import os
import sys
import django

sys.path.append('/home/max/PycharmProjects/automatic_publisher')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from publisher.utils import get_yandex_direct_download_url, download_from_yandex
from publisher.models import PublicationTask


def test_direct_url():
    """Тест получения прямой ссылки"""
    public_url = "https://disk.yandex.ru/i/FGShQav9zoizug"

    print("=" * 60)
    print("🧪 ТЕСТ 1: get_yandex_direct_download_url()")
    print("=" * 60)
    print(f"Публичная ссылка: {public_url}")
    print("-" * 60)

    try:
        direct_url = get_yandex_direct_download_url(public_url)
        print(f"✅ Прямая ссылка получена!")
        print(f"   {direct_url[:100]}...")
        return True
    except Exception as e:
        print(f"❌ ОШИБКА: {e}")
        return False


def test_download(task):
    """Тест скачивания видео"""
    save_path = f"/tmp/test_task_{task.id}.mp4"

    print("\n" + "=" * 60)
    print("🧪 ТЕСТ 2: download_from_yandex()")
    print("=" * 60)
    print(f"Ссылка скачивания: {task.video_url}")
    print(f"Путь сохранения: {save_path}")
    print("-" * 60)

    try:
        # Вызываем реальную функцию
        result_path = download_from_yandex(task)

        # Проверяем, что файл создался
        if os.path.exists(result_path):
            file_size = os.path.getsize(result_path)
            print(f"✅ Файл скачан успешно!")
            print(f"   Путь: {result_path}")
            print(f"   Размер: {file_size} байт ({file_size / 1024 / 1024:.2f} MB)")

            # Удаляем тестовый файл
            os.remove(result_path)
            print(f"   Тестовый файл удален")
            return True
        else:
            print(f"❌ Файл не найден по пути: {result_path}")
            return False

    except Exception as e:
        print(f"❌ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
        return False



if __name__ == "__main__":
    task = PublicationTask.objects.first()
    print("\n" + "🔵" * 30)
    print("ТЕСТИРОВАНИЕ РЕАЛЬНЫХ ФУНКЦИЙ")
    print("🔵" * 30)

    test1 = test_direct_url()
    test2 = test_download(task)

    print("\n" + "=" * 60)
    print("📊 РЕЗУЛЬТАТЫ ТЕСТОВ:")
    print(f"   get_yandex_direct_download_url: {'✅' if test1 else '❌'}")
    print(f"   download_from_yandex:            {'✅' if test2 else '❌'}")
    print("=" * 60)

    if test1 and test2:
        print("\n🎉 ВСЕ ТЕСТЫ ПРОЙДЕНЫ! Функции работают корректно!")
    else:
        print("\n❌ ЕСТЬ ПРОБЛЕМЫ! Нужно исправлять функции в utils.py")