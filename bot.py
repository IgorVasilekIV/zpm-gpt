__version__ = (2, 2, 1)

"""
Telegram-бот с Gemini:
- Поддержка текста, голоса, фото и видео
- Простая память пользователей
- Длинные ответы автоматически разбиваются
- Поддержка Markdown-разметки
- Автоматическая проверка и установка зависимостей
"""
import sys
import subprocess
import os
import json
import tempfile
import subprocess
from pathlib import Path
from time import time
from PIL import Image
from pydub import AudioSegment
import speech_recognition as sr

# --- Проверка и установка зависимостей ---
required_packages = [
    "pyTelegramBotAPI",
    "google-genai",
    "SpeechRecognition",
    "pydub",
    "pillow",
    "pytesseract",
    "python-dotenv"
]

for package in required_packages:
    try:
        if package == "pyTelegramBotAPI":
            import telebot
        else:
            __import__(package)
    except ImportError:
        print(f"Устанавливаем пакет: {package}")
        subprocess.check_call([sys.executable, "-m", "pip", "install", package])

# --- После установки импортируем нужные модули ---
import telebot
import pytesseract
from google import genai
from dotenv import load_dotenv

# --- Настройки ---
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MEMORY_FILE = "gemini_memory.json"
MAX_HISTORY = 10

if not TELEGRAM_TOKEN:
    raise SystemExit("Установите TELEGRAM_TOKEN в .env")
if not GEMINI_API_KEY:
    raise SystemExit("Установите GEMINI_API_KEY в .env")

bot = telebot.TeleBot(TELEGRAM_TOKEN)
client = genai.Client(api_key=GEMINI_API_KEY)

# --- Память пользователей ---
if Path(MEMORY_FILE).exists():
    with open(MEMORY_FILE, "r", encoding="utf-8") as f:
        memory = json.load(f)
else:
    memory = {}

def save_memory():
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(memory, f, ensure_ascii=False, indent=2)

def add_to_memory(user_id, role, text):
    key = str(user_id)
    if key not in memory:
        memory[key] = []
    memory[key].append({"role": role, "text": text, "ts": int(time())})
    if len(memory[key]) > MAX_HISTORY:
        memory[key] = memory[key][-MAX_HISTORY:]
    save_memory()

def get_history_prompt(user_id):
    key = str(user_id)
    if key not in memory:
        return ""
    parts = []
    for item in memory[key]:
        prefix = "User:" if item["role"] == "user" else "Assistant:"
        parts.append(f"{prefix} {item['text']}")
    return "\n".join(parts) + "\nAssistant:"

# --- Работа с длинными сообщениями и Markdown ---
def send_long_markdown(chat_id, text):
    MAX_LEN = 4000
    chunks = [text[i:i+MAX_LEN] for i in range(0, len(text), MAX_LEN)]
    for idx, chunk in enumerate(chunks, 1):
        header = f"(часть {idx}/{len(chunks)})\n" if len(chunks) > 1 else ""
        bot.send_message(chat_id, header + chunk, parse_mode="Markdown")

# --- Голосовое распознавание ---
def transcribe_audio(file_path):
    r = sr.Recognizer()
    try:
        audio = AudioSegment.from_file(file_path)
        wav_path = file_path + ".wav"
        audio.export(wav_path, format="wav")  # используем wav
        with sr.AudioFile(wav_path) as source:
            audio_data = r.record(source)
        text = r.recognize_google(audio_data, language="ru-RU")
        return text
    except Exception as e:
        return f"(ошибка распознавания: {e})"

# --- Распознавание текста с фото/кадра видео ---
def extract_text_from_image(img_path):
    try:
        text = pytesseract.image_to_string(Image.open(img_path), lang="rus+eng")
        return text.strip()
    except Exception as e:
        return f"(ошибка OCR: {e})"

def extract_frame_from_video(video_path, out_image_path):
    try:
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", video_path],
            capture_output=True, text=True
        )
        dur = float(probe.stdout.strip() or 0)
        ts = max(0.5, dur / 2)
        subprocess.run(["ffmpeg", "-y", "-ss", str(ts), "-i", video_path,
                        "-frames:v", "1", out_image_path], check=True)
        return True
    except Exception as e:
        print("ffmpeg error:", e)
        return False

# --- Вызов Gemini ---
def ask_gemini(prompt_text):
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt_text
        )
        return response.text
    except Exception as e:
        return f"(ошибка Gemini: {e})"

# --- Обработчики Telegram ---
@bot.message_handler(commands=["start"])
def cmd_start(message):
    bot.send_message(message.chat.id,
                     f"Привет! Я бот с Gemini. Отправь текст, голос, фото или видео.\n\nВерсия: {__version__}")

@bot.message_handler(commands=["clear_memory"])
def cmd_clear_memory(message):
    key = str(message.from_user.id)
    memory.pop(key, None)
    save_memory()
    bot.send_message(message.chat.id, "Память очищена.")

@bot.message_handler(content_types=["text"])
def handle_text(message):
    user_text = message.text
    add_to_memory(message.from_user.id, "user", user_text)

    hist = get_history_prompt(message.from_user.id)
    prompt = hist + "\nUser: " + user_text + "\nAssistant:"

    bot.send_chat_action(message.chat.id, "typing")
    ans = ask_gemini(prompt)

    add_to_memory(message.from_user.id, "assistant", ans)
    send_long_markdown(message.chat.id, ans)

@bot.message_handler(content_types=["voice", "audio"])
def handle_voice(message):
    file_info = bot.get_file(message.voice.file_id if message.content_type=="voice" else message.audio.file_id)
    with tempfile.TemporaryDirectory() as tmp:
        file_path = os.path.join(tmp, "voice.ogg")
        downloaded = bot.download_file(file_info.file_path)
        with open(file_path, "wb") as f:
            f.write(downloaded)
        text = transcribe_audio(file_path)
        add_to_memory(message.from_user.id, "user", f"(voice) {text}")
        hist = get_history_prompt(message.from_user.id)
        prompt = hist + "\nUser (voice): " + text + "\nAssistant:"
        bot.send_chat_action(message.chat.id, "typing")
        ans = ask_gemini(prompt)
        add_to_memory(message.from_user.id, "assistant", ans)
        send_long_markdown(message.chat.id, f"Распознанный текст: {text}\n\nОтвет:\n{ans}")

@bot.message_handler(content_types=["photo"])
def handle_photo(message):
    file_info = bot.get_file(message.photo[-1].file_id)
    with tempfile.TemporaryDirectory() as tmp:
        img_path = os.path.join(tmp, "photo.jpg")
        downloaded = bot.download_file(file_info.file_path)
        with open(img_path, "wb") as f:
            f.write(downloaded)
        ocr = extract_text_from_image(img_path)
        add_to_memory(message.from_user.id, "user", f"(image) OCR: {ocr}")
        prompt = get_history_prompt(message.from_user.id) + "\nUser sent an image. OCR: " + (ocr or "(пусто)")
        bot.send_chat_action(message.chat.id, "typing")
        ans = ask_gemini(prompt)
        add_to_memory(message.from_user.id, "assistant", ans)
        send_long_markdown(message.chat.id, f"OCR:\n{ocr}\n\nОтвет:\n{ans}")

@bot.message_handler(content_types=["video"])
def handle_video(message):
    file_info = bot.get_file(message.video.file_id)
    with tempfile.TemporaryDirectory() as tmp:
        vid_path = os.path.join(tmp, "video.mp4")
        downloaded = bot.download_file(file_info.file_path)
        with open(vid_path, "wb") as f:
            f.write(downloaded)
        frame = os.path.join(tmp, "frame.jpg")
        ok = extract_frame_from_video(vid_path, frame)
        if not ok:
            bot.send_message(message.chat.id, "Не удалось обработать видео.")
            return
        ocr = extract_text_from_image(frame)
        add_to_memory(message.from_user.id, "user", f"(video) OCR: {ocr}")
        prompt = get_history_prompt(message.from_user.id) + "\nUser sent a video. OCR: " + (ocr or "(пусто)")
        bot.send_chat_action(message.chat.id, "typing")
        ans = ask_gemini(prompt)
        add_to_memory(message.from_user.id, "assistant", ans)
        send_long_markdown(message.chat.id, f"Frame OCR:\n{ocr}\n\nОтвет:\n{ans}")

if __name__ == "__main__":
    print("Bot started...")
    bot.infinity_polling()