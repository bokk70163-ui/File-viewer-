import os
import io
import re
import pandas as pd
from math import ceil
import telebot
from telebot.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton
)
from flask import Flask, request

# --- Bot and Flask Setup ---
BOT_TOKEN = "7495758013:AAEaEqG8Dws02QTVLEgAijHnTT7SuBMyzK8"  # টোকেন এখানে হার্ডকোড করবেন না
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")
server = Flask(__name__)

# --- In-memory Data Stores (For simplicity) ---
user_choice = {}
user_mode = {}
excel_data = {}

PAGE_SIZE = 80

# --- Your Existing Bot Handlers (No changes needed here) ---

@bot.message_handler(commands=['start'])
def start(message):
    markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add(KeyboardButton("Generate Links"), KeyboardButton("View Excel"))
    bot.send_message(message.chat.id,
        "Hi! What do you want to do?",
        reply_markup=markup)

@bot.message_handler(func=lambda m: m.text in ["Generate Links", "View Excel"])
def choose_mode(message):
    chat_id = message.chat.id
    if message.text == "Generate Links":
        user_mode[chat_id] = "Links"
        markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        markup.add(KeyboardButton("Username"), KeyboardButton("Number"))
        bot.send_message(chat_id,
            "Do you want to generate links for usernames or numbers?",
            reply_markup=markup)
    elif message.text == "View Excel":
        user_mode[chat_id] = "Excel"
        bot.send_message(chat_id, "Please send me an `.xlsx` file.")

@bot.message_handler(func=lambda m: user_mode.get(m.chat.id) == "Links" and m.text in ["Username", "Number"])
def save_choice(message):
    user_choice[message.chat.id] = message.text
    bot.send_message(message.chat.id, f"Send your {message.text.lower()} list. Separate by space, comma or newline.")

@bot.message_handler(func=lambda m: user_mode.get(m.chat.id) == "Links" and m.chat.id in user_choice)
def generate_links(message):
    choice = user_choice[message.chat.id]
    text = message.text.strip()
    items = re.split(r'[,\s\n]+', text)
    links = []
    for item in items:
        item = item.strip()
        if not item: continue
        if choice == "Username":
            links.append(f"https://t.me/{item.lstrip('@')}")
        elif choice == "Number":
            links.append(f"https://t.me/{item.replace(' ', '')}")
    reply = "\n".join(links)
    bot.send_message(message.chat.id, f"Here are your links:\n{reply}")
    user_choice.pop(message.chat.id, None)
    user_mode.pop(message.chat.id, None)

@bot.message_handler(content_types=["document"], func=lambda m: user_mode.get(m.chat.id) == "Excel")
def handle_excel(message):
    if not (message.document.file_name or "").lower().endswith((".xlsx", ".xls")):
        bot.reply_to(message, "Please send a valid `.xlsx` file.")
        return
    try:
        file_info = bot.get_file(message.document.file_id)
        downloaded = bot.download_file(file_info.file_path)
        df = pd.read_excel(io.BytesIO(downloaded), engine="openpyxl")
        if df.empty:
            bot.reply_to(message, "The Excel file is empty.")
            return
        excel_data[message.chat.id] = {"df": df, "page": 0}
        send_page(message.chat.id)
    except Exception as e:
        bot.reply_to(message, f"An error occurred: {e}")

def send_page(chat_id):
    store = excel_data.get(chat_id)
    if not store: return
    df, page = store["df"], store["page"]
    total_rows = len(df)
    total_pages = ceil(total_rows / PAGE_SIZE)
    start = page * PAGE_SIZE
    end = min(start + PAGE_SIZE, total_rows)
    sub = df.iloc[start:end]
    header = " | ".join(map(str, sub.columns.tolist()))
    sep = " | ".join(["---"] * len(sub.columns))
    rows = [" | ".join(map(lambda c: str(c)[:30], r)) for _, r in sub.iterrows()]
    table_md = "\n".join([header, sep] + rows)
    caption = f"*Rows:* {start+1}–{end} of {total_rows}\n*Page:* {page+1}/{total_pages}\n\n"
    text = caption + f"```\n{table_md}\n```"
    kb = InlineKeyboardMarkup()
    btns = []
    if page > 0: btns.append(InlineKeyboardButton("⬅️ Prev", callback_data="prev"))
    if page < total_pages - 1: btns.append(InlineKeyboardButton("Next ➡️", callback_data="next"))
    if btns: kb.row(*btns)
    bot.send_message(chat_id, text, reply_markup=kb)

@bot.callback_query_handler(func=lambda call: call.data in ["prev", "next"])
def page_nav(call):
    chat_id = call.message.chat.id
    store = excel_data.get(chat_id)
    if not store: return
    if call.data == "prev" and store["page"] > 0: store["page"] -= 1
    elif call.data == "next": store["page"] += 1
    try:
        bot.delete_message(chat_id, call.message.message_id)
    except Exception:
        pass
    send_page(chat_id)
    bot.answer_callback_query(call.id)

# --- Webhook Handling ---
@server.route('/' + BOT_TOKEN, methods=['POST'])
def get_message():
    json_string = request.get_data().decode('utf-8')
    update = telebot.types.Update.de_json(json_string)
    bot.process_new_updates([update])
    return "!", 200

@server.route("/")
def webhook():
    bot.remove_webhook()
    # URL হবে: https://your-app-name.onrender.com/BOT_TOKEN
    bot.set_webhook(url='https://' + os.environ.get("RENDER_EXTERNAL_HOSTNAME") + '/' + BOT_TOKEN)
    return "Webhook set!", 200

if __name__ == "__main__":
    # এই অংশটি শুধুমাত্র লোকাল টেস্টিং এর জন্য, Render এটি ব্যবহার করবে না।
    print("Bot is running locally...")
    server.run(host="0.0.0.0", port=int(os.environ.get('PORT', 5000)))

