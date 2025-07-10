# В тестах отключены некоторые проверки Pylint
# pylint: disable=missing-module-docstring,missing-class-docstring,missing-function-docstring
# pylint: disable=redefined-outer-name,too-few-public-methods
# pylint: disable=import-outside-toplevel,unused-argument

import importlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


class FakeRedis:
    def __init__(self, *args, **kwargs):
        self.store = {}

    def ping(self):
        return True

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value):
        self.store[key] = value

    def setex(self, key, ttl, value):
        self.store[key] = value

    def delete(self, key):
        self.store.pop(key, None)


class FakeBot:
    def __init__(self, token: str):
        self.token = token

    async def get_file(self, file_id):
        return SimpleNamespace(file_path=f"{file_id}.jpg")

    async def download_file(self, src, dest):
        Path(dest).write_bytes(b"data")


class FakeDispatcher:
    def __init__(self):
        self.started = False

    def message(self, *args, **kwargs):
        def decorator(func):
            return func
        return decorator

    def callback_query(self, *args, **kwargs):
        def decorator(func):
            return func
        return decorator

    async def start_polling(self, bot):
        self.started = True


class FakeMessage:
    def __init__(self, text: str, user_id: int = 1):
        self.text = text
        self.from_user = SimpleNamespace(id=user_id)
        self.photo = []
        self.replies = []

    async def reply(self, text: str, **kwargs):
        self.replies.append((text, kwargs))


class FakeCallback:
    def __init__(self, data: str, user_id: int = 1):
        self.data = data
        self.from_user = SimpleNamespace(id=user_id)
        self.message = FakeMessage("callback", user_id)
        self.answered = False

    async def answer(self):
        self.answered = True


@pytest.fixture()
def bot_module(monkeypatch):
    monkeypatch.setenv("GREEDY_BOOK_TG_TOKEN", "token")
    monkeypatch.setenv("GIGACHAT_AUTH_KEY", "key")
    monkeypatch.setenv("ADMIN_USER_ID", "1")
    monkeypatch.setattr("redis.Redis", FakeRedis)
    monkeypatch.setattr("aiogram.Bot", FakeBot)
    monkeypatch.setattr("aiogram.Dispatcher", FakeDispatcher)
    import sys
    if "book_bot.telegram_bot_with_db" in sys.modules:
        del sys.modules["book_bot.telegram_bot_with_db"]
    module = importlib.import_module("book_bot.telegram_bot_with_db")
    return module


def test_parse_book_data(bot_module):
    text = (
        "Автор: A\n"
        "Название: B\n"
        "Год издания: 2020\n"
        "Категория: C\n"
        "Издательство: P"
    )
    res = bot_module.parse_book_data(text)
    assert res == {
        "author": "A",
        "title": "B",
        "publication_year": 2020,
        "category": "C",
        "publisher": "P",
    }


def test_get_prompt(bot_module):
    expected = Path("book_bot/prompt.txt").read_text(encoding="utf-8")
    assert bot_module.get_prompt() == expected


def test_db_keys(bot_module):
    bot_module.save_db_keys({"k": "db.sqlite"})
    assert bot_module.load_db_keys() == {"k": "db.sqlite"}
    bot_module.state.current_db_key = "k"
    assert bot_module.get_current_db_path() == "db.sqlite"


@pytest.mark.asyncio
async def test_db_operations(tmp_path, bot_module):
    db = tmp_path / "test.db"
    bot_module.redis_client.set("db_keys", json.dumps({"k": str(db)}))
    bot_module.state.current_db_key = "k"
    await bot_module.init_db(str(db))
    await bot_module.save_book(
        {
            "author": "A",
            "title": "B",
            "publication_year": 2020,
            "category": "C",
            "publisher": "P",
        },
        "1",
    )
    total = await bot_module.get_total_books()
    assert total == 1


def test_get_save_keyboard(bot_module):
    kb = bot_module.get_save_keyboard("bid")
    assert isinstance(kb, bot_module.InlineKeyboardMarkup)


@pytest.mark.asyncio
async def test_send_welcome(monkeypatch, tmp_path, bot_module):
    db = tmp_path / "db.sqlite"
    bot_module.save_db_keys({"k": str(db)})
    monkeypatch.setattr(bot_module, "init_db", AsyncMock())
    msg = FakeMessage("/start k")
    await bot_module.send_welcome(msg)
    assert msg.replies


@pytest.mark.asyncio
async def test_send_total_books(monkeypatch, bot_module):
    bot_module.state.current_db_key = "k"
    monkeypatch.setattr(bot_module, "get_total_books", AsyncMock(return_value=2))
    msg = FakeMessage("/total")
    await bot_module.send_total_books(msg)
    assert "2" in msg.replies[0][0]


@pytest.mark.asyncio
async def test_send_user_id(bot_module):
    msg = FakeMessage("/my_id", user_id=42)
    await bot_module.send_user_id(msg)
    assert "42" in msg.replies[0][0]


@pytest.mark.asyncio
async def test_add_db_key(monkeypatch, tmp_path, bot_module):
    monkeypatch.setattr(bot_module, "init_db", AsyncMock())
    msg = FakeMessage("/add_key newkey file.db", user_id=1)
    await bot_module.add_db_key(msg)
    assert bot_module.load_db_keys()["newkey"] == "file.db"


@pytest.mark.asyncio
async def test_handle_photo(monkeypatch, tmp_path, bot_module):
    bot_module.IMAGES_DIR = tmp_path
    db = tmp_path / "db.sqlite"
    bot_module.redis_client.set("db_keys", json.dumps({"k": str(db)}))
    bot_module.state.current_db_key = "k"
    await bot_module.init_db(str(db))

    monkeypatch.setattr(bot_module, "process_images", AsyncMock(return_value=""))
    monkeypatch.setattr(bot_module, "parse_book_data", lambda x: {"a": 1})
    monkeypatch.setattr(bot_module, "uuid4", lambda: "u1")

    msg = FakeMessage("photo")
    msg.photo = [SimpleNamespace(file_id="f1")]
    await bot_module.handle_photo(msg)
    assert "book:u1" in bot_module.redis_client.store


@pytest.mark.asyncio
async def test_process_save_callback(monkeypatch, bot_module):
    bot_module.state.current_db_key = "k"
    bot_module.redis_client.set("book:u1", json.dumps({"a": 1}))
    monkeypatch.setattr(bot_module, "save_book", AsyncMock(return_value=True))
    cb = FakeCallback("save_book:u1")
    await bot_module.process_save_callback(cb)
    assert cb.answered
    assert "book:u1" not in bot_module.redis_client.store


@pytest.mark.asyncio
async def test_main(monkeypatch, tmp_path, bot_module):
    called = False

    async def fake_polling(bot):
        nonlocal called
        called = True

    monkeypatch.setattr(bot_module.dp, "start_polling", fake_polling)
    bot_module.IMAGES_DIR = tmp_path / "imgs"
    await bot_module.main()
    assert called
