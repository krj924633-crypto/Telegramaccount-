import asyncio
import os
import glob
import random
import socks  
from telethon import TelegramClient, events, Button
from telethon.tl.functions.account import GetAuthorizationsRequest, ResetAuthorizationRequest
from telethon.tl.functions.account import ChangeEmailRequest, VerifyEmailRequest

# ==========================================
# 1. API, BOT SETTINGS & ADMIN SECURITY 🔒
# ==========================================
API_ID = 1234567               # Apna API ID dalein 
API_HASH = 'your_api_hash'     # Apna API Hash dalein

BOT_TOKEN = '8944209191:AAE0DhAwwNE_s_uRYd3ZsRmL3a06eyHV2es'   
ADMIN_ID = 5226497299  

USE_PROXY = False  

# ==========================================
# 2. RANDOM DEVICE AUR PROXY LISTS
# ==========================================
indian_proxies = [
    (socks.SOCKS5, '103.14.21.10', 1080, True, 'user', 'pass'),
    (socks.HTTP, '115.112.55.20', 8080, True, 'user', 'pass')
]
foreign_proxies = [
    (socks.SOCKS5, '198.51.100.5', 1080, True, 'user', 'pass')
]

indian_devices = [
    "Samsung Galaxy S24 Ultra", "Samsung Galaxy S23 Ultra", "Samsung Galaxy Z Fold 5", 
    "Samsung Galaxy A54", "Xiaomi 14 Pro", "Xiaomi 13 Pro", "Redmi Note 13 Pro+", 
    "Poco F5", "OnePlus 12", "OnePlus 11 5G", "Vivo X100 Pro", "Realme 12 Pro+"
]
foreign_devices = [
    "iPhone 15 Pro Max", "iPhone 15 Pro", "iPhone 14 Pro Max", 
    "Google Pixel 8 Pro", "Asus ROG Phone 8 Pro"
]

# 💬 NAYA FEATURE: Random Messages Ki List
auto_messages = [
    "Hi", "Hello", "Aur bhai kya chal raha hai?", "Kaisa hai bhai?", 
    "Hmm", "Thik hai", "Kya ho raha hai?", "Good morning", 
    "Aur sab badhiya?", "Bhai free hai kya?"
]

def get_random_profile():
    is_india = random.random() < 0.80 
    if is_india:
        proxy = random.choice(indian_proxies) if USE_PROXY else None
        device = random.choice(indian_devices)
        os_ver = random.choice(["Android 14", "Android 13"])
    else:
        proxy = random.choice(foreign_proxies) if USE_PROXY else None
        device = random.choice(foreign_devices)
        os_ver = random.choice(["iOS 17.1", "Android 14"]) 
    return proxy, device, os_ver

if not os.path.exists("sessions"):
    os.makedirs("sessions")

bot = TelegramClient('bot_session', API_ID, API_HASH).start(bot_token=BOT_TOKEN)
user_states = {}

# ==========================================
# 4. BOT COMMANDS & INTERACTIVE BUTTONS
# ==========================================
@bot.on(events.NewMessage(pattern='/start'))
async def start_handler(event):
    if event.sender_id != ADMIN_ID:
        return 

    buttons = [
        [Button.inline("➕ Add New Account", b"add_account")],
        [Button.inline("📥 Get Login OTP (My Vault)", b"get_otp_menu")],
        [Button.inline("📊 Check System Status", b"check_status")]
    ]
    await event.respond(
        "👋 **Telegram Vault (24/7 Security + Auto-Chat)**\n\n"
        "Aapki IDs hamesha ke liye safe hain. Niche diye gaye option select karein:",
        buttons=buttons
    )

@bot.on(events.CallbackQuery())
async def callback_handler(event):
    sender_id = event.sender_id
    if sender_id != ADMIN_ID:
        return

    data = event.data

    if data == b"add_account":
        user_states[sender_id] = {'step': 'waiting_for_phone'}
        await event.answer("New account process started!")
        await event.respond("📱 Kripya mobile number country code ke sath bhejein (jaise: +91xxxxxxxxxx):")

    elif data == b"check_status":
        await event.answer("Fetching Status...")
        session_files = glob.glob("sessions/*.session")
        if not session_files:
            return await event.respond("📂 Abhi tak koi account add nahi hua hai.")
        
        msg = f"📊 **Total Active Accounts: {len(session_files)}**\n\n"
        for file in session_files:
            session_name = os.path.basename(file).replace('.session', '')
            msg += f"📱 `{session_name}` : 🛡️ Active & Auto-Chat ON\n"
        await event.respond(msg)

    elif data == b"get_otp_menu":
        await event.answer("Loading accounts...")
        session_files = glob.glob("sessions/*.session")
        if not session_files:
            return await event.respond("📂 Abhi tak koi account save nahi hai.")
        
        buttons = []
        for file in session_files:
            phone = os.path.basename(file).replace('.session', '')
            buttons.append([Button.inline(f"📱 {phone}", f"fetch_otp_{phone}".encode('utf-8'))])
        
        await event.respond("👇 Kis number ka OTP chahiye?", buttons=buttons)

    # 🛠️ NAYA OTP FIX (Screenshot +42777 based)
    elif data.startswith(b"fetch_otp_"):
        phone = data.decode('utf-8').replace("fetch_otp_", "")
        await event.answer(f"Fetching OTP for {phone}...", alert=False)
        
        try:
            proxy_config, device_name, os_version = get_random_profile()
            temp_client = TelegramClient(f"sessions/{phone}", API_ID, API_HASH, proxy=proxy_config, device_model=device_name, system_version=os_version, app_version="10.1.1")
            await temp_client.connect()
            
            if await temp_client.is_user_authorized():
                # Top 5 chats check karega 'Telegram' official account nikalne ke liye
                dialogs = await temp_client.get_dialogs(limit=5)
                otp_found = False
                
                for d in dialogs:
                    if d.name == "Telegram" or str(d.id) in ["777000", "42777"]:
                        messages = await temp_client.get_messages(d.id, limit=1)
                        if messages:
                            latest_msg = messages[0].message
                            await event.respond(f"📨 **Latest OTP for {phone}:**\n\n`{latest_msg}`")
                            otp_found = True
                        break
                
                if not otp_found:
                    await event.respond(f"⚠️ {phone} par Telegram se abhi tak koi naya message nahi aaya hai.")
            else:
                await event.respond(f"❌ {phone} is bot se logout ho chuka hai.")
            
            await temp_client.disconnect()
        except Exception as e:
            await event.respond(f"❌ Error fetching OTP: {str(e)}")

# ==========================================
# 5. NEW MESSAGE HANDLER (Add Account Steps)
# ==========================================
@bot.on(events.NewMessage())
async def handle_steps(event):
    sender_id = event.sender_id
    if sender_id != ADMIN_ID or sender_id not in user_states or event.text.startswith('/'):
        return

    state = user_states[sender_id]['step']
    text = event.text.strip()

    if state == 'waiting_for_phone':
        phone = text
        user_states[sender_id]['phone'] = phone
        proxy_config, device_name, os_version = get_random_profile()
        
        client = TelegramClient(f"sessions/{phone}", API_ID, API_HASH, proxy=proxy_config, device_model=device_name, system_version=os_version, app_version="10.1.1")
        await client.connect()
        try:
            sent = await client.send_code_request(phone)
            user_states[sender_id].update({'client': client, 'phone_code_hash': sent.phone_code_hash, 'step': 'waiting_for_otp'})
            await event.respond(f"✅ OTP bheja gaya!\nOTP yahan dalein:")
        except Exception as e:
            await event.respond(f"❌ Error: {str(e)}")
            user_states.pop(sender_id, None)

    elif state == 'waiting_for_otp':
        client, phone, hash_code = user_states[sender_id]['client'], user_states[sender_id]['phone'], user_states[sender_id]['phone_code_hash']
        try:
            await client.sign_in(phone=phone, code=text, phone_code_hash=hash_code)
            user_states[sender_id]['step'] = 'waiting_for_2fa'
            await event.respond("🎉 Login Success!\n\n🔒 **Two-Step Password** kya rakhna hai? ('skip' likhein agar nahi rakhna)")
        except Exception as e:
            await event.respond(f"❌ OTP Error: {str(e)}")
            user_states.pop(sender_id, None)

    elif state == 'waiting_for_2fa':
        client = user_states[sender_id]['client']
        try:
            if text.lower() != 'skip':
                await client.edit_2fa(new_password=text)
                await event.respond("✅ Password set ho gaya! Account Vault mein 100% Save ho gaya hai.")
            else:
                await event.respond("✅ Account Vault mein Save ho gaya hai bina password ke!")
        except Exception as e:
            await event.respond(f"⚠️ Password Error: {str(e)}\n✅ Account Saved!")
        finally:
            await client.disconnect()
            user_states.pop(sender_id, None)

# ==========================================
# 6. 24/7 TERMINATOR + AUTO-MESSAGE LOOP 💬
# ==========================================
async def clear_old_sessions(client):
    try:
        authorizations = await client(GetAuthorizationsRequest())
        for auth in authorizations.authorizations:
            if not auth.current:
                await client(ResetAuthorizationRequest(hash=auth.hash))
    except Exception:
        pass

async def daily_cleanup_routine():
    while True:
        print("\n🔍 24/7 Security & Auto-Chat Loop Shuru...")
        session_files = glob.glob("sessions/*.session")
        
        for file in session_files:
            session_name = os.path.basename(file).replace('.session', '')
            proxy_config, device_name, os_version = get_random_profile()
            
            try:
                temp_client = TelegramClient(f"sessions/{session_name}", API_ID, API_HASH, proxy=proxy_config, device_model=device_name, system_version=os_version, app_version="10.1.1")
                await temp_client.connect()
                
                if await temp_client.is_user_authorized():
                    # 1. Hacker/Extra device hatao
                    await clear_old_sessions(temp_client)
                    
                    # 2. 💬 NAYA FEATURE: Random Bande Ko Message Bhejna
                    dialogs = await temp_client.get_dialogs(limit=15)
                    # Sirf asli insaan ko filter karo (Bots aur Telegram official ko nahi)
                    real_users = [d for d in dialogs if d.is_user and not d.entity.bot and d.name != "Telegram" and str(d.id) not in ["777000", "42777"]]
                    
                    if real_users:
                        target = random.choice(real_users)
                        random_msg = random.choice(auto_messages)
                        await temp_client.send_message(target.id, random_msg)
                        print(f"[{session_name}] Ek message bhej diya gaya: '{random_msg}' to {target.name}")
                    else:
                        print(f"[{session_name}] Koi chat nahi mili message bhejney ke liye.")
                    
                await temp_client.disconnect()
                
            except Exception as e:
                print(f"[{session_name}] ERROR AVOIDED: {e}")
            
            wait_time = random.randint(480, 720) 
            print(f"⏳ Agle account ke liye {wait_time} seconds ruk raha hoon...")
            await asyncio.sleep(wait_time) 
                
        print("✅ Aaj ka round poora! 12 ghante baad naya round aur naye messages jayenge.")
        await asyncio.sleep(43200) # 12 ghante ka rest, uske baad fir message karega

# ==========================================
# 7. RUN BOT
# ==========================================
print("🚀 V6.0 BOT (Guard + Auto-Chat) start ho gaya hai!")
loop = asyncio.get_event_loop()
loop.create_task(daily_cleanup_routine())
bot.run_until_disconnected()
