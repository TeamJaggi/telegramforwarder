from flask import Flask
import threading
import os

# ===== Dummy Flask Server =====
app = Flask(__name__)

@app.route('/')
def home():
    return "✅ Bot is running on Render!"

def run_flask():
    port = int(os.environ.get("PORT", 5000))  # Render ka port
    app.run(host="0.0.0.0", port=port)

# Flask ko alag thread me start karo
threading.Thread(target=run_flask).start()
import os
from telethon.sessions import StringSession
from telethon import TelegramClient, events
import asyncio
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
import sqlite3
import re

api_id = int(os.getenv("API_ID")) 
api_hash = os.getenv("API_HASH")

# Session string from environment variable
session_str = os.getenv("SESSION_STRING") 
client = TelegramClient(StringSession(session_str), api_id, api_hash)

# Bot token
TOKEN = os.getenv("BOT_TOKEN")

# Your Telegram User ID (replace with your actual ID)
OWNER_USER_ID = int(os.getenv("ADMIN_USER_ID"))

# Logging setup
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# DB setup
def init_db():
    conn = sqlite3.connect('auto_forward.db')
    c = conn.cursor()
    
    # Create tables if they don't exist
    c.execute('''CREATE TABLE IF NOT EXISTS channel_pairs
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  source_id INTEGER,
                  target_id INTEGER,
                  UNIQUE(source_id, target_id))''')
                  
    c.execute('''CREATE TABLE IF NOT EXISTS edits
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  old_text TEXT,
                  new_text TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS links
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  old_link TEXT,
                  new_link TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS settings
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  name TEXT UNIQUE,
                  value TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS admins
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER UNIQUE,
                  username TEXT,
                  is_owner BOOLEAN DEFAULT FALSE)''')
    
    # Default settings
    c.execute("INSERT OR IGNORE INTO settings (name, value) VALUES ('forwarding_enabled', 'true')")
    c.execute("INSERT OR IGNORE INTO settings (name, value) VALUES ('edit_sync', 'false')")
    c.execute("INSERT OR IGNORE INTO settings (name, value) VALUES ('delete_sync', 'false')")
    
    # Add yourself as the owner
    c.execute("INSERT OR IGNORE INTO admins (user_id, username, is_owner) VALUES (?, ?, ?)", 
              (OWNER_USER_ID, "Owner", True))
    
    conn.commit()
    conn.close()

init_db()

class ForwardBot:
    def __init__(self):
        self.channel_pairs = {}
        self.load_settings()
        self.load_channel_pairs()
        
    def load_channel_pairs(self):
        conn = sqlite3.connect('auto_forward.db')
        c = conn.cursor()
        c.execute("SELECT source_id, target_id FROM channel_pairs")
        results = c.fetchall()
        conn.close()
        
        self.channel_pairs = {}
        for source_id, target_id in results:
            if source_id not in self.channel_pairs:
                self.channel_pairs[source_id] = []
            self.channel_pairs[source_id].append(target_id)
            
    def load_settings(self):
        conn = sqlite3.connect('auto_forward.db')
        c = conn.cursor()
        
        c.execute("SELECT value FROM settings WHERE name='forwarding_enabled'")
        result = c.fetchone()
        self.forwarding_enabled = result and result[0] == 'true'
        
        c.execute("SELECT value FROM settings WHERE name='edit_sync'")
        result = c.fetchone()
        self.edit_sync = result and result[0] == 'true'
        
        c.execute("SELECT value FROM settings WHERE name='delete_sync'")
        result = c.fetchone()
        self.delete_sync = result and result[0] == 'true'
        
        conn.close()

    def add_channel_pair(self, source_id, target_id):
        conn = sqlite3.connect('auto_forward.db')
        c = conn.cursor()
        try:
            c.execute("INSERT INTO channel_pairs (source_id, target_id) VALUES (?, ?)",
                      (source_id, target_id))
            conn.commit()
            
            if source_id not in self.channel_pairs:
                self.channel_pairs[source_id] = []
            self.channel_pairs[source_id].append(target_id)
            
            success = True
        except sqlite3.IntegrityError:
            success = False
        conn.close()
        return success
        
    def remove_channel_pair(self, source_id, target_id=None):
        conn = sqlite3.connect('auto_forward.db')
        c = conn.cursor()
        
        if target_id:
            c.execute("DELETE FROM channel_pairs WHERE source_id=? AND target_id=?", (source_id, target_id))
        else:
            c.execute("DELETE FROM channel_pairs WHERE source_id=?", (source_id,))
            
        conn.commit()
        conn.close()
        
        if source_id in self.channel_pairs:
            if target_id:
                if target_id in self.channel_pairs[source_id]:
                    self.channel_pairs[source_id].remove(target_id)
                    if not self.channel_pairs[source_id]:
                        del self.channel_pairs[source_id]
            else:
                del self.channel_pairs[source_id]
            
    def get_all_channel_pairs(self):
        pairs = []
        for source_id, target_ids in self.channel_pairs.items():
            for target_id in target_ids:
                pairs.append((source_id, target_id))
        return pairs
        
    def set_setting(self, name, value):
        conn = sqlite3.connect('auto_forward.db')
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO settings (name, value) VALUES (?, ?)",
                  (name, value))
        conn.commit()
        conn.close()
        
        if name == 'forwarding_enabled':
            self.forwarding_enabled = value == 'true'
        elif name == 'edit_sync':
            self.edit_sync = value == 'true'
        elif name == 'delete_sync':
            self.delete_sync = value == 'true'
            
    def is_admin(self, user_id):
        conn = sqlite3.connect('auto_forward.db')
        c = conn.cursor()
        c.execute("SELECT user_id FROM admins WHERE user_id=?", (user_id,))
        result = c.fetchone()
        conn.close()
        return result is not None
        
    def is_owner(self, user_id):
        conn = sqlite3.connect('auto_forward.db')
        c = conn.cursor()
        c.execute("SELECT user_id FROM admins WHERE user_id=? AND is_owner=TRUE", (user_id,))
        result = c.fetchone()
        conn.close()
        return result is not None
        
    def add_admin(self, user_id, username):
        conn = sqlite3.connect('auto_forward.db')
        c = conn.cursor()
        try:
            c.execute("INSERT INTO admins (user_id, username) VALUES (?, ?)", 
                     (user_id, username))
            conn.commit()
            success = True
        except sqlite3.IntegrityError:
            success = False
        conn.close()
        return success
        
    def remove_admin(self, user_id):
        if self.is_owner(user_id):
            return False
            
        conn = sqlite3.connect('auto_forward.db')
        c = conn.cursor()
        c.execute("DELETE FROM admins WHERE user_id=?", (user_id,))
        conn.commit()
        conn.close()
        return True
        
    def get_all_admins(self):
        conn = sqlite3.connect('auto_forward.db')
        c = conn.cursor()
        c.execute("SELECT user_id, username, is_owner FROM admins")
        admins = c.fetchall()
        conn.close()
        return admins

bot = ForwardBot()

def admin_required(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not bot.is_admin(user_id):
            await update.message.reply_text("❌ You are not authorized to use this command.")
            return
        return await func(update, context)
    return wrapper

def owner_required(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not bot.is_owner(user_id):
            await update.message.reply_text("❌ Only the bot owner can use this command.")
            return
        return await func(update, context)
    return wrapper

@admin_required
async def add_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        message_text = update.message.text
        command_text = message_text.replace('/add_edit', '').replace('/addword', '').strip()
        
        if '/' not in command_text:
            await update.message.reply_text("❌ Format: /add_edit old_text/new_text")
            return
            
        old_text, new_text = command_text.split('/', 1)
        old_text = old_text.strip()
        new_text = new_text.strip()
        
        if not old_text or not new_text:
            await update.message.reply_text("❌ Both old_text and new_text required")
            return
        
        conn = sqlite3.connect('auto_forward.db')
        c = conn.cursor()
        c.execute("INSERT INTO edits (old_text, new_text) VALUES (?, ?)", (old_text, new_text))
        conn.commit()
        conn.close()
        
        await update.message.reply_text(f"✅ Replacement added:\n{old_text} → {new_text}")

    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

@admin_required
async def add_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        message_text = update.message.text
        command_text = message_text.replace('/addlink', '').strip()
        
        if ' ' in command_text:
            parts = command_text.split(' ', 1)
            old_link = parts[0].strip()
            new_link = parts[1].strip()
        else:
            await update.message.reply_text("❌ Format: /addlink old_link new_link")
            return
        
        if not old_link or not new_link:
            await update.message.reply_text("❌ Both links required")
            return
        
        conn = sqlite3.connect('auto_forward.db')
        c = conn.cursor()
        c.execute("INSERT INTO links (old_link, new_link) VALUES (?, ?)", (old_link, new_link))
        conn.commit()
        conn.close()
        
        await update.message.reply_text(f"✅ Link replacement added:\n{old_link} → {new_link}")

    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

@admin_required
async def remove_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not context.args:
            await update.message.reply_text("❌ Format: /removeword old_text")
            return

        old_text = ' '.join(context.args)
        conn = sqlite3.connect('auto_forward.db')
        c = conn.cursor()
        c.execute("DELETE FROM edits WHERE old_text=?", (old_text,))
        conn.commit()
        conn.close()
        await update.message.reply_text(f"✅ Replacement removed: {old_text}")

    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

@admin_required
async def remove_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not context.args:
            await update.message.reply_text("❌ Format: /removelink old_link")
            return

        old_link = ' '.join(context.args)
        conn = sqlite3.connect('auto_forward.db')
        c = conn.cursor()
        c.execute("DELETE FROM links WHERE old_link=?", (old_link,))
        conn.commit()
        conn.close()
        await update.message.reply_text(f"✅ Link replacement removed: {old_link}")

    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

@admin_required
async def show_edits(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect('auto_forward.db')
    c = conn.cursor()
    c.execute("SELECT old_text, new_text FROM edits")
    edits = c.fetchall()
    
    c.execute("SELECT old_link, new_link FROM links")
    links = c.fetchall()
    conn.close()

    if not edits and not links:
        await update.message.reply_text("❌ No active replacements found")
        return

    response = "📜 Active Replacements:\n\n"
    
    if edits:
        response += "📝 Text Replacements:\n" + "\n".join([f"{old} → {new}" for old, new in edits]) + "\n\n"
    
    if links:
        response += "🔗 Link Replacements:\n" + "\n".join([f"{old} → {new}" for old, new in links])

    await update.message.reply_text(response)

@admin_required
async def forward_on_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not context.args:
            status = "ON ✅" if bot.forwarding_enabled else "OFF ❌"
            await update.message.reply_text(f"📊 Forwarding Status: {status}")
            return
            
        status = context.args[0].lower()
        if status not in ['on', 'off']:
            await update.message.reply_text("❌ Format: /forward on or /forward off")
            return
            
        new_status = status == 'on'
        bot.set_setting('forwarding_enabled', 'true' if new_status else 'false')
        
        status_text = "ON ✅" if new_status else "OFF ❌"
        await update.message.reply_text(f"✅ Forwarding turned {status_text}")

    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

@admin_required
async def stop_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bot.set_setting('forwarding_enabled', 'false')
    await update.message.reply_text("🛑 Forwarding stopped")

@admin_required
async def check_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status = "ON ✅" if bot.forwarding_enabled else "OFF ❌"
    edit_status = "ON ✅" if bot.edit_sync else "OFF ❌"
    delete_status = "ON ✅" if bot.delete_sync else "OFF ❌"
    
    channel_pairs = bot.get_all_channel_pairs()
    if channel_pairs:
        channels_text = "\n".join([f"Source: {src} → Target: {tgt}" for src, tgt in channel_pairs])
        await update.message.reply_text(
            f"⚙️ Settings:\n"
            f"Forwarding: {status}\n"
            f"Edit Sync: {edit_status}\n"
            f"Delete Sync: {delete_status}\n\n"
            f"📡 Channel Pairs:\n{channels_text}"
        )
    else:
        await update.message.reply_text("No channel pairs set up yet")

@owner_required
async def reset_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect('auto_forward.db')
    c = conn.cursor()
    c.execute("DELETE FROM channel_pairs")
    c.execute("DELETE FROM edits")
    c.execute("DELETE FROM links")
    c.execute("DELETE FROM settings")
    
    c.execute("INSERT INTO settings (name, value) VALUES ('forwarding_enabled', 'true')")
    c.execute("INSERT INTO settings (name, value) VALUES ('edit_sync', 'false')")
    c.execute("INSERT INTO settings (name, value) VALUES ('delete_sync', 'false')")
    
    conn.commit()
    conn.close()
    
    bot.load_channel_pairs()
    bot.load_settings()
    
    await update.message.reply_text("✅ All settings reset successfully")

@admin_required
async def add_channel_pair(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not context.args or len(context.args) < 2:
            await update.message.reply_text("❌ Format: /addpair source_channel_id target_channel_id")
            return
            
        source_id = int(context.args[0])
        target_id = int(context.args[1])
        
        success = bot.add_channel_pair(source_id, target_id)
        if success:
            await update.message.reply_text(f"✅ Channel pair added:\nSource: {source_id} → Target: {target_id}")
        else:
            await update.message.reply_text("❌ This channel pair already exists")

    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

@admin_required
async def remove_channel_pair(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not context.args:
            await update.message.reply_text("❌ Format: /removepair source_channel_id [target_channel_id]")
            return
            
        source_id = int(context.args[0])
        target_id = int(context.args[1]) if len(context.args) > 1 else None
        
        bot.remove_channel_pair(source_id, target_id)
        
        if target_id:
            await update.message.reply_text(f"✅ Channel pair removed:\nSource: {source_id} → Target: {target_id}")
        else:
            await update.message.reply_text(f"✅ All channel pairs removed for source: {source_id}")

    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

@admin_required
async def list_channel_pairs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    channel_pairs = bot.get_all_channel_pairs()
    if channel_pairs:
        response = "📡 Channel Pairs:\n\n" + "\n".join([f"Source: {src} → Target: {tgt}" for src, tgt in channel_pairs])
        await update.message.reply_text(response)
    else:
        await update.message.reply_text("❌ No channel pairs set up yet")

@admin_required
async def block_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not context.args:
            await update.message.reply_text("❌ Format: /block text_to_block")
            return

        text_to_block = ' '.join(context.args)
        conn = sqlite3.connect('auto_forward.db')
        c = conn.cursor()
        c.execute("INSERT INTO edits (old_text, new_text) VALUES (?, ?)", (text_to_block, ''))
        conn.commit()
        conn.close()
        
        await update.message.reply_text(f"✅ Content blocked: {text_to_block}")

    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

@admin_required
async def toggle_edit_sync(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_status = not bot.edit_sync
    bot.set_setting('edit_sync', 'true' if new_status else 'false')
    
    status_text = "ON ✅" if new_status else "OFF ❌"
    await update.message.reply_text(f"✅ Edit Sync turned {status_text}")

@admin_required
async def toggle_delete_sync(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_status = not bot.delete_sync
    bot.set_setting('delete_sync', 'true' if new_status else 'false')
    
    status_text = "ON ✅" if new_status else "OFF ❌"
    await update.message.reply_text(f"✅ Delete Sync turned {status_text}")

@owner_required
async def add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not context.args:
            await update.message.reply_text("❌ Format: /addadmin user_id [username]")
            return
            
        user_id = int(context.args[0])
        username = context.args[1] if len(context.args) > 1 else "Unknown"
        
        success = bot.add_admin(user_id, username)
        if success:
            await update.message.reply_text(f"✅ Admin added: {user_id} ({username})")
        else:
            await update.message.reply_text("❌ This user is already an admin")

    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

@owner_required
async def remove_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not context.args:
            await update.message.reply_text("❌ Format: /removeadmin user_id")
            return
            
        user_id = int(context.args[0])
        success = bot.remove_admin(user_id)
        if success:
            await update.message.reply_text(f"✅ Admin removed: {user_id}")
        else:
            await update.message.reply_text("❌ Cannot remove the owner or user not found")

    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

@admin_required
async def list_admins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admins = bot.get_all_admins()
    if admins:
        response = "👑 Admins:\n\n" + "\n".join([f"ID: {user_id}, Name: {username}{' (Owner)' if is_owner else ''}" for user_id, username, is_owner in admins])
        await update.message.reply_text(response)
    else:
        await update.message.reply_text("❌ No admins found")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not bot.is_admin(user_id):
        await update.message.reply_text("❌ You are not authorized to use this bot.")
        return
        
    status = "ON ✅" if bot.forwarding_enabled else "OFF ❌"
    await update.message.reply_text(
        "🤖 Auto Forward Bot\n"
        f"Status: {status}\n"
        "\n"
        "/start - Bot status check\n"
        "/forward - Forwarding on/off\n"
        "/stop - Forwarding stop\n"
        "/settings - Current settings\n"
        "/reset - Reset all settings\n"
        "\n"
        "/addpair - Add channel pair\n"
        "/removepair - Remove channel pair\n"
        "/listpairs - List all channel pairs\n"
        "\n"
        "/addword - Add text replacement\n"
        "/addlink - Add link replacement\n"
        "/removeword - Remove text replacement\n"
        "/removelink - Remove link replacement\n"
        "/viewreplacements - View all replacements\n"
        "/block - Block specific content\n"
        "\n"
        "/edit_sync - Toggle edit sync\n"
        "/delete_sync - Toggle delete sync\n"
        "\n"
        "/addadmin - Add admin user\n"
        "/removeadmin - Remove admin user\n"
        "/listadmins - List all admins"
    )

@client.on(events.NewMessage)
async def handle_channel_post(event):
    if not bot.forwarding_enabled:
        return
        
    # Check if this channel is in our pairs
    if event.chat_id in bot.channel_pairs:
        message = event.message
        original_text = message.text
        formatted_text = original_text
        
        # Check if we need to apply any replacements
        conn = sqlite3.connect("auto_forward.db")
        c = conn.cursor()
        c.execute("SELECT old_text, new_text FROM edits")
        edits = c.fetchall()
        c.execute("SELECT old_link, new_link FROM links")
        links = c.fetchall()
        conn.close()
        
        has_replacements = False
        if edits or links:
            for old, new in edits:
                if old in formatted_text:
                    formatted_text = formatted_text.replace(old, new)
                    has_replacements = True
                    
            for old, new in links:
                if old in formatted_text:
                    formatted_text = formatted_text.replace(old, new)
                    has_replacements = True
        
        # Send to all target channels for this source
        target_ids = bot.channel_pairs[event.chat_id]
        for target_id in target_ids:
            try:
                # Always send as a new message (not forward) to hide "Forwarded from" tag
                if formatted_text:
                    await client.send_message(target_id, formatted_text)
                else:
                    # If no text content, try to forward media with caption
                    if message.media:
                        await client.send_file(target_id, message.media, caption=formatted_text if formatted_text else None)
            except Exception as e:
                logger.error(f"Error sending message to {target_id}: {e}")
                # Fallback: try sending as plain text
                try:
                    if formatted_text:
                        await client.send_message(target_id, formatted_text)
                except Exception as e2:
                    logger.error(f"Fallback also failed: {e2}")

async def main():
    print("Building app and starting client...")
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("forward", forward_on_off))
    app.add_handler(CommandHandler("stop", stop_bot))
    app.add_handler(CommandHandler("settings", check_settings))
    app.add_handler(CommandHandler("reset", reset_all))
    
    app.add_handler(CommandHandler("addpair", add_channel_pair))
    app.add_handler(CommandHandler("removepair", remove_channel_pair))
    app.add_handler(CommandHandler("listpairs", list_channel_pairs))
    
    app.add_handler(CommandHandler("addword", add_edit))
    app.add_handler(CommandHandler("addlink", add_link))
    app.add_handler(CommandHandler("removeword", remove_edit))
    app.add_handler(CommandHandler("removelink", remove_link))
    app.add_handler(CommandHandler("viewreplacements", show_edits))
    app.add_handler(CommandHandler("block", block_content))
    
    app.add_handler(CommandHandler("edit_sync", toggle_edit_sync))
    app.add_handler(CommandHandler("delete_sync", toggle_delete_sync))
    
    app.add_handler(CommandHandler("addadmin", add_admin))
    app.add_handler(CommandHandler("removeadmin", remove_admin))
    app.add_handler(CommandHandler("listadmins", list_admins))

    # Start the Telethon client first
    await client.start()
    print("Telethon client started")
    
    # Start the Telegram bot
    await app.initialize()
    await app.start()
    print("Telegram bot started")

    # Run both
    await asyncio.gather(
        client.run_until_disconnected(),
        app.updater.start_polling()
    )

if __name__ == "__main__":
    # Create a new event loop for Windows compatibility
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        print("Bot stopped by user")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        loop.close()
