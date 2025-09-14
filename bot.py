__version__ = "2.3.2"

import sys
import subprocess
import os

# --- Проверка и установка зависимостей ---
def install_missing_packages():
    req_file = "requirements.txt"
    if not os.path.exists(req_file):
        print("[WARN] requirements.txt не найден — пропускаем установку зависимостей")
        return

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


# --- Настройки ---
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

bot = telebot.TeleBot(TELEGRAM_TOKEN, parse_mode="HTML")  # HTML как в Hikka
client = genai.Client(api_key=GEMINI_API_KEY)


# --- Кастомный промпт ---
CUSTOM_PROMPT = """Ты — умный ассистент в Telegram.
Отвечай кратко и понятно. Используй HTML форматирование:
<b>жирный</b>, <i>курсив</i>, <code>код</code>, <a href="https://example.com">ссылки</a> <tg-spoiler>спойлер</tg-spoiler> <blockquote>цитата</blockquote> <blockquote expandable>свёрнутая цитата</blockquote>.
"""


# --- Общение с Gemini ---
def chat_with_gemini(user_id, text):
    try:
        response = client.models.generate_content(
            model="gemini-1.5-flash",
            contents=[
                {"role": "system", "parts": [{"text": CUSTOM_PROMPT}]},
                {"role": "user", "parts": [{"text": text}]}
            ]
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


# --- Обработка текста ---
@bot.message_handler(content_types=["text"])
def handle_text(message):
    reply = chat_with_gemini(message.chat.id, message.text)
    send_long_message(message.chat.id, reply)


# --- Обработка голосовых ---
@bot.message_handler(content_types=["voice"])
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
def handle_video(message):
    bot.send_message(message.chat.id, "📹 Видео получено! Но я пока не умею его распознавать.")


# --- Старт ---
if __name__ == "__main__":
    print("[INFO] Бот запущен...")
    bot.polling(none_stop=True)
