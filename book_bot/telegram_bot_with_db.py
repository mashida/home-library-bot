"""Telegram-бот для сохранения распознанных данных книг в SQLite."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import aiosqlite
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from gigachat import GigaChat
import redis
from uuid import uuid4

# Настройки логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Константы
API_TOKEN: Optional[str] = os.getenv("GREEDY_BOOK_TG_TOKEN")
GIGACHAT_AUTH_KEY: Optional[str] = os.getenv("GIGACHAT_AUTH_KEY")
ADMIN_USER_ID: int = int(os.getenv("ADMIN_USER_ID", 0))
REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT: int = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB: int = int(os.getenv("REDIS_DB", 0))
TEMP_BOOK_TTL: int = 3600  # TTL хранения временных данных книги (секунды)
IMAGES_DIR: Path = Path(__file__).parent / "images"

# Инициализация бота и роутера
bot: Bot = Bot(token=API_TOKEN)
dp: Dispatcher = Dispatcher()

# Инициализация Redis
redis_client: redis.Redis = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    db=REDIS_DB,
    decode_responses=True  # Автоматически декодировать строки
)

# Проверка подключения к Redis
try:
    redis_client.ping()
except redis.ConnectionError as e:
    logger.error(f"Failed to connect to Redis: {e}")
    raise

# Текущий ключ базы данных
CURRENT_DB_KEY: Optional[str] = None

# Загрузка ключей из Redis
def load_db_keys() -> Dict[str, str]:
    """Загрузить из Redis карту ключей баз данных.

    Returns:
        Dict[str, str]: Словарь вида ``ключ`` -> ``путь к файлу БД``.
    """

    try:
        keys_data = redis_client.get("db_keys")
        return json.loads(keys_data) if keys_data else {}
    except Exception as e:
        logger.error(f"Error loading DB keys from Redis: {e}")
        return {}

# Сохранение ключей в Redis
def save_db_keys(db_keys: Dict[str, str]) -> None:
    """Сохранить карту ключей баз данных в Redis.

    Args:
        db_keys: Словарь вида ``ключ`` -> ``путь к файлу БД``.
    """

    try:
        redis_client.set("db_keys", json.dumps(db_keys, ensure_ascii=False))
    except Exception as e:
        logger.error(f"Error saving DB keys to Redis: {e}")

# Получение пути к текущей БД
def get_current_db_path() -> Optional[str]:
    """Получить путь к выбранной базе данных, если он есть.

    Returns:
        Optional[str]: Путь к файлу базы данных или ``None``.
    """

    if CURRENT_DB_KEY:
        db_keys = load_db_keys()
        return db_keys.get(CURRENT_DB_KEY)
    return None

# Инициализация базы данных
async def init_db(db_path: str) -> None:
    """Создать таблицу книг, если её ещё нет.

    Args:
        db_path: Путь к файлу базы данных.
    """

    try:
        async with aiosqlite.connect(db_path) as conn:
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS books (
                    id TEXT PRIMARY KEY,
                    author TEXT,
                    title TEXT,
                    publication_year INTEGER,
                    category TEXT,
                    publisher TEXT,
                    user_id TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            await conn.commit()
    except Exception as e:
        logger.error(f"Error initializing DB {db_path}: {e}")

# Функция для получения количества книг в базе
async def get_total_books() -> int:
    """Получить количество книг в текущей базе данных.

    Returns:
        int: Число записей в таблице ``books``.
    """

    db_path = get_current_db_path()
    if not db_path:
        return 0
    try:
        async with aiosqlite.connect(db_path) as conn:
            cursor = await conn.execute("SELECT COUNT(*) FROM books")
            row = await cursor.fetchone()
            await cursor.close()
            return row[0]
    except Exception as e:
        logger.error(f"Error getting total books: {e}")
        return 0

# Функция для сохранения книги в базу данных
async def save_book(book_data: Dict[str, Any], user_id: str) -> bool:
    """Сохранить книгу в текущей базе данных.

    Args:
        book_data: Словарь с данными книги.
        user_id: Идентификатор пользователя Telegram.

    Returns:
        bool: ``True`` при успешном сохранении, иначе ``False``.
    """

    db_path = get_current_db_path()
    if not db_path:
        return False
    try:
        async with aiosqlite.connect(db_path) as conn:
            await conn.execute(
                """
                INSERT INTO books (id, author, title, publication_year, category, publisher, user_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid4()),
                    book_data.get('author', ''),
                    book_data.get('title', ''),
                    book_data.get('publication_year', 0),
                    book_data.get('category', ''),
                    book_data.get('publisher', ''),
                    user_id,
                ),
            )
            await conn.commit()
            return True
    except Exception as e:
        logger.error(f"Error saving book to database: {e}")
        return False

# Парсинг ответа GigaChat в словарь
def parse_book_data(text: str) -> Dict[str, Any]:
    """Преобразовать ответ GigaChat в словарь с данными книги.

    Args:
        text: Текстовый ответ модели.

    Returns:
        Dict[str, Any]: Извлечённые поля книги.
    """

    book_data: Dict[str, Any] = {}
    lines = text.strip().split('\n')
    for line in lines:
        if ': ' in line:
            key, value = line.split(': ', 1)
            if key == 'Автор':
                book_data['author'] = value
            elif key == 'Название':
                book_data['title'] = value
            elif key == 'Год издания':
                book_data['publication_year'] = int(value) if value.isdigit() else 0
            elif key == 'Категория':
                book_data['category'] = value
            elif key == 'Издательство':
                book_data['publisher'] = value
    return book_data

def get_prompt() -> str:
    """Получить текст подсказки для обработки изображений."""

    prompt_path = Path(__file__).parent / "prompt.txt"
    with open(prompt_path, 'r', encoding='utf-8') as file:
        return file.read()

# Функция для обработки изображений через GigaChat
async def process_images(image_paths: Iterable[Path]) -> str:
    """Отправить изображения в GigaChat и вернуть ответ модели.

    Args:
        image_paths: Итерация путей к файлам изображений.

    Returns:
        str: Текстовый ответ GigaChat.
    """

    try:
        with GigaChat(credentials=GIGACHAT_AUTH_KEY, verify_ssl_certs=False) as giga:
            # Загрузка всех изображений и получение их ID
            image_ids = []
            for image_path in image_paths:
                with open(image_path, "rb") as img:
                    file_info = giga.upload_file(img)
                image_ids.append(file_info.id_)

            # Формируем запрос для обработки изображений
            prompt = get_prompt()
            messages = [
                {
                    "role": "user",
                    "content": prompt,
                    "attachments": image_ids
                }
            ]
            request = {
                "model": "GigaChat-2-Pro",
                "messages": messages
            }
            # Отправляем запрос модели и получаем ответ
            result = giga.chat(request)
            return result.choices[0].message.content
    except Exception as e:
        logger.error(f"Error processing images: {e}")
        return "Произошла ошибка при обработке изображений."

# Хэндлер команды /start
@dp.message(Command(commands=["start"]))
async def send_welcome(message: types.Message) -> None:
    """Обработать команду ``/start`` и выбрать базу данных.

    Args:
        message: Сообщение пользователя с ключом базы.
    """
    global CURRENT_DB_KEY
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.reply("Пожалуйста, укажите ключ базы данных. Пример: /start Splunky-Rose4")
        return
    db_key = args[1].strip()
    db_keys = load_db_keys()
    if db_key not in db_keys:
        await message.reply("Неверный ключ базы данных. Попросите администратора добавить ключ.")
        return
    CURRENT_DB_KEY = db_key
    db_path = db_keys[db_key]
    await init_db(db_path)
    await message.reply(
        f"Подключено к базе данных с ключом {db_key}. "
        "Отправь изображение первой страницы книги, и я пришлю карточку для сохранения."
    )

# Хэндлер команды /total
@dp.message(Command(commands=["total"]))
async def send_total_books(message: types.Message) -> None:
    """Ответить количеством книг в базе данных.

    Args:
        message: Сообщение пользователя с командой ``/total``.
    """
    if not CURRENT_DB_KEY:
        await message.reply("Сначала подключитесь к базе данных с помощью /start <ключ>.")
        return
    total = await get_total_books()
    await message.reply(f"В базе данных сохранено {total} книг.")

# Хэндлер команды /my_id
@dp.message(Command(commands=["my_id"]))
async def send_user_id(message: types.Message) -> None:
    """Отправить пользователю его идентификатор Telegram.

    Args:
        message: Исходное сообщение пользователя.
    """
    user_id = message.from_user.id
    await message.reply(f"Ваш Telegram user_id: {user_id}")

# Хэндлер команды /add_key (только для админа)
@dp.message(Command(commands=["add_key"]))
async def add_db_key(message: types.Message) -> None:
    """Добавить новый ключ базы данных (только для администратора).

    Args:
        message: Сообщение с командой ``/add_key``.
    """
    if message.from_user.id != ADMIN_USER_ID:
        await message.reply("Эта команда доступна только администратору.")
        return
    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        await message.reply("Укажите ключ и имя файла БД. Пример: /add_key Splunky-Rose4 books_splunky.db")
        return
    db_key, db_file = args[1].strip(), args[2].strip()
    if not db_file.endswith('.db'):
        db_file += '.db'
    db_keys = load_db_keys()
    db_keys[db_key] = db_file
    save_db_keys(db_keys)
    await init_db(db_file)  # Инициализируем новую БД
    await message.reply(f"Ключ {db_key} добавлен с файлом БД {db_file}.")

# Создание инлайн-клавиатуры
def get_save_keyboard(book_id: str) -> InlineKeyboardMarkup:
    """Создать инлайн-клавиатуру для сохранения книги.

    Args:
        book_id: Идентификатор книги в Redis.

    Returns:
        InlineKeyboardMarkup: Клавиатура с кнопкой сохранения.
    """

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Сохранить", callback_data=f"save_book:{book_id}")
        ]
    ])
    return keyboard

# Хэндлер для получения изображений
@dp.message(F.photo)
async def handle_photo(message: types.Message) -> None:
    """Обработать фото, распознать книгу и сохранить данные в Redis.

    Args:
        message: Сообщение с фотографией страницы книги.
    """
    if not CURRENT_DB_KEY:
        await message.reply("Сначала подключитесь к базе данных с помощью /start <ключ>.")
        return
    # Скачиваем изображения
    image_paths = []
    photo = message.photo[-1]
    file_id = photo.file_id
    file = await bot.get_file(file_id)
    file_path = file.file_path

    # Скачиваем файл
    os.makedirs(IMAGES_DIR, exist_ok=True)
    image_path = IMAGES_DIR / f"{file_id}.jpg"
    await bot.download_file(file_path, str(image_path))
    image_paths.append(image_path)

    # Обрабатываем изображения через GigaChat
    result = await process_images(image_paths)

    # Парсим данные книги
    book_data = parse_book_data(result)

    # Генерируем уникальный ID для книги и сохраняем данные в Redis
    book_id = str(uuid4())
    try:
        redis_client.setex(
            f"book:{book_id}",
            TEMP_BOOK_TTL,
            json.dumps(book_data, ensure_ascii=False)
        )
    except Exception as e:
        logger.error(f"Error saving book data to Redis: {e}")
        await message.reply("Ошибка при сохранении данных книги.")
        return

    # Отправляем результат пользователю с клавиатурой
    await message.reply(
        result,
        parse_mode="Markdown",
        reply_markup=get_save_keyboard(book_id)
    )

    # Удаляем локальные изображения после обработки
    for image_path in image_paths:
        if os.path.exists(image_path):
            os.remove(image_path)

# Хэндлер для обработки callback'ов от инлайн-кнопки
@dp.callback_query(F.data.startswith("save_book:"))
async def process_save_callback(callback: types.CallbackQuery) -> None:
    """Сохранить книгу в БД по нажатию инлайн-кнопки.

    Args:
        callback: Объект callback от Telegram.
    """
    if not CURRENT_DB_KEY:
        await callback.message.reply("Сначала подключитесь к базе данных с помощью /start <ключ>.")
        return
    try:
        # Извлекаем ID книги из callback_data
        book_id = callback.data.split("save_book:")[1]

        # Получаем данные книги из Redis
        book_data_json = redis_client.get(f"book:{book_id}")
        if not book_data_json:
            await callback.message.reply("Ошибка: данные книги не найдены.")
            return
        book_data = json.loads(book_data_json)

        # Сохраняем в базу с user_id
        user_id = str(callback.from_user.id)
        if await save_book(book_data, user_id):
            await callback.message.reply("Книга успешно сохранена в базе данных!")
            # Удаляем данные из Redis
            redis_client.delete(f"book:{book_id}")
        else:
            await callback.message.reply("Ошибка при сохранении книги.")
    except Exception as e:
        logger.error(f"Error processing save callback: {e}")
        await callback.message.reply("Произошла ошибка при сохранении.")
    await callback.answer()

# Регистрация роутера в диспетчере и запуск бота
async def main() -> None:
    """Запустить бота."""

    # Создаем папку для изображений, если не существует
    os.makedirs(IMAGES_DIR, exist_ok=True)
    await dp.start_polling(bot)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Программа завершена.")
