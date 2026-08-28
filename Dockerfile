# publisher/Dockerfile
# Pin bookworm: floating python:3.10-slim moved to trixie; 77.222 often cannot
# reach deb.debian.org for a cold apt on the new base.
FROM python:3.10-slim-bookworm

# Отключаем запись байт-кода и буферизацию логов
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Устанавливаем рабочую директорию
WORKDIR /app

# Устанавливаем системные зависимости (нужно для некоторых пакетов).
# ADB в образ не кладём: публикация идёт через OpenAPI phone/uploadFile.
RUN apt-get update && apt-get install -y \
    gcc \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Копируем зависимости и устанавливаем
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Копируем весь проект
COPY . .

# Создаем необходимые папки
RUN mkdir -p /app/static /app/media /app/data

# Собираем статику
RUN python manage.py collectstatic --noinput

# Открываем порт
EXPOSE 8000

# Запускаем через gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--worker-class", "gthread", "--workers", "3", "--threads", "4", "--timeout", "600", "--keep-alive", "5", "config.wsgi:application"]