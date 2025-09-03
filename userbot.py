from flask import Flask
import threading
import os

app = Flask(__name__)

@app.route('/')
def home():
    return "✅ 𝑇𝑟𝑦𝑖𝑛𝑔 𝑇𝑜 𝑇𝑎𝑐𝑘𝑙𝑒 𝑆𝑒𝑡𝑏𝑎𝑐𝑘 𝑇𝐺 - @MrJaggiX!"

def run_flask():
    port = int(os.environ.get("PORT", 5000))  
    app.run(host="0.0.0.0", port=port)

# Flask ko background thread me start karo
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
from collections import defaultdict

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
                  filter_keywords TEXT,
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
    
    # Add message mapping table to track forwarded messages
    c.execute('''CREATE TABLE IF NOT EXISTS message_mapping
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  source_message_id INTEGER,
                  source_channel_id INTEGER,
                  target_message_id INTEGER,
                  target_channel_id INTEGER,
                  UNIQUE(source_message_id, source_channel_id, target_channel_id))''')
    
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
        self.channel_filters = {}  # Store filter keywords for each channel pair
        self.message_mapping = defaultdict(dict)  # source_channel_id -> {source_message_id: {target_channel_id: target_message_id}}
        self.load_settings()
        self.load_channel_pairs()
        self.load_message_mapping()
        
    def load_channel_pairs(self):
        conn = sqlite3.connect('auto_forward.db')
        c = conn.cursor()
        c.execute("SELECT source_id, target_id, filter_keywords FROM channel_pairs")
        results = c.fetchall()
        conn.close()
        
        self.channel_pairs = {}
        self.channel_filters = {}
        for source_id, target_id, filter_keywords in results:
            if source_id not in self.channel_pairs:
                self.channel_pairs[source_id] = []
                self.channel_filters[source_id] = {}
                
            self.channel_pairs[source_id].append(target_id)
            self.channel_filters[source_id][target_id] = filter_keywords
            
    def load_message_mapping(self):
        conn = sqlite3.connect('auto_forward.db')
        c = conn.cursor()
        c.execute("SELECT source_message_id, source_channel_id, target_message_id, target_channel_id FROM message_mapping")
        results = c.fetchall()
        conn.close()
        
        self.message_mapping = defaultdict(dict)
        for source_msg_id, source_chan_id, target_msg_id, target_chan_id in results:
            if source_chan_id not in self.message_mapping:
                self.message_mapping[source_chan_id] = {}
            
            if source_msg_id not in self.message_mapping[source_chan_id]:
                self.message_mapping[source_chan_id][source_msg_id] = {}
                
            self.message_mapping[source_chan_id][source_msg_id][target_chan_id] = target_msg_id
            
    def save_message_mapping(self, source_message_id, source_channel_id, target_message_id, target_channel_id):
        conn = sqlite3.connect('auto_forward.db')
        c = conn.cursor()
        try:
            c.execute("INSERT INTO message_mapping (source_message_id, source_channel_id, target_message_id, target_channel_id) VALUES (?, ?, ?, ?)",
                      (source_message_id, source_channel_id, target_message_id, target_channel_id))
            conn.commit()
            
            if source_channel_id not in self.message_mapping:
                self.message_mapping[source_channel_id] = {}
            
            if source_message_id not in self.message_mapping[source_channel_id]:
                self.message_mapping[source_channel_id][source_message_id] = {}
                
            self.message_mapping[source_channel_id][source_message_id][target_channel_id] = target_message_id
            
            success = True
        except sqlite3.IntegrityError:
            success = False
        conn.close()
        return success
        
    def delete_message_mapping(self, source_message_id, source_channel_id, target_channel_id=None):
        conn = sqlite3.connect('auto_forward.db')
        c = conn.cursor()
        
        if target_channel_id:
            c.execute("DELETE FROM message_mapping WHERE source_message_id=? AND source_channel_id=? AND target_channel_id=?", 
                     (source_message_id, source_channel_id, target_channel_id))
        else:
            c.execute("DELETE FROM message_mapping WHERE source_message_id=? AND source_channel_id=?", 
                     (source_message_id, source_channel_id))
            
        conn.commit()
        conn.close()
        
        if source_channel_id in self.message_mapping and source_message_id in self.message_mapping[source_channel_id]:
            if target_channel_id:
                if target_channel_id in self.message_mapping[source_channel_id][source_message_id]:
                    del self.message_mapping[source_channel_id][source_message_id][target_channel_id]
                    if not self.message_mapping[source_channel_id][source_message_id]:
                        del self.message_mapping[source_channel_id][source_message_id]
            else:
                del self.message_mapping[source_channel_id][source_message_id]
                
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

    def add_channel_pair(self, source_id, target_id, filter_keywords=None):
        conn = sqlite3.connect('auto_forward.db')
        c = conn.cursor()
        try:
            c.execute("INSERT INTO channel_pairs (source_id, target_id, filter_keywords) VALUES (?, ?, ?)",
                      (source_id, target_id, filter_keywords))
            conn.commit()
            
            if source_id not in self.channel_pairs:
                self.channel_pairs[source_id] = []
                self.channel_filters[source_id] = {}
                
            self.channel_pairs[source_id].append(target_id)
            self.channel_filters[source_id][target_id] = filter_keywords
            
            success = True
        except sqlite3.IntegrityError:
            success = False
        conn.close()
        return success
        
    def update_channel_filter(self, source_id, target_id, filter_keywords):
        conn = sqlite3.connect('auto_forward.db')
        c = conn.cursor()
        try:
            c.execute("UPDATE channel_pairs SET filter_keywords = ? WHERE source_id = ? AND target_id = ?",
                      (filter_keywords, source_id, target_id))
            conn.commit()
            
            if source_id in self.channel_filters and target_id in self.channel_filters[source_id]:
                self.channel_filters[source_id][target_id] = filter_keywords
                
            success = True
        except Exception as e:
            print(f"Error updating filter: {e}")
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
                        
                if source_id in self.channel_filters and target_id in self.channel_filters[source_id]:
                    del self.channel_filters[source_id][target_id]
                    if not self.channel_filters[source_id]:
                        del self.channel_filters[source_id]
            else:
                del self.channel_pairs[source_id]
                if source_id in self.channel_filters:
                    del self.channel_filters[source_id]
            
    def get_all_channel_pairs(self):
        pairs = []
        for source_id, target_ids in self.channel_pairs.items():
            for target_id in target_ids:
                filter_keywords = self.channel_filters.get(source_id, {}).get(target_id, None)
                pairs.append((source_id, target_id, filter_keywords))
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
        
    def should_forward_message(self, message_text, source_id, target_id):
        # If no filter is set, forward all messages
        if source_id not in self.channel_filters or target_id not in self.channel_filters[source_id]:
            return True
            
        filter_keywords = self.channel_filters[source_id][target_id]
        if not filter_keywords or filter_keywords.strip() == "":
            return True
            
        # Check if message contains any of the filter keywords
        keywords = [kw.strip() for kw in filter_keywords.split(",") if kw.strip()]
        message_lower = message_text.lower() if message_text else ""
        
        for keyword in keywords:
            if keyword.lower() in message_lower:
                return True
                
        return False

bot = ForwardBot()

def admin_required(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not bot.is_admin(user_id):
            await update.message.reply_text("➢𝑌𝑜𝑢 𝐴𝑟𝑒 𝑁𝑜𝑡 𝐴𝑢𝑡ℎ𝑜𝑟𝑖𝑠𝑒𝑑 𝑡𝑜 𝑢𝑠𝑒 𝑡ℎ𝑖𝑠 𝐶𝑜𝑚𝑚𝑎𝑛𝑑 🤓🤝")
            return
        return await func(update, context)
    return wrapper

def owner_required(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not bot.is_owner(user_id):
            await update.message.reply_text("➢𝑂𝑛𝑙𝑦 𝑡ℎ𝑒 𝑏𝑜𝑡 𝑜𝑤𝑛𝑒𝑟 𝑐𝑎𝑛 𝑢𝑠𝑒 𝑡ℎ𝑖𝑠 𝑐𝑜𝑚𝑚𝑎𝑛𝑑 🎗")
            return
        return await func(update, context)
    return wrapper

@admin_required
async def add_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        message_text = update.message.text
        command_text = message_text.replace('/add_edit', '').replace('/addword', '').strip()
        
        if '/' not in command_text:
            await update.message.reply_text("↳ Format: /addword old_text/new_text")
            return
            
        old_text, new_text = command_text.split('/', 1)
        old_text = old_text.strip()
        new_text = new_text.strip()
        
        if not old_text or not new_text:
            await update.message.reply_text("↳ Both old_text and new_text required")
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
            await update.message.reply_text("↳ Format: /addlink old_link new_link")
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
            await update.message.reply_text("➢ Format: /removeword old_text")
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
            await update.message.reply_text("➢ Format: /removelink old_link")
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
            await update.message.reply_text("➢ Format: /forward on or /forward off")
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
        channels_text = "\n".join([f"Source: {src} → Target: {tgt} | Filter: {filt if filt else 'None'}" for src, tgt, filt in channel_pairs])
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
    c.execute("DELETE FROM message_mapping")
    
    c.execute("INSERT INTO settings (name, value) VALUES ('forwarding_enabled', 'true')")
    c.execute("INSERT INTO settings (name, value) VALUES ('edit_sync', 'false')")
    c.execute("INSERT INTO settings (name, value) VALUES ('delete_sync', 'false')")
    
    conn.commit()
    conn.close()
    
    bot.load_channel_pairs()
    bot.load_settings()
    bot.load_message_mapping()
    
    await update.message.reply_text("✅ All settings reset successfully")

@admin_required
async def add_channel_pair(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not context.args or len(context.args) < 2:
            await update.message.reply_text("➢ Format: /addpair source_channel_id target_channel_id [filter_keywords]")
            await update.message.reply_text("📝 Example: /addpair -100123456789 -100987654321 keyword1,keyword2")
            return
            
        source_id = int(context.args[0])
        target_id = int(context.args[1])
        
        # Check if filter keywords are provided
        filter_keywords = ' '.join(context.args[2:]) if len(context.args) > 2 else None
        
        success = bot.add_channel_pair(source_id, target_id, filter_keywords)
        if success:
            if filter_keywords:
                await update.message.reply_text(f"✅ Channel pair added with filter:\nSource: {source_id} → Target: {target_id}\nFilter: {filter_keywords}")
            else:
                await update.message.reply_text(f"✅ Channel pair added:\nSource: {source_id} → Target: {target_id}")
        else:
            await update.message.reply_text("😃 This channel pair already exists")

    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

@admin_required
async def set_channel_filter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not context.args or len(context.args) < 2:
            await update.message.reply_text("➢ Format: /setfilter source_channel_id target_channel_id filter_keywords")
            await update.message.reply_text("📝 Example: /setfilter -100123456789 -100987654321 keyword1,keyword2,keyword3")
            await update.message.reply_text("📝 To remove filter: /setfilter source_channel_id target_channel_id none")
            return
            
        source_id = int(context.args[0])
        target_id = int(context.args[1])
        
        # Check if the channel pair exists
        if source_id not in bot.channel_pairs or target_id not in bot.channel_pairs[source_id]:
            await update.message.reply_text("🥱 Channel pair does not exist")
            return
            
        # Get filter keywords
        filter_keywords = ' '.join(context.args[2:]) if len(context.args) > 2 else None
        
        # Handle "none" keyword to remove filter
        if filter_keywords and filter_keywords.lower() == "none":
            filter_keywords = None
            
        success = bot.update_channel_filter(source_id, target_id, filter_keywords)
        if success:
            if filter_keywords:
                await update.message.reply_text(f"✅ Filter updated:\nSource: {source_id} → Target: {target_id}\nFilter: {filter_keywords}")
            else:
                await update.message.reply_text(f"✅ Filter removed:\nSource: {source_id} → Target: {target_id}")
        else:
            await update.message.reply_text("🥲 Error updating filter")

    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

@admin_required
async def remove_channel_pair(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not context.args:
            await update.message.reply_text("➢ Format: /removepair source_channel_id [target_channel_id]")
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
        response = "📡 Channel Pairs:\n\n" + "\n".join([f"Source: {src} → Target: {tgt} | Filter: {filt if filt else 'None'}" for src, tgt, filt in channel_pairs])
        await update.message.reply_text(response)
    else:
        await update.message.reply_text("🥱 No channel pairs set up yet")

@admin_required
async def block_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not context.args:
            await update.message.reply_text("➢ Format: /block text_to_block")
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
            await update.message.reply_text("➢ Format: /addadmin user_id [username]")
            return
            
        user_id = int(context.args[0])
        username = context.args[1] if len(context.args) > 1 else "Unknown"
        
        success = bot.add_admin(user_id, username)
        if success:
            await update.message.reply_text(f"✅ Admin added: {user_id} ({username})")
        else:
            await update.message.reply_text("🤔 This user is already an admin")

    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

@owner_required
async def remove_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not context.args:
            await update.message.reply_text("➢ Format: /removeadmin user_id")
            return
            
        user_id = int(context.args[0])
        success = bot.remove_admin(user_id)
        if success:
            await update.message.reply_text(f"✅ Admin removed: {user_id}")
        else:
            await update.message.reply_text("😎 Cannot remove the owner or user not found")

    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

@admin_required
async def list_admins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admins = bot.get_all_admins()
    if admins:
        response = "👑 Admins:\n\n" + "\n".join([f"ID: {user_id}, Name: {username}{' (Owner)' if is_owner else ''}" for user_id, username, is_owner in admins])
        await update.message.reply_text(response)
    else:
        await update.message.reply_text("🤔 No admins found")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not bot.is_admin(user_id):
        await update.message.reply_text("➢𝑊𝑎𝑛𝑡 𝑇𝑜 𝐴𝑐𝑐𝑒𝑠𝑠 𝑇ℎ𝑖𝑠 𝐵𝑜𝑡 𝐶𝑜𝑛𝑡𝑎𝑐𝑡 𝐵𝑜𝑡 𝑂𝑤𝑛𝑒𝑟 @𝑀𝑟𝐽𝑎𝑔𝑔𝑖𝑏𝑜𝑡")
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
        "/setfilter - Set filter keywords\n"
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
                # Check if message should be forwarded based on filter
                if not bot.should_forward_message(formatted_text, event.chat_id, target_id):
                    logger.info(f"Message not forwarded to {target_id} due to filter settings")
                    continue
                
                # Always send as a new message (not forward) to hide "Forwarded from" tag
                if formatted_text:
                    sent_message = await client.send_message(target_id, formatted_text)
                    # Save the mapping between source and target messages
                    if sent_message:
                        bot.save_message_mapping(message.id, event.chat_id, sent_message.id, target_id)
                else:
                    # If no text content, try to forward media with caption
                    if message.media:
                        sent_message = await client.send_file(target_id, message.media, caption=formatted_text if formatted_text else None)
                        # Save the mapping between source and target messages
                        if sent_message:
                            bot.save_message_mapping(message.id, event.chat_id, sent_message.id, target_id)
            except Exception as e:
                logger.error(f"Error sending message to {target_id}: {e}")
                # Fallback: try sending as plain text
                try:
                    if formatted_text:
                        sent_message = await client.send_message(target_id, formatted_text)
                        # Save the mapping between source and target messages
                        if sent_message:
                            bot.save_message_mapping(message.id, event.chat_id, sent_message.id, target_id)
                except Exception as e2:
                    logger.error(f"Fallback also failed: {e2}")

# Handle message edits
@client.on(events.MessageEdited)
async def handle_message_edit(event):
    if not bot.edit_sync or not bot.forwarding_enabled:
        return
        
    # Check if this channel is in our pairs and we have a mapping for this message
    if (event.chat_id in bot.message_mapping and 
        event.message.id in bot.message_mapping[event.chat_id]):
        
        message = event.message
        original_text = message.text
        formatted_text = original_text
        
        # Apply replacements if any
        conn = sqlite3.connect("auto_forward.db")
        c = conn.cursor()
        c.execute("SELECT old_text, new_text FROM edits")
        edits = c.fetchall()
        c.execute("SELECT old_link, new_link FROM links")
        links = c.fetchall()
        conn.close()
        
        if edits or links:
            for old, new in edits:
                if old in formatted_text:
                    formatted_text = formatted_text.replace(old, new)
                    
            for old, new in links:
                if old in formatted_text:
                    formatted_text = formatted_text.replace(old, new)
        
        # Edit all target messages
        target_mappings = bot.message_mapping[event.chat_id][event.message.id]
        for target_channel_id, target_message_id in target_mappings.items():
            try:
                await client.edit_message(target_channel_id, target_message_id, formatted_text)
            except Exception as e:
                logger.error(f"Error editing message in {target_channel_id}: {e}")

# Handle message deletions
@client.on(events.MessageDeleted)
async def handle_message_delete(event):
    if not bot.delete_sync or not bot.forwarding_enabled:
        return
        
    for deleted_message in event.deleted_ids:
        # Check if we have a mapping for this deleted message
        for source_channel_id, messages in bot.message_mapping.items():
            if deleted_message in messages:
                # Delete all target messages
                target_mappings = messages[deleted_message]
                for target_channel_id, target_message_id in target_mappings.items():
                    try:
                        await client.delete_messages(target_channel_id, target_message_id)
                    except Exception as e:
                        logger.error(f"Error deleting message in {target_channel_id}: {e}")
                
                # Remove the mapping
                bot.delete_message_mapping(deleted_message, source_channel_id)

async def main():
    print("Building app and starting client...")
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("forward", forward_on_off))
    app.add_handler(CommandHandler("stop", stop_bot))
    app.add_handler(CommandHandler("settings", check_settings))
    app.add_handler(CommandHandler("reset", reset_all))
    
    app.add_handler(CommandHandler("addpair", add_channel_pair))
    app.add_handler(CommandHandler("setfilter", set_channel_filter))
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
