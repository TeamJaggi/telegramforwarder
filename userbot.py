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
                  username TEXT)''')
    
    # Default settings
    c.execute("INSERT OR IGNORE INTO settings (name, value) VALUES ('forwarding_enabled', 'true')")
    c.execute("INSERT OR IGNORE INTO settings (name, value) VALUES ('edit_sync', 'false')")
    c.execute("INSERT OR IGNORE INTO settings (name, value) VALUES ('delete_sync', 'false')")
    
    # Add yourself as the first admin
    c.execute("INSERT OR IGNORE INTO admins (user_id, username) VALUES (?, ?)", 
              (ADMIN_USER_ID, "Owner"))
    
    conn.commit()
    conn.close()

init_db()  # Initialize database when script starts


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
            self.channel_pairs[source_id] = target_id
            
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
            self.channel_pairs[source_id] = target_id
            success = True
        except sqlite3.IntegrityError:
            success = False
        conn.close()
        return success
        
    def remove_channel_pair(self, source_id):
        conn = sqlite3.connect('auto_forward.db')
        c = conn.cursor()
        c.execute("DELETE FROM channel_pairs WHERE source_id=?", (source_id,))
        conn.commit()
        conn.close()
        
        if source_id in self.channel_pairs:
            del self.channel_pairs[source_id]
            
    def get_all_channel_pairs(self):
        return self.channel_pairs.items()
        
    def set_setting(self, name, value):
        conn = sqlite3.connect('auto_forward.db')
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO settings (name, value) VALUES (?, ?)",
                  (name, value))
        conn.commit()
        conn.close()
        
        # Update current instance
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
        conn = sqlite3.connect('auto_forward.db')
        c = conn.cursor()
        c.execute("DELETE FROM admins WHERE user_id=?", (user_id,))
        conn.commit()
        conn.close()
        
    def get_all_admins(self):
        conn = sqlite3.connect('auto_forward.db')
        c = conn.cursor()
        c.execute("SELECT user_id, username FROM admins")
        admins = c.fetchall()
        conn.close()
        return admins

bot = ForwardBot()

# Admin check decorator
def admin_required(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not bot.is_admin(user_id):
            await update.message.reply_text("❌ You are not authorized to use this command.")
            return
        return await func(update, context)
    return wrapper

@admin_required
async def add_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        message_text = update.message.text
        
        # Remove "/add_edit" or "/addword"
        command_text = message_text.replace('/add_edit', '').replace('/addword', '').strip()
        
        if '/' not in command_text:
            await update.message.reply_text("❌ Format: /add_edit old_text/new_text")
            return
            
        # Split by first '/'
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
        
        # Remove "/addlink"
        command_text = message_text.replace('/addlink', '').strip()
        
        # Split by space
        if ' ' in command_text:
            parts = command_text.split(' ', 1)
            old_link = parts[0].strip()
            new_link = parts[1].strip()
        else:
            await update.message.reply_text("❌ Format: /addlink old_link new_link")
            return
        
        # Basic validation
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

@admin_required
async def reset_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect('auto_forward.db')
    c = conn.cursor()
    c.execute("DELETE FROM channel_pairs")
    c.execute("DELETE FROM edits")
    c.execute("DELETE FROM links")
    c.execute("DELETE FROM settings")
    
    # Default settings
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
            await update.message.reply_text("❌ Format: /removepair source_channel_id")
            return
            
        source_id = int(context.args[0])
        bot.remove_channel_pair(source_id)
        await update.message.reply_text(f"✅ Channel pair removed for source: {source_id}")

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

@admin_required
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

@admin_required
async def remove_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not context.args:
            await update.message.reply_text("❌ Format: /removeadmin user_id")
            return
            
        user_id = int(context.args[0])
        bot.remove_admin(user_id)
        await update.message.reply_text(f"✅ Admin removed: {user_id}")

    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

@admin_required
async def list_admins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admins = bot.get_all_admins()
    if admins:
        response = "👑 Admins:\n\n" + "\n".join([f"ID: {user_id}, Name: {username}" for user_id, username in admins])
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
        text = event.raw_text

        # Apply edits
        conn = sqlite3.connect("auto_forward.db")
        c = conn.cursor()
        c.execute("SELECT old_text, new_text FROM edits")
        edits = c.fetchall()
        
        # Apply link replacements
        c.execute("SELECT old_link, new_link FROM links")
        links = c.fetchall()
        conn.close()

        for old, new in edits:
            text = text.replace(old, new)
            
        for old, new in links:
            text = text.replace(old, new)

        # Send to target using user account
        target_id = bot.channel_pairs[event.chat_id]
        if text.strip():
            await client.send_message(target_id, text)

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

    await client.start()
    await app.initialize()
    await app.start()

    print("✅ Bot and client both started")
    
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
