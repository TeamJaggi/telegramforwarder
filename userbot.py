from telethon import TelegramClient, events
import asyncio
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
import sqlite3

api_id = 123456        #  ai id dalna hai yha 
api_hash = "api hash"  #  api hash dalna hai 

client = TelegramClient("user_session", api_id, api_hash)

# blt token 
TOKEN = "bot token dal yha"

# lgging ke liye 
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# DB setup
def init_db():
    conn = sqlite3.connect('auto_forward.db')
    c = conn.cursor()
    
    # 
    c.execute("DROP TABLE IF EXISTS edits")
    c.execute("DROP TABLE IF EXISTS channels")
    
    # new table ke liye 
    c.execute('''CREATE TABLE IF NOT EXISTS channels
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  source_id INTEGER UNIQUE,
                  target_id INTEGER UNIQUE)''')
                  
    c.execute('''CREATE TABLE IF NOT EXISTS edits
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  old_text TEXT,
                  new_text TEXT)''')
    conn.commit()
    conn.close()

init_db()  # script shuru hone par hi 


class ForwardBot:
    def __init__(self):
        self.load_channels()

    def load_channels(self):
        conn = sqlite3.connect('auto_forward.db')
        c = conn.cursor()
        c.execute("SELECT source_id, target_id FROM channels LIMIT 1")
        result = c.fetchone()
        conn.close()

        if result:
            self.source_id = result[0]
            self.target_id = result[1]
        else:
            self.source_id = None
            self.target_id = None

    def set_channels(self, source_id, target_id):
        conn = sqlite3.connect('auto_forward.db')
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO channels (id, source_id, target_id) VALUES (1, ?, ?)",
                  (source_id, target_id))
        conn.commit()
        conn.close()
        self.source_id = source_id
        self.target_id = target_id

bot = ForwardBot()

async def add_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        args = context.args
        if not args or len(args) != 1 or '/' not in args[0]:
            await update.message.reply_text("❌ formate : /add_edit old_text/new_text")
            return

        old_text, new_text = args[0].split('/', 1)
        conn = sqlite3.connect('auto_forward.db')
        c = conn.cursor()
        c.execute("INSERT INTO edits (old_text, new_text) VALUES (?, ?)", (old_text, new_text))
        conn.commit()
        conn.close()
        await update.message.reply_text(f"✅ edit aff kar diya gaya :\n{old_text} → {new_text}")

    except Exception as e:
        await update.message.reply_text(f"❌  error : {str(e)}")

async def remove_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not context.args:
            await update.message.reply_text("❌ error: /remove_edit old_text")
            return

        old_text = ' '.join(context.args)
        conn = sqlite3.connect('auto_forward.db')
        c = conn.cursor()
        c.execute("DELETE FROM edits WHERE old_text=?", (old_text,))
        conn.commit()
        conn.close()
        await update.message.reply_text(f"✅ edit hataya gaya : {old_text}")

    except Exception as e:
        await update.message.reply_text(f"❌ Error : {str(e)}")

async def show_edits(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect('auto_forward.db')
    c = conn.cursor()
    c.execute("SELECT old_text, new_text FROM edits")
    edits = c.fetchall()
    conn.close()

    if not edits:
        await update.message.reply_text("❌ No Actibe edit found ")
        return

    response = "📜 Actuve Edits :\n" + "\n".join([f"{old} → {new}" for old, new in edits])
    await update.message.reply_text(response)
    
        
@client.on(events.NewMessage)
async def handle_channel_post(event):
    if bot.source_id and event.chat_id == bot.source_id:
        text = event.raw_text

        # apply edits
        conn = sqlite3.connect("auto_forward.db")
        c = conn.cursor()
        c.execute("SELECT old_text, new_text FROM edits")
        edits = c.fetchall()
        conn.close()

        for old, new in edits:
            text = text.replace(old, new)

        # Send to target using user account
        if bot.target_id:
            await client.send_message(bot.target_id, text)

        
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Auto forword bot\n"
        "\n"
        "/set_source -  spurce channel.add karne ke liye \n"
        "/set_target - target channel.set karne ke liye \n"
        "/check_settings - setting dekhne ke liye \n"
        "/add_edit - edit add karne ke liye \n"
        "/remove_edit - edit hatane ke liye\n"
        "/show_edits - edit dekhne ke liye "
    )

async def check_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if bot.source_id and bot.target_id:
        await update.message.reply_text(
            f"⚙️ Setting:\n"
            f"Source Channel: {bot.source_id}\n"
            f"Target channel: {bot.target_id}"
        )
    else:
        await update.message.reply_text("Pahle source channel aur target channel set karo ")
        
async def set_source(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if update.message.reply_to_message and update.message.reply_to_message.forward_from_chat:
            source_id = update.message.reply_to_message.forward_from_chat.id
        elif context.args:
            source_id = int(context.args[0])
        else:
            await update.message.reply_text(""""commond ke sath channel id do
            Example : /set_source -1002675315826""")
            return

        bot.set_channels(source_id, bot.target_id)
        await update.message.reply_text(f"✅ source channel.set : {source_id}")

    except Exception as e:
        await update.message.reply_text(f"error: {str(e)}")

async def set_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if update.message.reply_to_message and update.message.reply_to_message.forward_from_chat:
            target_id = update.message.reply_to_message.forward_from_chat.id
        elif context.args:
            target_id = int(context.args[0])
        else:
            await update.message.reply_text("""commond ke sath channel id do
            Example :  /set_target -1002701768930""")
            return

        bot.set_channels(bot.source_id, target_id)
        await update.message.reply_text(f"✅ Target channel.set : {target_id}")

    except Exception as e:
        await update.message.reply_text(f"Error: {str(e)}")

async def main():
    print("Building app and starting client...")
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("set_source", set_source))
    app.add_handler(CommandHandler("set_target", set_target))
    app.add_handler(CommandHandler("check_settings", check_settings))
    app.add_handler(CommandHandler("add_edit", add_edit))
    app.add_handler(CommandHandler("remove_edit", remove_edit))
    app.add_handler(CommandHandler("show_edits", show_edits))

    await client.start()
    await app.initialize()
    await app.start()

    print("✅ Bot aur  client dino chalu ho gaye ")
    #
    await asyncio.gather(
        client.run_until_disconnected(),
        app.updater.start_polling()
    )

    print("🛑 Bot stopped")
if __name__ == "__main__":
    import asyncio
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"❌ Error: {e}") 
