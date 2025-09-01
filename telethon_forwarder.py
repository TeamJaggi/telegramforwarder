from telethon import TelegramClient, events, Button
from telethon.sessions import StringSession
import json
import os
import asyncio
import re

# Configuration
CONFIG_FILE = "telethon_config.json"

# Default Configuration
DEFAULT_CONFIG = {
    "api_id": 1234567,
    "api_hash": "your_api_hash_here",
    "session_string": "your_session_string_here",
    "bot_token": "your_bot_token_here",
    "source_chats": [],
    "destination_chats": [],
    "word_replacements": {},
    "link_replacements": {},
    "blocked_keywords": [],
    "edit_sync": True,
    "delete_sync": True,
    "is_forwarding": False
}

class TelethonForwarderBot:
    def __init__(self):
        self.config = self.load_config()
        self.client = None
        self.bot = None
        self.initialize_clients()
        
    def load_config(self):
        """Load configuration from file"""
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        else:
            with open(CONFIG_FILE, 'w') as f:
                json.dump(DEFAULT_CONFIG, f, indent=4)
            return DEFAULT_CONFIG.copy()
    
    def save_config(self):
        """Save configuration to file"""
        with open(CONFIG_FILE, 'w') as f:
            json.dump(self.config, f, indent=4)
    
    def initialize_clients(self):
        """Initialize user client and bot"""
        # User client (for monitoring channels)
        self.client = TelegramClient(
            StringSession(self.config["session_string"]),
            self.config["api_id"],
            self.config["api_hash"]
        )
        
        # Bot client (for sending messages)
        self.bot = TelegramClient(
            "bot_session",
            self.config["api_id"],
            self.config["api_hash"]
        ).start(bot_token=self.config["bot_token"])
        
        # Register event handlers
        self.register_handlers()
    
    def register_handlers(self):
        """Register all event handlers"""
        
        # Bot command handlers
        @self.bot.on(events.NewMessage(pattern='/start'))
        async def start_handler(event):
            await self.start_command(event)
        
        @self.bot.on(events.NewMessage(pattern='/forward'))
        async def forward_handler(event):
            await self.forward_command(event)
        
        @self.bot.on(events.NewMessage(pattern='/stop'))
        async def stop_handler(event):
            await self.stop_command(event)
        
        @self.bot.on(events.NewMessage(pattern='/settings'))
        async def settings_handler(event):
            await self.settings_command(event)
        
        @self.bot.on(events.NewMessage(pattern='/reset'))
        async def reset_handler(event):
            await self.reset_command(event)
        
        @self.bot.on(events.NewMessage(pattern='/setsource'))
        async def set_source_handler(event):
            await self.set_source_command(event)
        
        @self.bot.on(events.NewMessage(pattern='/removesource'))
        async def remove_source_handler(event):
            await self.remove_source_command(event)
        
        @self.bot.on(events.NewMessage(pattern='/settarget'))
        async def set_target_handler(event):
            await self.set_target_command(event)
        
        @self.bot.on(events.NewMessage(pattern='/removetarget'))
        async def remove_target_handler(event):
            await self.remove_target_command(event)
        
        @self.bot.on(events.NewMessage(pattern='/addword'))
        async def add_word_handler(event):
            await self.add_word_command(event)
        
        @self.bot.on(events.NewMessage(pattern='/addlink'))
        async def add_link_handler(event):
            await self.add_link_command(event)
        
        @self.bot.on(events.NewMessage(pattern='/removeword'))
        async def remove_word_handler(event):
            await self.remove_word_command(event)
        
        @self.bot.on(events.NewMessage(pattern='/removelink'))
        async def remove_link_handler(event):
            await self.remove_link_command(event)
        
        @self.bot.on(events.NewMessage(pattern='/viewreplacements'))
        async def view_replacements_handler(event):
            await self.view_replacements_command(event)
        
        @self.bot.on(events.NewMessage(pattern='/block'))
        async def block_handler(event):
            await self.block_command(event)
        
        @self.bot.on(events.NewMessage(pattern='/edit_sync'))
        async def edit_sync_handler(event):
            await self.edit_sync_command(event)
        
        @self.bot.on(events.NewMessage(pattern='/delete_sync'))
        async def delete_sync_handler(event):
            await self.delete_sync_command(event)
        
        # Message forwarding handler
        @self.client.on(events.NewMessage)
        async def message_handler(event):
            await self.handle_message(event)
    
    # Command Handlers
    async def start_command(self, event):
        """Handle /start command"""
        welcome_text = """
🤖 **Telethon Auto Forwarder Bot Started!** ✅

**Available Commands:**
/start - Check bot status
/forward - Start forwarding
/stop - Stop forwarding
/settings - Show settings
/reset - Reset all settings

/setsource - Add source channel
/removesource - Remove source channel
/settarget - Add target channel
/removetarget - Remove target channel

/addword - Add word replacement
/addlink - Add link replacement
/removeword - Remove word replacement
/removelink - Remove link replacement
/viewreplacements - Show replacements

/block - Block keywords
/edit_sync - Toggle edit sync
/delete_sync - Toggle delete sync

**Status:** {}
""".format("✅ Running" if self.config["is_forwarding"] else "❌ Stopped")
        
        await event.reply(welcome_text)
    
    async def forward_command(self, event):
        """Handle /forward command"""
        if not self.config["source_chats"] or not self.config["destination_chats"]:
            await event.reply("❌ Please set source and target channels first!")
            return
        
        self.config["is_forwarding"] = True
        self.save_config()
        await event.reply("✅ Forwarding started!")
    
    async def stop_command(self, event):
        """Handle /stop command"""
        self.config["is_forwarding"] = False
        self.save_config()
        await event.reply("⏹️ Forwarding stopped!")
    
    async def settings_command(self, event):
        """Handle /settings command"""
        settings_text = """
⚙️ **Current Settings:**

**Source Channels:** {}
**Target Channels:** {}
**Word Replacements:** {} rules
**Link Replacements:** {} rules
**Blocked Keywords:** {} words
**Edit Sync:** {}
**Delete Sync:** {}
**Forwarding Status:** {}
""".format(
    len(self.config["source_chats"]),
    len(self.config["destination_chats"]),
    len(self.config["word_replacements"]),
    len(self.config["link_replacements"]),
    len(self.config["blocked_keywords"]),
    "✅ On" if self.config["edit_sync"] else "❌ Off",
    "✅ On" if self.config["delete_sync"] else "❌ Off",
    "✅ Running" if self.config["is_forwarding"] else "❌ Stopped"
)
        await event.reply(settings_text)
    
    async def reset_command(self, event):
        """Handle /reset command"""
        self.config.update(DEFAULT_CONFIG)
        self.save_config()
        await event.reply("🔄 All settings reset to default!")
    
    async def set_source_command(self, event):
        """Handle /setsource command"""
        try:
            args = event.text.split()
            if len(args) < 2:
                await event.reply("❌ Usage: /setsource <channel_id>")
                return
            
            chat_id = int(args[1])
            if chat_id not in self.config["source_chats"]:
                self.config["source_chats"].append(chat_id)
                self.save_config()
                await event.reply(f"✅ Source channel {chat_id} added!")
            else:
                await event.reply("ℹ️ Channel already in source list!")
        except Exception as e:
            await event.reply(f"❌ Error: {str(e)}")
    
    async def remove_source_command(self, event):
        """Handle /removesource command"""
        try:
            args = event.text.split()
            if len(args) < 2:
                await event.reply("❌ Usage: /removesource <channel_id>")
                return
            
            chat_id = int(args[1])
            if chat_id in self.config["source_chats"]:
                self.config["source_chats"].remove(chat_id)
                self.save_config()
                await event.reply(f"✅ Source channel {chat_id} removed!")
            else:
                await event.reply("❌ Channel not found in source list!")
        except Exception as e:
            await event.reply(f"❌ Error: {str(e)}")
    
    async def set_target_command(self, event):
        """Handle /settarget command"""
        try:
            args = event.text.split()
            if len(args) < 2:
                await event.reply("❌ Usage: /settarget <channel_id>")
                return
            
            chat_id = int(args[1])
            if chat_id not in self.config["destination_chats"]:
                self.config["destination_chats"].append(chat_id)
                self.save_config()
                await event.reply(f"✅ Target channel {chat_id} added!")
            else:
                await event.reply("ℹ️ Channel already in target list!")
        except Exception as e:
            await event.reply(f"❌ Error: {str(e)}")
    
    async def remove_target_command(self, event):
        """Handle /removetarget command"""
        try:
            args = event.text.split()
            if len(args) < 2:
                await event.reply("❌ Usage: /removetarget <channel_id>")
                return
            
            chat_id = int(args[1])
            if chat_id in self.config["destination_chats"]:
                self.config["destination_chats"].remove(chat_id)
                self.save_config()
                await event.reply(f"✅ Target channel {chat_id} removed!")
            else:
                await event.reply("❌ Channel not found in target list!")
        except Exception as e:
            await event.reply(f"❌ Error: {str(e)}")
    
    async def add_word_command(self, event):
        """Handle /addword command"""
        try:
            args = event.text.split()
            if len(args) < 3:
                await event.reply("❌ Usage: /addword <old_word> <new_word>")
                return
            
            old_word = ' '.join(args[1:-1])
            new_word = args[-1]
            
            self.config["word_replacements"][old_word] = new_word
            self.save_config()
            await event.reply(f"✅ Word replacement added: '{old_word}' → '{new_word}'")
        except Exception as e:
            await event.reply(f"❌ Error: {str(e)}")
    
    async def add_link_command(self, event):
        """Handle /addlink command"""
        try:
            args = event.text.split()
            if len(args) < 3:
                await event.reply("❌ Usage: /addlink <old_link> <new_link>")
                return
            
            old_link = args[1]
            new_link = args[2]
            
            self.config["link_replacements"][old_link] = new_link
            self.save_config()
            await event.reply(f"✅ Link replacement added: '{old_link}' → '{new_link}'")
        except Exception as e:
            await event.reply(f"❌ Error: {str(e)}")
    
    async def remove_word_command(self, event):
        """Handle /removeword command"""
        try:
            args = event.text.split()
            if len(args) < 2:
                await event.reply("❌ Usage: /removeword <word>")
                return
            
            word = args[1]
            if word in self.config["word_replacements"]:
                del self.config["word_replacements"][word]
                self.save_config()
                await event.reply(f"✅ Word replacement '{word}' removed!")
            else:
                await event.reply("❌ Word not found in replacements!")
        except Exception as e:
            await event.reply(f"❌ Error: {str(e)}")
    
    async def remove_link_command(self, event):
        """Handle /removelink command"""
        try:
            args = event.text.split()
            if len(args) < 2:
                await event.reply("❌ Usage: /removelink <link>")
                return
            
            link = args[1]
            if link in self.config["link_replacements"]:
                del self.config["link_replacements"][link]
                self.save_config()
                await event.reply(f"✅ Link replacement '{link}' removed!")
            else:
                await event.reply("❌ Link not found in replacements!")
        except Exception as e:
            await event.reply(f"❌ Error: {str(e)}")
    
    async def view_replacements_command(self, event):
        """Handle /viewreplacements command"""
        word_text = "**Word Replacements:**\n" + '\n'.join(
            [f"`{k}` → `{v}`" for k, v in self.config["word_replacements"].items()]
        ) if self.config["word_replacements"] else "**No word replacements**"
        
        link_text = "\n**Link Replacements:**\n" + '\n'.join(
            [f"`{k}` → `{v}`" for k, v in self.config["link_replacements"].items()]
        ) if self.config["link_replacements"] else "\n**No link replacements**"
        
        await event.reply(word_text + link_text)
    
    async def block_command(self, event):
        """Handle /block command"""
        try:
            args = event.text.split()
            if len(args) < 2:
                await event.reply("❌ Usage: /block <keyword>")
                return
            
            keyword = args[1]
            if keyword not in self.config["blocked_keywords"]:
                self.config["blocked_keywords"].append(keyword)
                self.save_config()
                await event.reply(f"✅ Keyword '{keyword}' added to block list!")
            else:
                await event.reply("ℹ️ Keyword already in block list!")
        except Exception as e:
            await event.reply(f"❌ Error: {str(e)}")
    
    async def edit_sync_command(self, event):
        """Handle /edit_sync command"""
        self.config["edit_sync"] = not self.config["edit_sync"]
        self.save_config()
        status = "✅ ON" if self.config["edit_sync"] else "❌ OFF"
        await event.reply(f"🔄 Edit sync turned {status}")
    
    async def delete_sync_command(self, event):
        """Handle /delete_sync command"""
        self.config["delete_sync"] = not self.config["delete_sync"]
        self.save_config()
        status = "✅ ON" if self.config["delete_sync"] else "❌ OFF"
        await event.reply(f"🗑️ Delete sync turned {status}")
    
    async def handle_message(self, event):
        """Handle incoming messages for forwarding"""
        if not self.config["is_forwarding"]:
            return
        
        if event.chat_id not in self.config["source_chats"]:
            return
        
        # Check for blocked keywords
        text = event.text or (event.message.message if event.message else "")
        if not text:
            return
        
        if any(keyword.lower() in text.lower() for keyword in self.config["blocked_keywords"]):
            print(f"🚫 Blocked message containing keyword")
            return
        
        # Apply replacements
        processed_text = self.apply_replacements(text)
        
        try:
            for dest_chat in self.config["destination_chats"]:
                try:
                    if event.message.media:
                        # Forward media with caption
                        await self.bot.send_file(
                            dest_chat,
                            event.message.media,
                            caption=processed_text
                        )
                    else:
                        # Send text message
                        await self.bot.send_message(
                            dest_chat,
                            processed_text
                        )
                    print(f"✅ Forwarded to {dest_chat}")
                except Exception as e:
                    print(f"❌ Failed to forward to {dest_chat}: {e}")
            
            print(f"✅ Message forwarded from {event.chat_id}")
        except Exception as e:
            print(f"❌ Error in forwarding: {e}")
    
    def apply_replacements(self, text):
        """Apply word and link replacements"""
        for old_word, new_word in self.config["word_replacements"].items():
            text = text.replace(old_word, new_word)
        
        for old_link, new_link in self.config["link_replacements"].items():
            text = text.replace(old_link, new_link)
        
        return text
    
    async def run(self):
        """Run both clients"""
        await self.client.start()
        print("User client started!")
        
        await self.bot.start()
        print("Bot started!")
        
        # Keep running
        await asyncio.Event().wait()
 
        # Run the bot
        bot = TelethonForwarderBot()
        
        # Check if config needs setup
        if (bot.config["api_id"] == DEFAULT_CONFIG["api_id"] or
            bot.config["api_hash"] == DEFAULT_CONFIG["api_hash"] or
            bot.config["session_string"] == DEFAULT_CONFIG["session_string"] or
            bot.config["bot_token"] == DEFAULT_CONFIG["bot_token"]):
            print("⚠️ Please update telethon_config.json with your credentials!")
            print("1. Get API_ID and API_HASH from https://my.telegram.org")
            print("2. Get Bot Token from @BotFather")
            print("3. Generate session string: python telethon_forwarder.py generate_session")
            exit(1)
        
        # Run the bot
        print("Starting Telethon Auto Forwarder...")
        asyncio.run(bot.run())
