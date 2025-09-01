from pyrogram import Client, filters
from pyrogram.types import Message
import asyncio
import json
import os
import re
from typing import Dict, List, Tuple, Optional

# Configuration File Path
CONFIG_FILE = "config.json"

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

class AutoForwarderBot:
    def __init__(self):
        self.config = self.load_config()
        self.user_client = None
        self.bot_client = None
        self.initialize_clients()
        
    def load_config(self):
        """Load configuration from file or create default"""
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
        """Initialize user and bot clients"""
        self.user_client = Client(
            name="user_session",
            session_string=self.config["session_string"],
            api_id=self.config["api_id"],
            api_hash=self.config["api_hash"]
        )
        
        self.bot_client = Client(
            name="forward_bot",
            api_id=self.config["api_id"],
            api_hash=self.config["api_hash"],
            bot_token=self.config["bot_token"]
        )
        
        # Register all handlers
        self.register_handlers()
    
    def register_handlers(self):
        """Register all message handlers"""
        
        # Start command
        @self.bot_client.on_message(filters.command("start"))
        async def start_command(client, message: Message):
            await self.start_command_handler(client, message)
        
        # Forward command
        @self.bot_client.on_message(filters.command("forward"))
        async def forward_command(client, message: Message):
            await self.forward_command_handler(client, message)
        
        # Stop command
        @self.bot_client.on_message(filters.command("stop"))
        async def stop_command(client, message: Message):
            await self.stop_command_handler(client, message)
        
        # Settings command
        @self.bot_client.on_message(filters.command("settings"))
        async def settings_command(client, message: Message):
            await self.settings_command_handler(client, message)
        
        # Reset command
        @self.bot_client.on_message(filters.command("reset"))
        async def reset_command(client, message: Message):
            await self.reset_command_handler(client, message)
        
        # Set source command
        @self.bot_client.on_message(filters.command("setsource"))
        async def set_source_command(client, message: Message):
            await self.set_source_command_handler(client, message)
        
        # Remove source command
        @self.bot_client.on_message(filters.command("removesource"))
        async def remove_source_command(client, message: Message):
            await self.remove_source_command_handler(client, message)
        
        # Set target command
        @self.bot_client.on_message(filters.command("settarget"))
        async def set_target_command(client, message: Message):
            await self.set_target_command_handler(client, message)
        
        # Remove target command
        @self.bot_client.on_message(filters.command("removetarget"))
        async def remove_target_command(client, message: Message):
            await self.remove_target_command_handler(client, message)
        
        # Add word replacement
        @self.bot_client.on_message(filters.command("addword"))
        async def add_word_command(client, message: Message):
            await self.add_word_command_handler(client, message)
        
        # Add link replacement
        @self.bot_client.on_message(filters.command("addlink"))
        async def add_link_command(client, message: Message):
            await self.add_link_command_handler(client, message)
        
        # Remove word replacement
        @self.bot_client.on_message(filters.command("removeword"))
        async def remove_word_command(client, message: Message):
            await self.remove_word_command_handler(client, message)
        
        # Remove link replacement
        @self.bot_client.on_message(filters.command("removelink"))
        async def remove_link_command(client, message: Message):
            await self.remove_link_command_handler(client, message)
        
        # View replacements
        @self.bot_client.on_message(filters.command("viewreplacements"))
        async def view_replacements_command(client, message: Message):
            await self.view_replacements_command_handler(client, message)
        
        # Block content
        @self.bot_client.on_message(filters.command("block"))
        async def block_command(client, message: Message):
            await self.block_command_handler(client, message)
        
        # Edit sync toggle
        @self.bot_client.on_message(filters.command("edit_sync"))
        async def edit_sync_command(client, message: Message):
            await self.edit_sync_command_handler(client, message)
        
        # Delete sync toggle
        @self.bot_client.on_message(filters.command("delete_sync"))
        async def delete_sync_command(client, message: Message):
            await self.delete_sync_command_handler(client, message)
        
        # Message handler for forwarding
        @self.user_client.on_message()
        async def message_handler(client, message: Message):
            await self.message_handler_func(client, message)
        
        # Edit message handler
        @self.user_client.on_edited_message()
        async def edit_message_handler(client, message: Message):
            await self.edit_message_handler_func(client, message)
        
        # Delete message handler
        @self.user_client.on_deleted_messages()
        async def delete_message_handler(client, messages):
            await self.delete_message_handler_func(client, messages)
    
    # Command Handlers
    async def start_command_handler(self, client, message: Message):
        """Handle /start command"""
        welcome_text = """
🤖 **Auto Forwarder Bot Started!** ✅

**Available Commands:**
/start - Check if bot is running
/forward - Start forwarding messages
/stop - Stop forwarding messages
/settings - Show current configuration
/reset - Reset all settings

/setsource - Add source channel ID
/removesource - Remove source channel ID
/settarget - Add target channel ID
/removetarget - Remove target channel ID

/addword - Add word replacement rule
/addlink - Add link replacement rule
/removeword - Remove word replacement rule
/removelink - Remove link replacement rule
/viewreplacements - Show all active replacements

/block - Block specific message content
/edit_sync - Toggle edit sync on/off
/delete_sync - Toggle delete sync on/off

**Status:** {}
""".format("✅ Running" if self.config["is_forwarding"] else "❌ Stopped")
        
        await message.reply(welcome_text)
    
    async def forward_command_handler(self, client, message: Message):
        """Handle /forward command"""
        if not self.config["source_chats"] or not self.config["destination_chats"]:
            await message.reply("❌ Please set source and target channels first!")
            return
        
        self.config["is_forwarding"] = True
        self.save_config()
        await message.reply("✅ Forwarding started!")
    
    async def stop_command_handler(self, client, message: Message):
        """Handle /stop command"""
        self.config["is_forwarding"] = False
        self.save_config()
        await message.reply("⏹️ Forwarding stopped!")
    
    async def settings_command_handler(self, client, message: Message):
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
        await message.reply(settings_text)
    
    async def reset_command_handler(self, client, message: Message):
        """Handle /reset command"""
        self.config.update(DEFAULT_CONFIG)
        self.save_config()
        await message.reply("🔄 All settings have been reset to default!")
    
    async def set_source_command_handler(self, client, message: Message):
        """Handle /setsource command"""
        try:
            chat_id = int(message.text.split()[1])
            if chat_id not in self.config["source_chats"]:
                self.config["source_chats"].append(chat_id)
                self.save_config()
                await message.reply(f"✅ Source channel {chat_id} added!")
            else:
                await message.reply("ℹ️ This channel is already in source list!")
        except (IndexError, ValueError):
            await message.reply("❌ Usage: /setsource <channel_id>")
        except Exception as e:
            await message.reply(f"❌ Error: {str(e)}")
    
    async def remove_source_command_handler(self, client, message: Message):
        """Handle /removesource command"""
        try:
            chat_id = int(message.text.split()[1])
            if chat_id in self.config["source_chats"]:
                self.config["source_chats"].remove(chat_id)
                self.save_config()
                await message.reply(f"✅ Source channel {chat_id} removed!")
            else:
                await message.reply("❌ Channel not found in source list!")
        except (IndexError, ValueError):
            await message.reply("❌ Usage: /removesource <channel_id>")
        except Exception as e:
            await message.reply(f"❌ Error: {str(e)}")
    
    async def set_target_command_handler(self, client, message: Message):
        """Handle /settarget command"""
        try:
            chat_id = int(message.text.split()[1])
            if chat_id not in self.config["destination_chats"]:
                self.config["destination_chats"].append(chat_id)
                self.save_config()
                await message.reply(f"✅ Target channel {chat_id} added!")
            else:
                await message.reply("ℹ️ This channel is already in target list!")
        except (IndexError, ValueError):
            await message.reply("❌ Usage: /settarget <channel_id>")
        except Exception as e:
            await message.reply(f"❌ Error: {str(e)}")
    
    async def remove_target_command_handler(self, client, message: Message):
        """Handle /removetarget command"""
        try:
            chat_id = int(message.text.split()[1])
            if chat_id in self.config["destination_chats"]:
                self.config["destination_chats"].remove(chat_id)
                self.save_config()
                await message.reply(f"✅ Target channel {chat_id} removed!")
            else:
                await message.reply("❌ Channel not found in target list!")
        except (IndexError, ValueError):
            await message.reply("❌ Usage: /removetarget <channel_id>")
        except Exception as e:
            await message.reply(f"❌ Error: {str(e)}")
    
    async def add_word_command_handler(self, client, message: Message):
        """Handle /addword command"""
        try:
            parts = message.text.split()
            if len(parts) < 3:
                await message.reply("❌ Usage: /addword <old_word> <new_word>")
                return
            
            old_word = ' '.join(parts[1:-1])
            new_word = parts[-1]
            
            self.config["word_replacements"][old_word] = new_word
            self.save_config()
            await message.reply(f"✅ Word replacement added: '{old_word}' → '{new_word}'")
        except Exception as e:
            await message.reply(f"❌ Error: {str(e)}")
    
    async def add_link_command_handler(self, client, message: Message):
        """Handle /addlink command"""
        try:
            parts = message.text.split()
            if len(parts) < 3:
                await message.reply("❌ Usage: /addlink <old_link> <new_link>")
                return
            
            old_link = parts[1]
            new_link = parts[2]
            
            self.config["link_replacements"][old_link] = new_link
            self.save_config()
            await message.reply(f"✅ Link replacement added: '{old_link}' → '{new_link}'")
        except Exception as e:
            await message.reply(f"❌ Error: {str(e)}")
    
    async def remove_word_command_handler(self, client, message: Message):
        """Handle /removeword command"""
        try:
            word = message.text.split()[1]
            if word in self.config["word_replacements"]:
                del self.config["word_replacements"][word]
                self.save_config()
                await message.reply(f"✅ Word replacement '{word}' removed!")
            else:
                await message.reply("❌ Word not found in replacements!")
        except (IndexError, ValueError):
            await message.reply("❌ Usage: /removeword <word>")
        except Exception as e:
            await message.reply(f"❌ Error: {str(e)}")
    
    async def remove_link_command_handler(self, client, message: Message):
        """Handle /removelink command"""
        try:
            link = message.text.split()[1]
            if link in self.config["link_replacements"]:
                del self.config["link_replacements"][link]
                self.save_config()
                await message.reply(f"✅ Link replacement '{link}' removed!")
            else:
                await message.reply("❌ Link not found in replacements!")
        except (IndexError, ValueError):
            await message.reply("❌ Usage: /removelink <link>")
        except Exception as e:
            await message.reply(f"❌ Error: {str(e)}")
    
    async def view_replacements_command_handler(self, client, message: Message):
        """Handle /viewreplacements command"""
        word_text = "**Word Replacements:**\n" + '\n'.join(
            [f"`{k}` → `{v}`" for k, v in self.config["word_replacements"].items()]
        ) if self.config["word_replacements"] else "**No word replacements**"
        
        link_text = "\n**Link Replacements:**\n" + '\n'.join(
            [f"`{k}` → `{v}`" for k, v in self.config["link_replacements"].items()]
        ) if self.config["link_replacements"] else "\n**No link replacements**"
        
        await message.reply(word_text + link_text)
    
    async def block_command_handler(self, client, message: Message):
        """Handle /block command"""
        try:
            keyword = message.text.split()[1]
            if keyword not in self.config["blocked_keywords"]:
                self.config["blocked_keywords"].append(keyword)
                self.save_config()
                await message.reply(f"✅ Keyword '{keyword}' added to block list!")
            else:
                await message.reply("ℹ️ Keyword already in block list!")
        except (IndexError, ValueError):
            await message.reply("❌ Usage: /block <keyword>")
        except Exception as e:
            await message.reply(f"❌ Error: {str(e)}")
    
    async def edit_sync_command_handler(self, client, message: Message):
        """Handle /edit_sync command"""
        self.config["edit_sync"] = not self.config["edit_sync"]
        self.save_config()
        status = "✅ ON" if self.config["edit_sync"] else "❌ OFF"
        await message.reply(f"🔄 Edit sync turned {status}")
    
    async def delete_sync_command_handler(self, client, message: Message):
        """Handle /delete_sync command"""
        self.config["delete_sync"] = not self.config["delete_sync"]
        self.save_config()
        status = "✅ ON" if self.config["delete_sync"] else "❌ OFF"
        await message.reply(f"🗑️ Delete sync turned {status}")
    
    # Message Handlers
    async def message_handler_func(self, client, message: Message):
        """Handle incoming messages"""
        if not self.config["is_forwarding"]:
            return
        
        if message.chat.id not in self.config["source_chats"]:
            return
        
        # Check for blocked keywords
        text = message.text or message.caption or ""
        if any(keyword in text for keyword in self.config["blocked_keywords"]):
            print(f"Blocked message containing keyword: {text}")
            return
        
        # Apply replacements
        processed_text = self.apply_replacements(text)
        
        try:
            for dest_chat in self.config["destination_chats"]:
                if message.text:
                    await self.bot_client.send_message(
                        dest_chat, 
                        processed_text,
                        reply_to_message_id=message.reply_to_message_id if message.reply_to_message_id else None
                    )
                elif message.photo:
                    await self.bot_client.send_photo(
                        dest_chat,
                        message.photo.file_id,
                        caption=processed_text
                    )
                elif message.video:
                    await self.bot_client.send_video(
                        dest_chat,
                        message.video.file_id,
                        caption=processed_text
                    )
                elif message.document:
                    await self.bot_client.send_document(
                        dest_chat,
                        message.document.file_id,
                        caption=processed_text
                    )
                elif message.audio:
                    await self.bot_client.send_audio(
                        dest_chat,
                        message.audio.file_id,
                        caption=processed_text
                    )
                
            print(f"Message forwarded from {message.chat.id} to {len(self.config['destination_chats'])} destinations")
        except Exception as e:
            print(f"Error forwarding message: {e}")
    
    async def edit_message_handler_func(self, client, message: Message):
        """Handle edited messages"""
        if not self.config["edit_sync"] or not self.config["is_forwarding"]:
            return
        
        # Edit sync logic would go here
        # This requires storing message mappings between source and destination
        print(f"Message edited in {message.chat.id}")
    
    async def delete_message_handler_func(self, client, messages):
        """Handle deleted messages"""
        if not self.config["delete_sync"] or not self.config["is_forwarding"]:
            return
        
        # Delete sync logic would go here
        # This requires storing message mappings between source and destination
        print(f"Messages deleted: {len(messages)}")
    
    def apply_replacements(self, text: str) -> str:
        """Apply word and link replacements to text"""
        if not text:
            return text
        
        # Apply word replacements
        for old_word, new_word in self.config["word_replacements"].items():
            text = text.replace(old_word, new_word)
        
        # Apply link replacements
        for old_link, new_link in self.config["link_replacements"].items():
            text = text.replace(old_link, new_link)
        
        return text
    
    async def run(self):
        """Run both clients"""
        await self.user_client.start()
        await self.bot_client.start()
        print("Bot started successfully!")
        
        # Keep running
        await asyncio.Event().wait()

# Main execution
if __name__ == "__main__":
    bot = AutoForwarderBot()
    
    # First time setup check
    if (bot.config["api_id"] == DEFAULT_CONFIG["api_id"] or 
        bot.config["api_hash"] == DEFAULT_CONFIG["api_hash"] or
        bot.config["session_string"] == DEFAULT_CONFIG["session_string"] or
        bot.config["bot_token"] == DEFAULT_CONFIG["bot_token"]):
        print("⚠️ Please update config.json with your actual API credentials!")
        print("1. Get API_ID and API_HASH from https://my.telegram.org")
        print("2. Get Bot Token from @BotFather")
        print("3. Generate session string using generate_session.py")
        exit(1)
    
    # Run the bot
    import asyncio
    asyncio.run(bot.run())