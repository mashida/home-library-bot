# Используем официальный образ Python 3.11
FROM python:3.11-slim

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем файлы проекта
COPY requirements.txt .
COPY telegram_bot_with_db.py .
COPY prompt.txt .

# Устанавливаем зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Создаём директорию для изображений и БД
RUN mkdir -p /app/images /app/db

# Указываем тома для персистентного хранения
VOLUME /app/db

# Указываем команду для запуска бота
CMD ["python", "telegram_bot_with_db.py"]