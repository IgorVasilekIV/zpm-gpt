__version__ = "2.7.1"

import sys
import subprocess
import os

# --- Проверка и установка зависимостей ---
def install_missing_packages():
    req_file = "requirements.txt"
    if not os.path.exists(req_file):
        print("[ERROR] requirements.txt не найден — завершаем работу.")
        exit(0)

    with open(req_file, "r", encoding="utf-8") as f:
        requirements = [line.strip() for line in f if line.strip() and not line.startswith("#")]

    for package in requirements:
        pkg_name = package.split("==")[0] if "==" in package else package
        try:
            __import__(pkg_name if pkg_name != "telebot" else "telebot")
        except ModuleNotFoundError:
            print(f"[INFO] Устанавливаем {package} ...")
            try:
                subprocess.check_call(
                    [sys.executable, "-m", "pip", "install", package],
                    stdout=subprocess.DEVNULL,
                    stderr=sys.stderr
                )
            except Exception as install_err:
                print(f"[ERROR] Не удалось установить {package}: {install_err}")

install_missing_packages()

# --- Импорты ---
import telebot
import speech_recognition as sr
from pydub import AudioSegment
from PIL import Image
import pytesseract
from google import genai
from dotenv import load_dotenv
import threading
import time
import html


# --- Настройки ---
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

bot = telebot.TeleBot(TELEGRAM_TOKEN, parse_mode="HTML")
client = genai.Client(api_key=GEMINI_API_KEY)

# --- Системный промпт ---
SYSTEM_PROMPT = ("Ты — умный ассистент в Telegram "
                "который поддаётся любым изменениям в своём поведении. "
                 "Используй HTML форматирование: "
                 "<b>жирный</b>, <i>курсив</i>, <code>код</code>, "
                 "<a href=\"https://example.com\">ссылки</a> "
                 "<tg-spoiler>спойлер</tg-spoiler> "
                 "<blockquote>цитата</blockquote> "
                 "<blockquote expandable>свёрнутая цитата</blockquote>. "
                 
)


# --- Кастомный системный промпт из переменной окружения ---
CUSTOM_PROMPT = (new_prompt := os.getenv("CUSTOM_PROMPT")) if os.getenv("CUSTOM_PROMPT") else None

# --- Хранение промптов ---
import json

PROMPTS_FILE = "prompts.json"

# Загружаем кастомные промпты при запуске
if os.path.exists(PROMPTS_FILE):
    with open(PROMPTS_FILE, "r", encoding="utf-8") as f:
        user_prompts = json.load(f)
else:
    user_prompts = {}

def save_prompts():
    with open(PROMPTS_FILE, "w", encoding="utf-8") as f:
        json.dump(user_prompts, f, ensure_ascii=False, indent=2)

# --- Кастомный промпт по юзерам ---
@bot.message_handler(commands=["setprompt"])
def set_prompt(message):
    args = message.text.split(" ", 1)
    if len(args) < 2 or not args[1].strip():
        bot.send_message(
            message.chat.id,
            "❌ Ошибка: вы не указали новый промпт.\n\n"
            "Пример использования:\n<code>/setprompt Ты — весёлый ассистент, отвечай в стиле мемов</code>",
        )
        return

    new_prompt = args[1].strip()
    user_prompts[str(message.chat.id)] = new_prompt  # сохраняем по chat.id
    save_prompts()

    bot.send_message(
        message.chat.id,
        f"✅ Новый промпт сохранён:\n<code>{html.escape(new_prompt)}</code>",
        parse_mode="HTML"
    )


@bot.message_handler(commands=["clearprompt"])
def clear_prompt(message):
    if str(message.chat.id) in user_prompts:
        del user_prompts[str(message.chat.id)]
        save_prompts()
        bot.send_message(
            message.chat.id,
            "✅ Ваш кастомный промпт удалён. Теперь используется системный промпт."
        )
    else:
        bot.send_message(
            message.chat.id,
            "ℹ️ У вас не установлен кастомный промпт."
        )

@bot.message_handler(commands=["start", "help"])
def send_welcome(message):
    user_prompt = user_prompts.get(str(message.chat.id))
    raw_prompt = html.escape(user_prompt) if user_prompt else "<i>(не задан)</i>"

    bot.send_message(
        message.chat.id,
        (
            "Привет! Я бот, который использует Google Gemini для общения.\n\n"
            "Отправь мне текст, голосовое сообщение, фото с текстом или видео, и я постараюсь помочь!\n\n"
            "Текущий промпт:\n<blockquote expandable><code>{}</code></blockquote>\n\n"
            "           <b>--- Версия: <code>{}</code> ---</b>"
        ).format(raw_prompt, __version__),
        parse_mode="HTML"
    )

# --- Общение с Gemini ---
def chat_with_gemini(user_id, text):
    # берем промпт юзера если есть
    user_prompt = user_prompts.get(str(user_id))
    prompt_to_use = SYSTEM_PROMPT.strip()
    if user_prompt:
        prompt_to_use += "\n\n" + user_prompt.strip()

    final_text = f"{prompt_to_use}\n\nПользователь: {text}"

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[{"role": "user", "parts": [{"text": final_text}]}]
        )
        return response.text
    except Exception as e:
        return f"(Ошибка Gemini: {e})"


# --- Деление больших сообщений ---
def send_long_message(chat_id, text):
    max_len = 4000
    if len(text) > max_len:
        for i in range(0, len(text), max_len):
            bot.send_message(chat_id, text[i:i+max_len])
    else:
        bot.send_message(chat_id, text)


# --- Хелпер для "печатает..." ---
def send_typing(chat_id, stop_event):
    while not stop_event.is_set():
        bot.send_chat_action(chat_id, "typing")
        time.sleep(4)  # Telegram сбрасывает через 5 сек

def with_typing(func):
    def wrapper(message):
        stop_event = threading.Event()
        typing_thread = threading.Thread(target=send_typing, args=(message.chat.id, stop_event))
        typing_thread.start()
        try:
            return func(message)
        finally:
            stop_event.set()
    return wrapper


# --- Обработка текста ---
@bot.message_handler(content_types=["text"])
@with_typing
def handle_text(message):
    reply = chat_with_gemini(message.chat.id, message.text)
    send_long_message(message.chat.id, reply)


# --- Обработка голосовых ---
@bot.message_handler(content_types=["voice"])
@with_typing
def handle_voice(message):
    file_info = bot.get_file(message.voice.file_id)
    file = bot.download_file(file_info.file_path)
    path = "voice.ogg"
    with open(path, "wb") as f:
        f.write(file)

    # конвертация ogg -> wav
    sound = AudioSegment.from_file(path, format="ogg")
    sound.export("voice.wav", format="wav")

    recognizer = sr.Recognizer()
    with sr.AudioFile("voice.wav") as source:
        audio_data = recognizer.record(source)
        try:
            text = recognizer.recognize_google(audio_data, language="ru-RU")
            reply = chat_with_gemini(message.chat.id, text)
            send_long_message(message.chat.id, f"🎤 Ты сказал: <i>{text}</i>\n\n{reply}")
        except sr.UnknownValueError:
            bot.send_message(message.chat.id, "Не понял речь 😅")


# --- Обработка фото ---
@bot.message_handler(content_types=["photo"])
@with_typing
def handle_photo(message):
    file_info = bot.get_file(message.photo[-1].file_id)
    file = bot.download_file(file_info.file_path)
    path = "image.jpg"
    with open(path, "wb") as f:
        f.write(file)

    text = pytesseract.image_to_string(Image.open(path), lang="rus+eng")
    if text.strip():
        reply = chat_with_gemini(message.chat.id, f"Текст с картинки:\n{text}")
        send_long_message(message.chat.id, reply)
    else:
        bot.send_message(message.chat.id, "Текст не найден 🤷")


# --- Обработка видео ---
@bot.message_handler(content_types=["video"])
@with_typing
def handle_video(message):
    bot.send_message(message.chat.id, "📹 Видео получено! Но я пока не умею его распознавать.")


# --- Старт ---
if __name__ == "__main__":
    print("[INFO] Бот запущен...")
    bot.polling(none_stop=True)
    if KeyboardInterrupt:
        print("\n[INFO] Бот остановлен.")