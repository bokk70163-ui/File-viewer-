import os
import io
import re
import pandas as pd
from math import ceil
import telebot
from telebot.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton,
    Update # Added for webhook
)
from flask import Flask, request

# --- Bot and Flask Setup ---
BOT_TOKEN = os.environ.get("BOT_TOKEN") # টোকেন এখানে হার্ডকোড করবেন না
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")
server = Flask(__name__)

# --- In-memory Data Stores (For simplicity) ---
user_choice = {}
user_mode = {}
excel_data = {}

PAGE_SIZE = 80 # You can adjust this page size

# --- Helper Function for Link Commands ---

def get_text_to_process(message):
    """Extracts text from a command, reply, or forward for processing."""
    text_to_process = None
    
    # Check for text supplied directly with the command
    # e.g., /addlink 123 456
    parts = message.text.split(maxsplit=1)
    if len(parts) > 1:
        text_to_process = parts[1]
    
    # Check for a reply to another message
    elif message.reply_to_message:
        if message.reply_to_message.text:
            text_to_process = message.reply_to_message.text
        elif message.reply_to_message.contact:
            # If replying to a contact card
            text_to_process = message.reply_to_message.contact.phone_number
            
    # Check if the message is a forward
    elif message.forward_date: # 'forward_date' is a good indicator of a forwarded message
        if message.text: # The text of the forwarded message
            text_to_process = message.text
            
    # Check if the message itself is a contact card
    elif message.contact:
        text_to_process = message.contact.phone_number

    return text_to_process

# --- Bot Handlers ---

@bot.message_handler(commands=['start'])
def start(message):
    """
    Handles the /start command with the new professional welcome message.
    """
    # Welcome text with Markdown links
    welcome_text = (
        "Welcome to the Bot!\n\n"
        "By using this bot, you agree to our "
        "[Terms of Service](https://telegra.ph/PRIVACY-POLICY-11-09-406) and [Privacy Policy](https://telegra.ph/PRIVACY-POLICY-11-09-407).\n\n"
        "Here's what I can do:\n\n"
        "### 🔗 Link Generation\n"
        "Generate `t.me/+` links from a list of numbers or usernames.\n"
        "• `/addlink [numbers]` - Quickly create links for a list of numbers.\n"
        "• `/addusername [usernames]` - Quickly create links for a list of usernames.\n"
        "• You can also use these commands by replying to a message or forwarding one.\n"
        "• Alternatively, use the **Generate Links** button.\n\n"
        "### 📄 Excel Viewer\n"
        "View `.xlsx` or `.xls` files page by page, directly in the chat.\n"
        "• `/view` - Use this command as a caption when uploading a file, or reply to a file with it.\n"
        "• Alternatively, use the **View Excel** button.\n"
        "• Once open, you can navigate pages, switch columns, and copy the data.\n\n"
        "Select an option to begin:"
    )

    # Main menu with inline buttons
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("Generate Links", callback_data="mode_links"),
        InlineKeyboardButton("View Excel", callback_data="mode_excel")
    )
    markup.row(
        InlineKeyboardButton("Customer Service", url="paste customer link here")
    )

    # Send welcome message
    bot.send_message(message.chat.id,
        welcome_text,
        reply_markup=markup,
        parse_mode="Markdown",
        disable_web_page_preview=True)

@bot.callback_query_handler(func=lambda call: call.data in ["mode_links", "mode_excel"])
def handle_mode_choice(call):
    """
    Handles the button press from the /start menu.
    """
    chat_id = call.message.chat.id
    
    if call.data == "mode_links":
        user_mode[chat_id] = "Links"
        markup = InlineKeyboardMarkup()
        markup.row(
            InlineKeyboardButton("Username", callback_data="choice_user"),
            InlineKeyboardButton("Number", callback_data="choice_num")
        )
        bot.send_message(chat_id,
            "Do you want to generate links for usernames or numbers?",
            reply_markup=markup)
            
    elif call.data == "mode_excel":
        user_mode[chat_id] = "Excel"
        bot.send_message(chat_id, "Please send me an `.xlsx` or `.xls` file.")
    
    bot.answer_callback_query(call.id)
    try:
        # Edit the original start message to clean up the chat
        bot.edit_message_text("Please follow the instructions below:", chat_id, call.message.message_id, reply_markup=None)
    except Exception:
        pass # Ignore if editing fails

@bot.callback_query_handler(func=lambda call: call.data in ["choice_user", "choice_num"])
def handle_link_choice(call):
    """
    Handles the Username/Number button press.
    """
    chat_id = call.message.chat.id
    if call.data == "choice_user":
        user_choice[chat_id] = "Username"
    elif call.data == "choice_num":
        user_choice[chat_id] = "Number"
        
    choice_text = user_choice[chat_id].lower()
    bot.send_message(chat_id, f"Send your {choice_text} list. Separate by space, comma or newline.")
    
    bot.answer_callback_query(call.id)
    try:
        # Edit the previous message
        bot.edit_message_text(f"Mode selected: {choice_text.capitalize()}", chat_id, call.message.message_id, reply_markup=None)
    except Exception:
        pass

@bot.message_handler(func=lambda m: user_mode.get(m.chat.id) == "Links" and m.chat.id in user_choice)
def generate_links(message):
    """
    Generates links based on the user's text list.
    (This is the original function, remains unchanged)
    """
    choice = user_choice[message.chat.id]
    text = message.text.strip()
    items = re.split(r'[,\s\n]+', text)
    links = []
    
    for item in items:
        item = item.strip()
        if not item: continue
        if choice == "Username":
            links.append(f"https://t.me/+{item.lstrip('@')}")
        elif choice == "Number":
            # Remove '+' if present, as it's added in the link
            links.append(f"https://t.me/+{item.replace(' ', '').lstrip('+')}")
            
    reply = "\n".join(links)
    bot.send_message(message.chat.id, f"Here are your links:\n```\n{reply}\n```")
    
    # Clear state
    user_choice.pop(message.chat.id, None)
    user_mode.pop(message.chat.id, None)

# --- NEW: /addlink Command ---
@bot.message_handler(commands=['addlink'])
def add_link(message):
    """
    Generates t.me/+ links for numbers provided in the command,
    a reply, or a forwarded message.
    """
    text_to_process = get_text_to_process(message)
    
    if not text_to_process:
        bot.reply_to(message, 
            "Usage: `/addlink [numbers]`\n"
            "You can also reply to a message containing numbers, "
            "forward a message, or send/reply to a contact card.")
        return

    items = re.split(r'[,\s\n]+', text_to_process.strip())
    links = []
    for item in items:
        item = item.strip().lstrip('+') # Clean up spaces and leading +
        if item.isdigit(): # Ensure it's a number
            links.append(f"https://t.me/+{item}")
    
    if not links:
        bot.reply_to(message, "No valid numbers found.")
        return
        
    reply = "\n".join(links)
    bot.send_message(message.chat.id, f"Here are your links:\n```\n{reply}\n```")

# --- NEW: /addusername Command ---
@bot.message_handler(commands=['addusername'])
def add_username(message):
    """
    Generates t.me/+ links for usernames provided in the command,
    a reply, or a forwarded message.
    """
    text_to_process = get_text_to_process(message)
    
    if not text_to_process:
        bot.reply_to(message, 
            "Usage: `/addusername [usernames]`\n"
            "You can also reply to or forward a message containing usernames.")
        return

    items = re.split(r'[,\s\n]+', text_to_process.strip())
    links = []
    for item in items:
        item = item.strip()
        if item: # Ensure not empty
            links.append(f"https://t.me/+{item.lstrip('@')}")
    
    if not links:
        bot.reply_to(message, "No valid usernames found.")
        return
        
    reply = "\n".join(links)
    bot.send_message(message.chat.id, f"Here are your links:\n```\n{reply}\n```")


# --- NEW: /view Command ---
@bot.message_handler(commands=['view'])
def view_command(message):
    """
    Handles the /view command when replying to a file.
    """
    chat_id = message.chat.id
    if message.reply_to_message and message.reply_to_message.document:
        # Set the mode so handle_excel picks it up
        user_mode[chat_id] = "Excel"
        # Pass the message that *contains* the document
        handle_excel(message.reply_to_message)
    else:
        bot.reply_to(message, 
            "Please reply to an `.xlsx` or `.xls` file with `/view`,\n"
            "or send the file with `/view` as the caption.")

# --- MODIFIED: Excel File Handling ---

@bot.message_handler(content_types=["document"])
def handle_excel(message):
    """
    Handles uploaded Excel file.
    MODIFIED:
    - Triggers on "Excel" mode OR if caption is /view.
    - Stores column index and count.
    - Reads with header=None.
    """
    chat_id = message.chat.id
    
    # Check if this handler should run
    is_view_command = (message.caption or "").lower().strip() == "/view"
    is_excel_mode = user_mode.get(chat_id) == "Excel"
    
    if not (is_view_command or is_excel_mode):
        return # Not for this handler

    if not (message.document.file_name or "").lower().endswith((".xlsx", ".xls")):
        bot.reply_to(message, "Please send a valid `.xlsx` or `.xls` file.")
        return
        
    # If triggered by /view caption, set mode
    if is_view_command:
        user_mode[chat_id] = "Excel"

    try:
        file_info = bot.get_file(message.document.file_id)
        downloaded = bot.download_file(file_info.file_path)
        
        # MODIFICATION: header=None treats the first row as data
        df = pd.read_excel(io.BytesIO(downloaded), engine="openpyxl", header=None)
        
        if df.empty:
            bot.reply_to(message, "The Excel file is empty.")
            return
            
        total_cols = df.shape[1]
        # Default to 2nd col (index 1) if it exists, else 1st (index 0)
        default_col = 1 if total_cols > 1 else 0
            
        # Store file data, page, and column info
        excel_data[chat_id] = {
            "df": df, 
            "page": 0,
            "col_index": default_col,
            "total_cols": total_cols
        }
        
        send_page(chat_id) # Send the first page
        
    except Exception as e:
        bot.reply_to(message, f"An error occurred: {e}")

def send_page(chat_id):
    """
    Sends a paginated view of the Excel data.
    MODIFIED:
    - Reads from the selected column index.
    - Adds column navigation buttons.
    - Adds a "Copy" button.
    """
    store = excel_data.get(chat_id)
    if not store: return

    df = store["df"]
    page = store["page"]
    col_index = store.get("col_index", 0)
    total_cols = store.get("total_cols", 1)
    
    # Safety check for column index
    if col_index >= total_cols:
        col_index = 0
        store["col_index"] = 0

    total_rows = len(df)
    total_pages = ceil(total_rows / PAGE_SIZE)
    if total_pages == 0: total_pages = 1 # Handle empty df

    start = page * PAGE_SIZE
    end = min(start + PAGE_SIZE, total_rows)
    page_df = df.iloc[start:end]

    content = "No numbers found on this page."
    
    if not page_df.empty:
        # Get data from the currently selected column
        number_col = page_df.iloc[:, col_index]
        
        # Convert the column to numeric, drop non-numeric, format as integer string
        clean_numbers = pd.to_numeric(number_col, errors='coerce').dropna().astype('int64').astype(str)

        if not clean_numbers.empty:
            content = "\n".join(clean_numbers)

    # Create the message caption with pagination and column info
    caption = (
        f"*Rows:* {start+1}–{end} of {total_rows}\n"
        f"*Page:* {page+1}/{total_pages}\n"
        f"*Column:* {col_index+1}/{total_cols}\n\n"
    )
    text = caption + content
    
    # --- Create navigation buttons ---
    kb = InlineKeyboardMarkup()
    
    # Row 1: Column Navigation
    col_btns = []
    if total_cols > 1:
        col_btns.append(InlineKeyboardButton("⬅️ Col", callback_data="prev_col"))
        col_btns.append(InlineKeyboardButton(f"{col_index+1}/{total_cols}", callback_data="col_info")) # Just for show
        col_btns.append(InlineKeyboardButton("Col ➡️", callback_data="next_col"))
    kb.row(*col_btns)
    
    # Row 2: Page Navigation
    page_btns = []
    if page > 0: 
        page_btns.append(InlineKeyboardButton("⬅️ Prev", callback_data="prev"))
    if page < total_pages - 1: 
        page_btns.append(InlineKeyboardButton("Next ➡️", callback_data="next"))
    if page_btns:
        kb.row(*page_btns)
        
    # Row 3: Copy Button
    kb.row(InlineKeyboardButton("Copy Numbers", callback_data="copy_page"))
        
    bot.send_message(chat_id, text, reply_markup=kb)

# --- MODIFIED: Page & Column Navigation ---
@bot.callback_query_handler(func=lambda call: call.data in ["prev", "next", "prev_col", "next_col"])
def page_nav(call):
    """
    Handles page and column navigation.
    MODIFIED:
    - Added prev_col, next_col logic.
    - Removed bot.delete_message to keep history.
    """
    chat_id = call.message.chat.id
    store = excel_data.get(chat_id)
    if not store: 
        bot.answer_callback_query(call.id, "File data expired. Please re-upload.")
        return
    
    total_cols = store.get("total_cols", 1)
    total_rows = len(store["df"])
    total_pages = ceil(total_rows / PAGE_SIZE)
    if total_pages == 0: total_pages = 1
    
    # Update state based on button press
    if call.data == "prev" and store["page"] > 0: 
        store["page"] -= 1
    elif call.data == "next" and store["page"] < total_pages - 1: 
        store["page"] += 1
    elif call.data == "prev_col" and total_cols > 1:
        store["col_index"] = (store.get("col_index", 0) - 1) % total_cols
    elif call.data == "next_col" and total_cols > 1:
        store["col_index"] = (store.get("col_index", 0) + 1) % total_cols
        
    try:
        # MODIFICATION: User requested to KEEP old content.
        # We no longer delete the previous message.
        # bot.delete_message(chat_id, call.message.message_id)
        pass # Do nothing
    except Exception:
        pass # Ignore
        
    send_page(chat_id) # Send a NEW message with the updated view
    bot.answer_callback_query(call.id)

# --- NEW: Copy Button Handler ---
@bot.callback_query_handler(func=lambda call: call.data == "copy_page")
def copy_page_content(call):
    """
    Handles the 'Copy Numbers' button press.
    Sends the numbers from the *current* view as a new, copy-able message.
    """
    chat_id = call.message.chat.id
    store = excel_data.get(chat_id)
    if not store: 
        bot.answer_callback_query(call.id, "File data expired. Please re-upload.")
        return

    # Re-calculate the content for the current page and column
    df = store["df"]
    page = store["page"]
    col_index = store.get("col_index", 0)
    total_cols = store.get("total_cols", 1)
    
    if col_index >= total_cols: col_index = 0

    total_rows = len(df)
    start = page * PAGE_SIZE
    end = min(start + PAGE_SIZE, total_rows)
    page_df = df.iloc[start:end]

    content = ""
    if not page_df.empty:
        number_col = page_df.iloc[:, col_index]
        clean_numbers = pd.to_numeric(number_col, errors='coerce').dropna().astype('int64').astype(str)
        if not clean_numbers.empty:
            content = "\n".join(clean_numbers)

    if content:
        # Send content in a new message, formatted as code for easy copying
        bot.send_message(chat_id, f"```\n{content}\n```")
        bot.answer_callback_query(call.id, "Numbers sent as a new message.")
    else:
        bot.answer_callback_query(call.id, "No numbers to copy on this page.")

@bot.callback_query_handler(func=lambda call: call.data == "col_info")
def col_info_dummy(call):
    """Handles the dummy column info button."""
    bot.answer_callback_query(call.id, "This just shows the current column.")


# --- Webhook Handling (No changes needed) ---
@server.route('/' + BOT_TOKEN, methods=['POST'])
def get_message():
    json_string = request.get_data().decode('utf-8')
    update = Update.de_json(json_string) # Use the imported Update class
    bot.process_new_updates([update])
    return "!", 200

@server.route("/")
def webhook():
    bot.remove_webhook()
    # URL will be: https://your-app-name.onrender.com/BOT_TOKEN
    bot.set_webhook(url='https://' + os.environ.get("RENDER_EXTERNAL_HOSTNAME") + '/' + BOT_TOKEN)
    return "Webhook set!", 200

if __name__ == "__main__":
    # This part is for local testing only, Render will not use it.
    print("Bot is running locally...")
    bot.remove_webhook()
    bot.polling() # Use polling for local testing
    # server.run(host="0.0.0.0", port=int(os.environ.get('PORT', 5000)))
