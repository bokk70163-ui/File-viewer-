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
# BOT_TOKEN = os.environ.get("BOT_TOKEN") 
# টেস্টিং এর জন্য সরাসরি টোকেন বসাচ্ছি, আপনি ডেপ্লয় করার সময় উপরের লাইনটি আনকমেন্ট করবেন এবং নিচেরটি সরাবেন।
BOT_TOKEN = os.environ.get("BOT_TOKEN")
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")
server = Flask(__name__)

# --- In-memory Data Stores ---
user_data = {} # Unified user state if needed later
excel_data = {}

PAGE_SIZE = 100 # ব্যবহারকারীর অনুরোধ অনুযায়ী 100 করা হয়েছে

# --- Helper Functions ---

def generate_tme_links(text, mode):
    items = re.split(r'[,\s\n]+', text)
    links = []
    for item in items:
        item = item.strip()
        if not item: continue
        # ক্লিনআপ: যদি ইউজারনেমে ইতিমধ্যে @ থাকে বা নাম্বারে স্পেস থাকে
        clean_item = item.replace(" ", "").lstrip("@")
        
        if mode == "username":
            # স্ট্যান্ডার্ড ইউজারনেম ফরম্যাট: t.me/username
            links.append(f"https://t.me/{clean_item}")
        elif mode == "number":
             # নম্বর ফরম্যাট: t.me/+number
            if not clean_item.startswith("+"):
                 # যদি নাম্বারে + না থাকে, তবে প্রয়োজনে যুক্ত করা যেতে পারে, 
                 # তবে টেলিগ্রাম সাধারণত + সহ ফরম্যাট আশা করে।
                 # ধরে নিচ্ছি ব্যবহারকারী + সহ বা ছাড়া দিতে পারে, আমরা সেইফ সাইডে + রাখছি।
                 links.append(f"https://t.me/+{clean_item}")
            else:
                 links.append(f"https://t.me/{clean_item}")
    return "\n".join(links)

# --- NEW: Professional Welcome Message ---

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    welcome_text = (
        f"Welcome to *{bot.get_me().first_name}*! 🤖\n\n"
        "Please note that by using this bot, you agree to our Terms of Service and Privacy Policy.\n\n"
        "✅ *Terms of Service:* [Read Here](https://telegra.ph/PRIVACY-POLICY-11-09-407)\n"
        "🔒 *Privacy Policy:* [Read Here](https://telegra.ph/PRIVACY-POLICY-11-09-406)\n\n"
        "*Available Features:*\n"
        "📂 `/view` - Reply to an Excel file to view its content (Rows 1-100, etc.).\n"
        "🔗 `/addlink <list>` - Convert a list of numbers to t.me join links.\n"
        "👤 `/addusername <list>` - Convert a list of usernames to t.me links.\n\n"
        "_Select an option below or use a command to get started!_"
    )
    
    # Main Menu Keyboard
    markup = InlineKeyboardMarkup()
    markup.row(InlineKeyboardButton("📞 Customer Service", url="@Pro_Support_24_7_Bot"))
    
    bot.send_message(message.chat.id, welcome_text, reply_markup=markup, disable_web_page_preview=True)

# --- NEW: Direct Command Handlers (/addlink, /addusername) ---

@bot.message_handler(commands=['addlink'])
def cmd_addlink(message):
    try:
        # কমান্ডের পরের অংশ নেওয়া
        text_to_process = message.text.split(maxsplit=1)[1]
        links = generate_tme_links(text_to_process, mode="number")
        if links:
            bot.reply_to(message, f"Here are your number links:\n\n{links}")
        else:
            bot.reply_to(message, "No valid numbers found.")
    except IndexError:
        bot.reply_to(message, "Please provide numbers after the command.\nExample: `/addlink +88017xxx, +88019xxx`")

@bot.message_handler(commands=['addusername'])
def cmd_addusername(message):
    try:
        text_to_process = message.text.split(maxsplit=1)[1]
        links = generate_tme_links(text_to_process, mode="username")
        if links:
            bot.reply_to(message, f"Here are your username links:\n\n{links}")
        else:
            bot.reply_to(message, "No valid usernames found.")
    except IndexError:
        bot.reply_to(message, "Please provide usernames after the command.\nExample: `/addusername user1, user2`")

# --- NEW & MODIFIED: Excel File Handling (/view and uploads) ---

@bot.message_handler(commands=['view'])
def cmd_view(message):
    # যদি ইউজার কোনো ফাইলে রিপ্লাই করে /view দেয়
    if message.reply_to_message and message.reply_to_message.document:
        process_excel(message.reply_to_message)
    else:
        bot.reply_to(message, "Please reply to an Excel (`.xlsx`/`.xls`) file with `/view`, or just send me the file.")

@bot.message_handler(content_types=["document"])
def handle_document(message):
    # সরাসরি ফাইল দিলেও প্রসেস হবে
    if (message.document.file_name or "").lower().endswith((".xlsx", ".xls")):
        process_excel(message)
    else:
        # অন্য ডকুমেন্ট ইগনোর করা যেতে পারে অথবা এরর মেসেজ দেওয়া যেতে পারে
        pass 

def process_excel(message):
    try:
        file_info = bot.get_file(message.document.file_id)
        downloaded = bot.download_file(file_info.file_path)
        # header=None রাখা হয়েছে যাতে প্রথম সারিও ডেটা হিসেবে কাউন্ট হয়
        df = pd.read_excel(io.BytesIO(downloaded), engine="openpyxl", header=None)
        
        if df.empty:
            bot.reply_to(message, "⚠️ The Excel file is empty.")
            return
            
        # নতুন ফাইল আপলোড হলে পেজ ০ থেকে শুরু হবে
        excel_data[message.chat.id] = {"df": df, "page": 0}
        bot.reply_to(message, "✅ File received! Processing...")
        send_page(message.chat.id)
        
    except Exception as e:
        bot.reply_to(message, f"❌ An error occurred while processing the file:\n`{e}`")

def send_page(chat_id):
    """
    Sends a paginated view of the Excel data.
    MODIFIED: Adds copy-paste support and better pagination buttons.
    """
    store = excel_data.get(chat_id)
    if not store: return

    df, page = store["df"], store["page"]
    total_rows = len(df)
    total_pages = ceil(total_rows / PAGE_SIZE)

    start = page * PAGE_SIZE
    end = min(start + PAGE_SIZE, total_rows)
    page_df = df.iloc[start:end]

    # Column selection logic (unchanged essentially, picks col 1 if exists, else 0)
    if page_df.shape[1] > 1:
        number_col = page_df.iloc[:, 1]
        col_idx = 2 # For display purposes (human readable 1-based index)
    else:
        number_col = page_df.iloc[:, 0]
        col_idx = 1

    # Clean and convert data
    clean_numbers = pd.to_numeric(number_col, errors='coerce').dropna().astype('int64').astype(str)

    if clean_numbers.empty:
        content = "No valid numbers found in this range."
    else:
        # MODIFICATION: Wrapping in ``` marks for one-tap copy in Telegram
        content = "```\n" + "\n".join(clean_numbers) + "\n```"

    # Caption with details
    caption = (
        f"📊 *Data Viewer* (Col {col_idx})\n"
        f"📑 *Page:* {page + 1}/{total_pages}\n"
        f"🔢 *Rows:* {start + 1} to {end} (of {total_rows})\n\n"
        f"{content}\n\n"
        f"_Tip: Tap the numbers above to copy._"
    )
    
    # Navigation Buttons (Modified style as requested: < Row No >)
    kb = InlineKeyboardMarkup()
    btns = []
    
    # Previous Button
    if page > 0:
        btns.append(InlineKeyboardButton(f"⬅️ < {start}", callback_data="prev"))
    
    # Current Page Indicator (Optional, acts as a disabled button just for show)
    # btns.append(InlineKeyboardButton(f"• {page+1} •", callback_data="noop"))

    # Next Button
    if page < total_pages - 1:
        btns.append(InlineKeyboardButton(f"{end + 1} > ➡️", callback_data="next"))
        
    if btns:
        kb.row(*btns)
        
    bot.send_message(chat_id, caption, reply_markup=kb)

# --- Callback Handler for Pagination ---

@bot.callback_query_handler(func=lambda call: call.data in ["prev", "next", "noop"])
def page_nav(call):
    chat_id = call.message.chat.id
    store = excel_data.get(chat_id)
    
    if call.data == "noop":
        bot.answer_callback_query(call.id, "Current Page")
        return

    if not store:
        bot.answer_callback_query(call.id, "Session expired. Please upload file again.")
        return
    
    if call.data == "prev" and store["page"] > 0: 
        store["page"] -= 1
    elif call.data == "next": 
        store["page"] += 1
        
    # MODIFICATION: 'Keep the open content' - We DO NOT delete the old message.
    # We just send the new page as a new message.
    # Optional: We could edit the *reply_markup* of the old message to remove buttons 
    # so users don't click old buttons, but keeping them might be preferred by some.
    # For now, leaving them as is, just sending new message.
    
    send_page(chat_id)
    bot.answer_callback_query(call.id) # Stop the loading animation on button

# --- Webhook Handling (No changes as requested) ---
@server.route('/' + BOT_TOKEN, methods=['POST'])
def get_message():
    json_string = request.get_data().decode('utf-8')
    update = telebot.types.Update.de_json(json_string)
    bot.process_new_updates([update])
    return "!", 200

@server.route("/")
def webhook():
    bot.remove_webhook()
    bot.set_webhook(url='https://' + os.environ.get("RENDER_EXTERNAL_HOSTNAME") + '/' + BOT_TOKEN)
    return "Webhook set!", 200

if __name__ == "__main__":
    # Local testing
    # print("Bot is running locally...")
    server.run(host="0.0.0.0", port=int(os.environ.get('PORT', 5000)))
