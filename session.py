from telethon.sync import TelegramClient
from telethon.sessions import StringSession

API_ID = 29657994  # yha session id dalna hai 
API_HASH = "85f461c4f637911d79c65da1fc2bdd77"  # api hash
SESSION_NAME = "user_session"  # session ka name 

with TelegramClient(SESSION_NAME, API_ID, API_HASH) as client:
    print("session ban gya ", SESSION_NAME + ".session")
