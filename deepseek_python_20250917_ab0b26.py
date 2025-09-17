from flask import Flask
import threading
import os
import time

app = Flask(__name__)

@app.route('/')
def home():
    return "✅ 𝑇𝑟𝑦𝑖𝑛𝑔 𝑇𝑜 𝑇𝑎𝑐𝑘𝑙𝑒 𝑆𝑒𝑡𝑏𝑎𝑐𝑘 𝑇𝐺 - @MrJaggiX!"

def run_flask():
    port = int(os.environ.get("PORT", 5000))  
    app.run(host="0.0.0.0", port=port)

# Flask ko background thread me start karo
threading.Thread(target=run_flask, daemon=True).start()

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
import aiosqlite
from concurrent.futures import ThreadPoolExecutor

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

# Thread pool for database operations
db_executor = ThreadPoolExecutor(max_workers=5)

# DB setup
async def init_db():
    async with aiosqlite.connect('auto_forward.db') as conn:
        # Create tables if they don't exist
        await conn.execute('''CREATE TABLE IF NOT EXISTS channel_pairs
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      source_id INTEGER,
                      target_id INTEGER,
                      filter_keywords TEXT,
                      UNIQUE(source_id, target_id))''')
                      
        await conn.execute('''CREATE TABLE IF NOT EXISTS edits
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      old_text TEXT,
                      new_text TEXT)''')
        
        await conn.execute('''CREATE TABLE IF NOT EXISTS links
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      old_link TEXT,
                      new_link TEXT)''')
        
        await conn.execute('''CREATE TABLE IF NOT EXISTS settings
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      name TEXT UNIQUE,
                      value TEXT)''')
        
        await conn.execute('''CREATE TABLE IF NOT EXISTS admins
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      user_id INTEGER UNIQUE,
                      username TEXT,
                      is_owner BOOLEAN DEFAULT FALSE)''')
        
        # Add message mapping table to track forwarded messages
        await conn.execute('''CREATE TABLE IF NOT EXISTS message_mapping
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      source_message_id INTEGER,
                      source_channel_id INTEGER,
                      target_message_id INTEGER,
                      target_channel_id INTEGER,
                      timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                      UNIQUE(source_message_id, source_channel_id, target_channel_id))''')
        
        # Create index for faster lookups
        await conn.execute('''CREATE INDEX IF NOT EXISTS idx_message_mapping 
                              ON message_mapping(source_channel_id, source_message_id)''')
        await conn.execute('''CREATE INDEX IF NOT EXISTS idx_channel_pairs 
                              ON channel_pairs(source_id)''')
        
        # Default settings
        await conn.execute("INSERT OR IGNORE INTO settings (name, value) VALUES ('forwarding_enabled', 'true')")
        await conn.execute("INSERT OR IGNORE INTO settings (name, value) VALUES ('edit_sync', 'false')")
        await conn.execute("INSERT OR IGNORE INTO settings (name, value) VALUES ('delete_sync', 'false')")
        await conn.execute("INSERT OR IGNORE INTO settings (name, value) VALUES ('text_only', 'false')")
        await conn.execute("INSERT OR IGNORE INTO settings (name, value) VALUES ('max_concurrent_tasks', '10')")
        
        # Add yourself as the owner
        await conn.execute("INSERT OR IGNORE INTO admins (user_id, username, is_owner) VALUES (?, ?, ?)", 
                  (OWNER_USER_ID, "Owner", True))
        
        await conn.commit()

# Initialize database in an async way
asyncio.run(init_db())

class ForwardBot:
    def __init__(self):
        self.channel_pairs = {}
        self.channel_filters = {}  # Store filter keywords for each channel pair
        self.message_mapping = defaultdict(dict)  # source_channel_id -> {source_message_id: {target_channel_id: target_message_id}}
        self.semaphore = None
        self.max_concurrent_tasks = 10
        asyncio.run(self.load_settings())
        asyncio.run(self.load_channel_pairs())
        asyncio.run(self.load_message_mapping())
        self.last_processed_message = {}  # Track last processed message per channel
        self.processing_tasks = set()  # Track currently processing tasks
        
    async def load_channel_pairs(self):
        async with aiosqlite.connect('auto_forward.db') as conn:
            cursor = await conn.execute("SELECT source_id, target_id, filter_keywords FROM channel_pairs")
            results = await cursor.fetchall()
            
        self.channel_pairs = {}
        self.channel_filters = {}
        for source_id, target_id, filter_keywords in results:
            if source_id not in self.channel_pairs:
                self.channel_pairs[source_id] = []
                self.channel_filters[source_id] = {}
                
            self.channel_pairs[source_id].append(target_id)
            self.channel_filters[source_id][target_id] = filter_keywords
            
    async def load_message_mapping(self):
        async with aiosqlite.connect('auto_forward.db') as conn:
            cursor = await conn.execute("SELECT source_message_id, source_channel_id, target_message_id, target_channel_id FROM message_mapping")
            results = await cursor.fetchall()
            
        self.message_mapping = defaultdict(dict)
        for source_msg_id, source_chan_id, target_msg_id, target_chan_id in results:
            if source_chan_id not in self.message_mapping:
                self.message_mapping[source_chan_id] = {}
            
            if source_msg_id not in self.message_mapping[source_chan_id]:
                self.message_mapping[source_chan_id][source_msg_id] = {}
                
            self.message_mapping[source_chan_id][source_msg_id][target_chan_id] = target_msg_id
            
    async def save_message_mapping(self, source_message_id, source_channel_id, target_message_id, target_channel_id):
        try:
            async with aiosqlite.connect('auto_forward.db') as conn:
                await conn.execute("INSERT OR REPLACE INTO message_mapping (source_message_id, source_channel_id, target_message_id, target_channel_id) VALUES (?, ?, ?, ?)",
                          (source_message_id, source_channel_id, target_message_id, target_channel_id))
                await conn.commit()
                
                if source_channel_id not in self.message_mapping:
                    self.message_mapping[source_channel_id] = {}
                
                if source_message_id not in self.message_mapping[source_channel_id]:
                    self.message_mapping[source_channel_id][source_message_id] = {}
                    
                self.message_mapping[source_channel_id][source_message_id][target_channel_id] = target_message_id
                
                return True
        except Exception as e:
            logger.error(f"Error saving message mapping: {e}")
            return False
        
    async def delete_message_mapping(self, source_message_id, source_channel_id, target_channel_id=None):
        try:
            async with aiosqlite.connect('auto_forward.db') as conn:
                if target_channel_id:
                    await conn.execute("DELETE FROM message_mapping WHERE source_message_id=? AND source_channel_id=? AND target_channel_id=?", 
                             (source_message_id, source_channel_id, target_channel_id))
                else:
                    await conn.execute("DELETE FROM message_mapping WHERE source_message_id=? AND source_channel_id=?", 
                             (source_message_id, source_channel_id))
                    
                await conn.commit()
                
                if source_channel_id in self.message_mapping and source_message_id in self.message_mapping[source_channel_id]:
                    if target_channel_id:
                        if target_channel_id in self.message_mapping[source_channel_id][source_message_id]:
                            del self.message_mapping[source_channel_id][source_message_id][target_channel_id]
                            if not self.message_mapping[source_channel_id][source_message_id]:
                                del self.message_mapping[source_channel_id][source_message_id]
                    else:
                        del self.message_mapping[source_channel_id][source_message_id]
        except Exception as e:
            logger.error(f"Error deleting message mapping: {e}")
                
    async def load_settings(self):
        async with aiosqlite.connect('auto_forward.db') as conn:
            cursor = await conn.execute("SELECT value FROM settings WHERE name='forwarding_enabled'")
            result = await cursor.fetchone()
            self.forwarding_enabled = result and result[0] == 'true'
            
            cursor = await conn.execute("SELECT value FROM settings WHERE name='edit_sync'")
            result = await cursor.fetchone()
            self.edit_sync = result and result[0] == 'true'
            
            cursor = await conn.execute("SELECT value FROM settings WHERE name='delete_sync'")
            result = await cursor.fetchone()
            self.delete_sync = result and result[0] == 'true'
            
            cursor = await conn.execute("SELECT value FROM settings WHERE name='text_only'")
            result = await cursor.fetchone()
            self.text_only = result and result[0] == 'true'
            
            cursor = await conn.execute("SELECT value FROM settings WHERE name='max_concurrent_tasks'")
            result = await cursor.fetchone()
            if result:
                self.max_concurrent_tasks = int(result[0])
            
        self.semaphore = asyncio.Semaphore(self.max_concurrent_tasks)

    async def add_channel_pair(self, source_id, target_id, filter_keywords=None):
        try:
            async with aiosqlite.connect('auto_forward.db') as conn:
                await conn.execute("INSERT INTO channel_pairs (source_id, target_id, filter_keywords) VALUES (?, ?, ?)",
                          (source_id, target_id, filter_keywords))
                await conn.commit()
                
                if source_id not in self.channel_pairs:
                    self.channel_pairs[source_id] = []
                    self.channel_filters[source_id] = {}
                    
                self.channel_pairs[source_id].append(target_id)
                self.channel_filters[source_id][target_id] = filter_keywords
                
                return True
        except Exception as e:
            logger.error(f"Error adding channel pair: {e}")
            return False
        
    async def update_channel_filter(self, source_id, target_id, filter_keywords):
        try:
            async with aiosqlite.connect('auto_forward.db') as conn:
                await conn.execute("UPDATE channel_pairs SET filter_keywords = ? WHERE source_id = ? AND target_id = ?",
                          (filter_keywords, source_id, target_id))
                await conn.commit()
                
                if source_id in self.channel_filters and target_id in self.channel_filters[source_id]:
                    self.channel_filters[source_id][target_id] = filter_keywords
                    
                return True
        except Exception as e:
            logger.error(f"Error updating filter: {e}")
            return False
        
    async def remove_channel_pair(self, source_id, target_id=None):
        try:
            async with aiosqlite.connect('auto_forward.db') as conn:
                if target_id:
                    await conn.execute("DELETE FROM channel_pairs WHERE source_id=? AND target_id=?", (source_id, target_id))
                else:
                    await conn.execute("DELETE FROM channel_pairs WHERE source_id=?", (source_id,))
                    
                await conn.commit()
                
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
        except Exception as e:
            logger.error(f"Error removing channel pair: {e}")
            
    def get_all_channel_pairs(self):
        pairs = []
        for source_id, target_ids in self.channel_pairs.items():
            for target_id in target_ids:
                filter_keywords = self.channel_filters.get(source_id, {}).get(target_id, None)
                pairs.append((source_id, target_id, filter_keywords))
        return pairs
        
    async def set_setting(self, name, value):
        try:
            async with aiosqlite.connect('auto_forward.db') as conn:
                await conn.execute("INSERT OR REPLACE INTO settings (name, value) VALUES (?, ?)",
                          (name, value))
                await conn.commit()
                
            if name == 'forwarding_enabled':
                self.forwarding_enabled = value == 'true'
            elif name == 'edit_sync':
                self.edit_sync = value == 'true'
            elif name == 'delete_sync':
                self.delete_sync = value == 'true'
            elif name == 'text_only':
                self.text_only = value == 'true'
            elif name == 'max_concurrent_tasks':
                self.max_concurrent_tasks = int(value)
                self.semaphore = asyncio.Semaphore(self.max_concurrent_tasks)
        except Exception as e:
            logger.error(f"Error setting setting: {e}")
            
    async def is_admin(self, user_id):
        try:
            async with aiosqlite.connect('auto_forward.db') as conn:
                cursor = await conn.execute("SELECT user_id FROM admins WHERE user_id=?", (user_id,))
                result = await cursor.fetchone()
                return result is not None
        except Exception as e:
            logger.error(f"Error checking admin: {e}")
            return False
        
    async def is_owner(self, user_id):
        try:
            async with aiosqlite.connect('auto_forward.db') as conn:
                cursor = await conn.execute("SELECT user_id FROM admins WHERE user_id=? AND is_owner=TRUE", (user_id,))
                result = await cursor.fetchone()
                return result is not None
        except Exception as e:
            logger.error(f"Error checking owner: {e}")
            return False
        
    async def add_admin(self, user_id, username):
        try:
            async with aiosqlite.connect('auto_forward.db') as conn:
                await conn.execute("INSERT INTO admins (user_id, username) VALUES (?, ?)", 
                         (user_id, username))
                await conn.commit()
                return True
        except Exception as e:
            logger.error(f"Error adding admin: {e}")
            return False
        
    async def remove_admin(self, user_id):
        if await self.is_owner(user_id):
            return False
            
        try:
            async with aiosqlite.connect('auto_forward.db') as conn:
                await conn.execute("DELETE FROM admins WHERE user_id=?", (user_id,))
                await conn.commit()
                return True
        except Exception as e:
            logger.error(f"Error removing admin: {e}")
            return False
        
    async def get_all_admins(self):
        try:
            async with aiosqlite.connect('auto_forward.db') as conn:
                cursor = await conn.execute("SELECT user_id, username, is_owner FROM admins")
                admins = await cursor.fetchall()
                return admins
        except Exception as e:
            logger.error(f"Error getting admins: {e}")
            return []
        
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

    async def get_edits_and_links(self):
        try:
            async with aiosqlite.connect('auto_forward.db') as conn:
                cursor = await conn.execute("SELECT old_text, new_text FROM edits")
                edits = await cursor.fetchall()
                
                cursor = await conn.execute("SELECT old_link, new_link FROM links")
                links = await cursor.fetchall()
                
                return edits, links
        except Exception as e:
            logger.error(f"Error getting edits and links: {e}")
            return [], []

bot = ForwardBot()

def admin_required(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not await bot.is_admin(user_id):
            await update.message.reply_text("➢𝑌𝑜𝑢 𝐴𝑟𝑒 𝑁𝑜𝑡 𝐴𝑢𝑡ℎ𝑜𝑟𝑖𝑠𝑒𝑑 𝑡𝑜 𝑢𝑠𝑒 𝑡ℎ𝑖𝑠 𝐶𝑜𝑚𝑚𝑎𝑛𝑑 🤓🤝")
            return
        return await func(update, context)
    return wrapper

def owner_required(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not await bot.is_owner(user_id):
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
        
        async with aiosqlite.connect('auto_forward.db') as conn:
            await conn.execute("INSERT INTO edits (old_text, new_text) VALUES (?, ?)", (old_text, new_text))
            await conn.commit()
        
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
        
        async with aiosqlite.connect('auto_forward.db') as conn:
            await conn.execute("INSERT INTO links (old_link, new_link) VALUES (?, ?)", (old_link, new_link))
            await conn.commit()
        
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
        async with aiosqlite.connect('auto_forward.db') as conn:
            await conn.execute("DELETE FROM edits WHERE old_text=?", (old_text,))
            await conn.commit()
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
        async with aiosqlite.connect('auto_forward.db') as conn:
            await conn.execute("DELETE FROM links WHERE old_link=?", (old_link,))
            await conn.commit()
        await update.message.reply_text(f"✅ Link replacement removed: {old_link}")

    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

@admin_required
async def show_edits(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with aiosqlite.connect('auto_forward.db') as conn:
        cursor = await conn.execute("SELECT old_text, new_text FROM edits")
        edits = await cursor.fetchall()
        
        cursor = await conn.execute("SELECT old_link, new_link FROM links")
        links = await cursor.fetchall()

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
        await bot.set_setting('forwarding_enabled', 'true' if new_status else 'false')
        
        status_text = "ON ✅" if new_status else "OFF ❌"
        await update.message.reply_text(f"✅ Forwarding turned {status_text}")

    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

@admin_required
async def stop_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await bot.set_setting('forwarding_enabled', 'false')
    await update.message.reply_text("🛑 Forwarding stopped")

@admin_required
async def check_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status = "ON ✅" if bot.forwarding_enabled else "OFF ❌"
    edit_status = "ON ✅" if bot.edit_sync else "OFF ❌"
    delete_status = "ON ✅" if bot.delete_sync else "OFF ❌"
    text_only_status = "ON ✅" if bot.text_only else "OFF ❌"
    
    channel_pairs = bot.get_all_channel_pairs()
    if channel_pairs:
        channels_text = "\n".join([f"Source: {src} → Target: {tgt} | Filter: {filt if filt else 'None'}" for src, tgt, filt in channel_pairs])
        await update.message.reply_text(
            f"⚙️ Settings:\n"
            f"Forwarding: {status}\n"
            f"Edit Sync: {edit_status}\n"
            f"Delete Sync: {delete_status}\n"
            f"Text Only Mode: {text_only_status}\n"
            f"Max Concurrent Tasks: {bot.max_concurrent_tasks}\n\n"
            f"📡 Channel Pairs:\n{channels_text}"
        )
    else:
        await update.message.reply_text("No channel pairs set up yet")

@owner_required
async def reset_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with aiosqlite.connect('auto_forward.db') as conn:
        await conn.execute("DELETE FROM channel_pairs")
        await conn.execute("DELETE FROM edits")
        await conn.execute("DELETE FROM links")
        await conn.execute("DELETE FROM settings")
        await conn.execute("DELETE FROM message_mapping")
        
        await conn.execute("INSERT INTO settings (name, value) VALUES ('forwarding_enabled', 'true')")
        await conn.execute("INSERT INTO settings (name, value) VALUES ('edit_sync', 'false')")
        await conn.execute("INSERT INTO settings (name, value) VALUES ('delete_sync', 'false')")
        await conn.execute("INSERT INTO settings (name, value) VALUES ('text_only', 'false')")
        await conn.execute("INSERT INTO settings (name, value) VALUES ('max_concurrent_tasks', '10')")
        
        await conn.commit()
    
    await bot.load_channel_pairs()
    await bot.load_settings()
    await bot.load_message_mapping()
    
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
        
        success = await bot.add_channel_pair(source_id, target_id, filter_keywords)
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
            
        success = await bot.update_channel_filter(source_id, target_id, filter_keywords)
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
        
        await bot.remove_channel_pair(source_id, target_id)
        
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
        async with aiosqlite.connect('auto_forward.db') as conn:
            await conn.execute("INSERT INTO edits (old_text, new_text) VALUES (?, ?)", (text_to_block, ''))
            await conn.commit()
        
        await update.message.reply_text(f"✅ Content blocked: {text_to_block}")

    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

@admin_required
async def toggle_edit_sync(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_status = not bot.edit_sync
    await bot.set_setting('edit_sync', 'true' if new_status else 'false')
    
    status_text = "ON ✅" if new_status else "OFF ❌"
    await update.message.reply_text(f"✅ Edit Sync turned {status_text}")

@admin_required
async def toggle_delete_sync(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_status = not bot.delete_sync
    await bot.set_setting('delete_sync', 'true' if new_status else 'false')
    
    status_text = "ON ✅" if new_status else "OFF ❌"
    await update.message.reply_text(f"✅ Delete Sync turned {status_text}")

@admin_required
async def toggle_text_only(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_status = not bot.text_only
    await bot.set_setting('text_only', 'true' if new_status else 'false')
    
    status_text = "ON ✅" if new_status else "OFF ❌"
    await update.message.reply_text(f"✅ Text Only Mode turned {status_text}\n\n"
                                   f"अब केवल text messages ही forward होंगे, media files नहीं।")

@owner_required
async def add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not context.args:
            await update.message.reply_text("➢ Format: /addadmin user_id [username]")
            return
            
        user_id = int(context.args[0])
        username = context.args[1] if len(context.args) > 1 else "Unknown"
        
        success = await bot.add_admin(user_id, username)
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
        success = await bot.remove_admin(user_id)
        if success:
            await update.message.reply_text(f"✅ Admin removed: {user_id}")
        else:
            await update.message.reply_text("😎 Cannot remove the owner or user not found")

    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

@admin_required
async def list_admins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admins = await bot.get_all_admins()
    if admins:
        response = "👑 Admins:\n\n" + "\n".join([f"ID: {user_id}, Name: {username}{' (Owner)' if is_owner else ''}" for user_id, username, is_owner in admins])
        await update.message.reply_text(response)
    else:
        await update.message.reply_text("🤔 No admins found")

@admin_required
async def set_concurrent_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not context.args:
            await update.message.reply_text(f"Current max concurrent tasks: {bot.max_concurrent_tasks}")
            return
            
        max_tasks = int(context.args[0])
        if max_tasks < 1 or max_tasks > 50:
            await update.message.reply_text("Please enter a value between 1 and 50")
            return
            
        await bot.set_setting('max_concurrent_tasks', str(max_tasks))
        await update.message.reply_text(f"✅ Max concurrent tasks set to {max_tasks}")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await bot.is_admin(user_id):
        await update.message.reply_text("➢𝑊𝑎𝑛𝑡 𝑇𝑜 𝐴𝑐𝑐𝑒𝑠𝑠 𝑇ℎ𝑖𝑠 𝐵𝑜𝑡 𝐶𝑜𝑛𝑡𝑎𝑐𝑡 𝐵𝑜𝑡 𝐴𝑑𝑚𝑖𝑛 🎗")
        return
        
    await update.message.reply_text(
        "🤖 Welcome to the Auto Forward Bot!\n\n"
        "📚 Available Commands:\n"
        "• /start - Show this message\n"
        "• /addpair - Add a channel pair\n"
        "• /removepair - Remove a channel pair\n"
        "• /setfilter - Set filter for a channel pair\n"
        "• /listpairs - List all channel pairs\n"
        "• /addword - Add text replacement\n"
        "• /addlink - Add link replacement\n"
        "• /removeword - Remove text replacement\n"
        "• /removelink - Remove link replacement\n"
        "• /showreps - Show all replacements\n"
        "• /forward - Toggle forwarding on/off\n"
        "• /editsync - Toggle edit sync\n"
        "• /deletesync - Toggle delete sync\n"
        "• /textonly - Toggle text only mode\n"
        "• /settings - Show current settings\n"
        "• /block - Block specific content\n"
        "• /addadmin - Add an admin (Owner only)\n"
        "• /removeadmin - Remove an admin (Owner only)\n"
        "• /listadmins - List all admins\n"
        "• /maxtasks - Set max concurrent tasks\n"
        "• /reset - Reset all settings (Owner only)\n"
        "• /stop - Stop forwarding\n\n"
        "📝 Use /help command for detailed instructions"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await bot.is_admin(user_id):
        await update.message.reply_text("➢𝑊𝑎𝑛𝑡 𝑇𝑜 𝐴𝑐𝑐𝑒𝑠𝑠 𝑇ℎ𝑖𝑠 𝐵𝑜𝑡 𝐶𝑜𝑛𝑡𝑎𝑐𝑡 𝐵𝑜𝑡 𝐴𝑑𝑚𝑖𝑛 🎗")
        return
        
    await update.message.reply_text(
        "🤖 Auto Forward Bot Help\n\n"
        "📚 Setup Instructions:\n"
        "1. Add the bot as admin in both source and target channels with necessary permissions\n"
        "2. Use /addpair source_channel_id target_channel_id to create a forwarding pair\n"
        "3. Use /setfilter to add keyword filtering (optional)\n"
        "4. Use /addword and /addlink to set up text/link replacements (optional)\n\n"
        "📝 Channel IDs:\n"
        "• Channel IDs are negative numbers (e.g., -100123456789)\n"
        "• To get a channel ID, forward a message from that channel to @userinfobot\n\n"
        "🔧 Advanced Features:\n"
        "• Use /editsync and /deletesync to enable edit and delete synchronization\n"
        "• Use /textonly to forward only text messages\n"
        "• Use /maxtasks to adjust performance for high-volume channels\n\n"
        "📊 Monitoring:\n"
        "• Use /settings to check current configuration\n"
        "• Use /listpairs to see all channel pairs\n"
        "• Use /showreps to see all text/link replacements"
    )

# Message processing functions
async def process_message(event, source_id, target_id, message_text, media=None):
    """Process and forward a single message"""
    try:
        async with bot.semaphore:
            # Check if we should forward this message based on filters
            if not bot.should_forward_message(message_text, source_id, target_id):
                logger.info(f"Skipping message due to filter: {source_id} -> {target_id}")
                return None

            # Apply text replacements
            edits, links = await bot.get_edits_and_links()
            processed_text = message_text
            
            if processed_text:
                for old_text, new_text in edits:
                    processed_text = processed_text.replace(old_text, new_text)
                
                for old_link, new_link in links:
                    processed_text = processed_text.replace(old_link, new_link)

            # Forward the message
            if bot.text_only and media:
                # Text-only mode: only forward text
                if processed_text:
                    sent_message = await client.send_message(target_id, processed_text)
                    return sent_message
                return None
            else:
                # Normal mode: forward with media if available
                if media:
                    sent_message = await client.send_file(target_id, media, caption=processed_text)
                else:
                    sent_message = await client.send_message(target_id, processed_text)
                
                return sent_message
                
    except Exception as e:
        logger.error(f"Error forwarding message: {e}")
        return None

@client.on(events.NewMessage)
async def handle_new_message(event):
    if not bot.forwarding_enabled:
        return
        
    try:
        source_id = event.chat_id
        if source_id not in bot.channel_pairs:
            return
            
        # Skip if it's our own message to prevent loops
        if event.message and event.message.sender_id == (await client.get_me()).id:
            return
            
        message_text = event.message.text or event.message.caption or ""
        media = event.message.media if not bot.text_only else None
        
        # Create tasks for all target channels
        tasks = []
        for target_id in bot.channel_pairs[source_id]:
            task = asyncio.create_task(
                process_message_and_save_mapping(event, source_id, target_id, message_text, media)
            )
            tasks.append(task)
            
        # Wait for all tasks to complete
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
            
    except Exception as e:
        logger.error(f"Error in handle_new_message: {e}")

async def process_message_and_save_mapping(event, source_id, target_id, message_text, media):
    """Process a message and save the mapping between source and target messages"""
    try:
        sent_message = await process_message(event, source_id, target_id, message_text, media)
        if sent_message:
            await bot.save_message_mapping(
                event.message.id, source_id, 
                sent_message.id, target_id
            )
    except Exception as e:
        logger.error(f"Error processing message: {e}")

@client.on(events.MessageEdited)
async def handle_edit(event):
    if not bot.forwarding_enabled or not bot.edit_sync:
        return
        
    try:
        source_id = event.chat_id
        if source_id not in bot.message_mapping or event.message.id not in bot.message_mapping[source_id]:
            return
            
        message_text = event.message.text or event.message.caption or ""
        
        # Apply text replacements
        edits, links = await bot.get_edits_and_links()
        processed_text = message_text
        
        if processed_text:
            for old_text, new_text in edits:
                processed_text = processed_text.replace(old_text, new_text)
            
            for old_link, new_link in links:
                processed_text = processed_text.replace(old_link, new_link)
        
        # Get all target messages that need to be updated
        target_messages = bot.message_mapping[source_id][event.message.id]
        
        # Create edit tasks
        tasks = []
        for target_channel_id, target_message_id in target_messages.items():
            task = asyncio.create_task(
                client.edit_message(target_channel_id, target_message_id, processed_text)
            )
            tasks.append(task)
            
        # Execute all edits concurrently
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
            
    except Exception as e:
        logger.error(f"Error in handle_edit: {e}")

@client.on(events.MessageDeleted)
async def handle_delete(event):
    if not bot.forwarding_enabled or not bot.delete_sync:
        return
        
    try:
        for deleted_msg in event.deleted_ids:
            source_id = event.chat_id
            if source_id in bot.message_mapping and deleted_msg in bot.message_mapping[source_id]:
                target_messages = bot.message_mapping[source_id][deleted_msg]
                
                # Create delete tasks
                tasks = []
                for target_channel_id, target_message_id in target_messages.items():
                    task = asyncio.create_task(
                        client.delete_messages(target_channel_id, target_message_id)
                    )
                    tasks.append(task)
                    
                # Execute all deletes concurrently
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)
                    
                # Clean up the mapping
                await bot.delete_message_mapping(deleted_msg, source_id)
                
    except Exception as e:
        logger.error(f"Error in handle_delete: {e}")

async def main():
    # Start the Telegram client
    await client.start()
    
    # Set up the bot application
    application = Application.builder().token(TOKEN).build()

    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("addpair", add_channel_pair))
    application.add_handler(CommandHandler("removepair", remove_channel_pair))
    application.add_handler(CommandHandler("setfilter", set_channel_filter))
    application.add_handler(CommandHandler("listpairs", list_channel_pairs))
    application.add_handler(CommandHandler("addword", add_edit))
    application.add_handler(CommandHandler("addlink", add_link))
    application.add_handler(CommandHandler("removeword", remove_edit))
    application.add_handler(CommandHandler("removelink", remove_link))
    application.add_handler(CommandHandler("showreps", show_edits))
    application.add_handler(CommandHandler("forward", forward_on_off))
    application.add_handler(CommandHandler("editsync", toggle_edit_sync))
    application.add_handler(CommandHandler("deletesync", toggle_delete_sync))
    application.add_handler(CommandHandler("textonly", toggle_text_only))
    application.add_handler(CommandHandler("settings", check_settings))
    application.add_handler(CommandHandler("reset", reset_all))
    application.add_handler(CommandHandler("stop", stop_bot))
    application.add_handler(CommandHandler("block", block_content))
    application.add_handler(CommandHandler("addadmin", add_admin))
    application.add_handler(CommandHandler("removeadmin", remove_admin))
    application.add_handler(CommandHandler("listadmins", list_admins))
    application.add_handler(CommandHandler("maxtasks", set_concurrent_tasks))

    # Start the bot
    await application.initialize()
    await application.start()
    await application.updater.start_polling()

    logger.info("Bot started successfully!")
    
    # Keep the client running
    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())