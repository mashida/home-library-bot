import os
import logging
import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from gigachat import GigaChat

# Настройки логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Константы
API_TOKEN = os.getenv("GREEDY_BOOK_TG_TOKEN")
GIGACHAT_AUTH_KEY = os.getenv("GIGACHAT_AUTH_KEY")

# Инициализация бота и роутера
bot = Bot(token=API_TOKEN)
dp = Dispatcher()


def get_prompt() -> str:
    """
    Function to prompt from prompt.txt
    :return: prompt as string
    """
    with open('prompt.txt', 'r', encoding='utf-8') as file:
        return file.read()


# Функция для обработки изображений через GigaChat
async def process_images(image_paths: list) -> str:
    try:
        with GigaChat(credentials=GIGACHAT_AUTH_KEY, verify_ssl_certs=False) as giga:
            # Загрузка всех изображений и получение их ID
            image_ids = []
            for image_path in image_paths:
                with open(image_path, "rb") as img:
                    file_info = giga.upload_file(img)  # загружает файл в хранилище
                image_ids.append(file_info.id_)

            # Формируем запрос для обработки изображений
            prompt = get_prompt()
            messages = [
                {
                    "role": "user",
                    "content": prompt,
                    "attachments": image_ids  # передаём список ID изображений
                }
            ]
            request = {
                "model": "GigaChat-2-Pro",
                "messages": messages
            }
            # Отправляем запрос модели и получаем ответ
            result = giga.chat(request)

            # Получаем результат
            return result.choices[0].message.content
    except Exception as e:
        logger.error(f"Error processing images: {e}")
        return "Произошла ошибка при обработке изображений."


# Хэндлер команды /start
@dp.message(Command(commands=["start", "help"]))
async def send_welcome(message: types.Message) -> None:
    await message.reply(
        "Привет! Отправь мне изображение первой страницы книги, и я пришлю тебе карточку этой книги для сохранения в базе."
    )


# Хэндлер для получения изображений
@dp.message(F.photo)
async def handle_photo(message: types.Message) -> None:
    # Скачиваем изображения
    image_paths = []
    photo = message.photo[-1]
    file_id = photo.file_id
    file = await bot.get_file(file_id)
    file_path = file.file_path

    # Скачиваем файл
    image_path = f'./images/{file_id}.jpg'
    await bot.download_file(file_path, image_path)
    image_paths.append(image_path)

    # Обрабатываем изображения через GigaChat
    result = await process_images(image_paths)

    # Отправляем результат пользователю
    await message.reply(result, parse_mode="Markdown")

    # Удаляем локальные изображения после обработки
    for image_path in image_paths:
        if os.path.exists(image_path):
            os.remove(image_path)  # Удаляем файл


# Регистрация роутера в диспетчере и запуск бота
async def main() -> None:
    await dp.start_polling(bot)


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Программа завершена.")
