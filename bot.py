import telebot
import sqlite3
import threading
import time
import asyncio
import datetime
import json
import os
from pyrogram import Client
from pyrogram.enums import ChatMemberStatus
from pyrogram.errors import FloodWait, SessionPasswordNeeded
from pyrogram.raw.types import UpdateGroupCallParticipants

# ==========================================
# ⚙️ CONFIGURATION & ADMIN SETUP
# ==========================================
MASTER_TOKEN = '8944209191:AAHFqTScbBY7p9kXmivnrdDiLHt-l22Cgew'
MASTER_ADMIN_ID = 5226497299
CONTACT_USERNAME = "TEAM_101_HELP"
API_ID = 31776585
API_HASH = "38ef078842d8db1752b87ca4deabab9d"

# ==========================================
# 🛠️ PERMANENT BACKGROUND ENGINE (PYROGRAM)
# ==========================================
_pyrogram_loop = asyncio.new_event_loop()

def start_pyrogram_loop(loop):
    asyncio.set_event_loop(loop)
    loop.run_forever()

threading.Thread(target=start_pyrogram_loop, args=(_pyrogram_loop,), daemon=True).start()

def run_async(coro):
    future = asyncio.run_coroutine_threadsafe(coro, _pyrogram_loop)
    return future.result()

# ==========================================
# 🛠️ DATABASE SETUP (UNIFIED + SAAS)
# ==========================================
def init_db():
    conn = sqlite3.connect('bot_database.db', check_same_thread=False)
    cursor = conn.cursor()

    cursor.execute('''CREATE TABLE IF NOT EXISTS owners (
                        owner_id INTEGER PRIMARY KEY,
                        channel_id INTEGER,
                        channel_name TEXT,
                        auto_approve BOOLEAN DEFAULT 0,
                        msg_1 INTEGER,
                        msg_2 INTEGER,
                        msg_3 INTEGER,
                        delay INTEGER DEFAULT 0,
                        uc_expiry INTEGER DEFAULT 0,
                        rp_expiry INTEGER DEFAULT 0,
                        reminder_sent INTEGER DEFAULT 0,
                        reject_premium BOOLEAN DEFAULT 0
                    )''')
    try:
        cursor.execute("ALTER TABLE owners ADD COLUMN uc_expiry INTEGER DEFAULT 0")
        cursor.execute("ALTER TABLE owners ADD COLUMN rp_expiry INTEGER DEFAULT 0")
        cursor.execute("ALTER TABLE owners ADD COLUMN reminder_sent INTEGER DEFAULT 0")
        cursor.execute("ALTER TABLE owners ADD COLUMN reject_premium BOOLEAN DEFAULT 0")
        cursor.execute("ALTER TABLE owners ADD COLUMN btn_1 TEXT")
        cursor.execute("ALTER TABLE owners ADD COLUMN btn_2 TEXT")
        cursor.execute("ALTER TABLE owners ADD COLUMN btn_3 TEXT")
    except: pass

    cursor.execute('''CREATE TABLE IF NOT EXISTS global_users (user_id INTEGER PRIMARY KEY)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS vip_users (user_id INTEGER PRIMARY KEY)''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS premium_customers (
                        owner_id INTEGER PRIMARY KEY,
                        phone_number TEXT,
                        channel_uid INTEGER,
                        session_string TEXT,
                        expiry_date INTEGER
                    )''')
    try:
        cursor.execute("ALTER TABLE premium_customers ADD COLUMN session_string TEXT")
    except: pass

    cursor.execute('''CREATE TABLE IF NOT EXISTS clone_bots (
                        bot_token TEXT PRIMARY KEY,
                        owner_id INTEGER,
                        expiry_date INTEGER,
                        features TEXT
                    )''')
    try:
        cursor.execute("ALTER TABLE clone_bots ADD COLUMN features TEXT")
    except: pass

    conn.commit()
    conn.close()

init_db()

def get_db_connection():
    return sqlite3.connect('bot_database.db', check_same_thread=False)

# ==========================================
# 🤖 BOT FACTORY (SaaS Architecture)
# ==========================================
active_bots = {}

def run_bot_instance(bot_token, IS_MASTER=False):
    bot = telebot.TeleBot(bot_token)
    bot_id = bot_token.split(":")[0] 

    admin_target_users = {}
    setup_states = {}
    user_locked_msgs = {}
    premium_setup_states = {}
    admin_editing_bot = {}

    def is_bot_expired():
        if IS_MASTER: return False
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT expiry_date FROM clone_bots WHERE bot_token=?", (bot_token,))
        row = c.fetchone()
        conn.close()
        if row and time.time() > row[0]: return True
        return False

    def verify_feature(user_id, feature_key):
        if IS_MASTER: return True 
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT owner_id, expiry_date, features FROM clone_bots WHERE bot_token=?", (bot_token,))
        row = c.fetchone()
        conn.close()
        if not row: return False
        owner, exp, feats_json = row
        if user_id != owner: return False 
        if time.time() > exp: return "EXPIRED"
        try:
            feats = json.loads(feats_json) if feats_json else {}
            return feats.get(feature_key, False)
        except: return False

    def get_main_menu(user_id):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT auto_approve, delay, channel_name, reject_premium FROM owners WHERE owner_id = ?", (user_id,))
        owner_data = cursor.fetchone()
        markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)

        if not owner_data and user_id != MASTER_ADMIN_ID:
            markup.row("🔄 Check Status")
            conn.close()
            return markup

        auto_status = "ON 🟢" if owner_data and owner_data[0] else "OFF 🔴"
        delay = owner_data[1] if owner_data else 0
        reject_status = "ON 🟢" if owner_data and owner_data[3] else "OFF 🔴"

        if IS_MASTER:
            if user_id == MASTER_ADMIN_ID:
                markup.row("👑 Advance Premium Panel", "🤖 Multiple Bot")
                markup.row("👥 Users Check", "📢 Broadcast")
            elif owner_data:
                markup.row("👥 Users Check")

        if owner_data or (IS_MASTER and user_id == MASTER_ADMIN_ID):
            markup.row("🧹 Channel Premium Remove") 
            markup.row(f"🚫 Reject Premium: {reject_status}")
            markup.row(f"⚙️ Auto-Approve: {auto_status}")
            markup.row("1️⃣ Setup Msg 1", "2️⃣ Setup Msg 2", "3️⃣ Setup Msg 3")
            markup.row(f"⏱️ Setup Delay: {delay} sec")

        conn.close()
        return markup

    def check_access(user_id, feature_column):
        if is_bot_expired(): return False 
        if IS_MASTER and user_id == MASTER_ADMIN_ID: return True
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(f"SELECT {feature_column} FROM owners WHERE owner_id = ?", (user_id,))
        data = cursor.fetchone()
        conn.close()
        if data and data[0] and time.time() < data[0]: return True
        return False

    def check_pr_access(user_id):
        if is_bot_expired(): return False 
        if IS_MASTER and user_id == MASTER_ADMIN_ID: return True
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT expiry_date FROM premium_customers WHERE owner_id = ?", (user_id,))
        data = cursor.fetchone()
        conn.close()
        if data and data[0] and time.time() < data[0]: return True
        return False

    def send_premium_warning(message, feature_name):
        msg = f"⚠️ Yeh '{feature_name}' ek Premium Feature hai!\n\nContact Admin: @{CONTACT_USERNAME}"
        bot.reply_to(message, msg)

    # ==========================================
    # 🤖 MULTIPLE BOT MENU & FEATURE TOGGLE
    # ==========================================
    if IS_MASTER:
        @bot.message_handler(func=lambda m: m.text == "🤖 Multiple Bot" and m.from_user.id == MASTER_ADMIN_ID)
        def multi_bot_menu(message):
            markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
            markup.row("➕ Add Bot", "⏳ Expiry Bot Time")
            markup.row("⚙️ Premium Feature Check")
            markup.row("🔙 Back to Main Menu")
            bot.send_message(message.chat.id, "🤖 **SaaS Multiple Bot Manager:**", reply_markup=markup, parse_mode="Markdown")

        @bot.message_handler(func=lambda m: m.text == "➕ Add Bot" and m.from_user.id == MASTER_ADMIN_ID)
        def add_bot_step1(message):
            msg = bot.reply_to(message, "🤖 Naye bot ka Token bhejo (Cancel ke liye 'cancel'):", reply_markup=telebot.types.ReplyKeyboardRemove())
            bot.register_next_step_handler(msg, add_bot_step2)

        def add_bot_step2(message):
            if message.text.lower() == 'cancel': return bot.send_message(message.chat.id, "❌ Cancelled.", reply_markup=get_main_menu(message.from_user.id))
            token = message.text.strip()
            msg = bot.reply_to(message, "👤 Is clone bot ke Owner ki Telegram UID bhejo:")
            bot.register_next_step_handler(msg, lambda m: add_bot_step3(m, token))

        def add_bot_step3(message, token):
            try:
                owner_uid = int(message.text.strip())
                exp = int(time.time()) + (30 * 24 * 3600)
                feats = {"auto_approve": False, "welcome_msg": False, "reject_premium": False, "channel_cleaner": False}
                
                conn = get_db_connection()
                c = conn.cursor()
                c.execute("INSERT OR REPLACE INTO clone_bots (bot_token, owner_id, expiry_date, features) VALUES (?, ?, ?, ?)", (token, owner_uid, exp, json.dumps(feats)))
                conn.commit()
                conn.close()

                clone_bot = run_bot_instance(token, IS_MASTER=False)
                active_bots[token] = clone_bot
                threading.Thread(target=lambda: poll_bot(clone_bot), daemon=True).start()
                
                bot.send_message(message.chat.id, "✅ **Bot Added & Started for 30 Days!**", parse_mode="Markdown")
                admin_editing_bot[message.chat.id] = token
                send_feature_panel(message.chat.id, token)
            except Exception as e:
                bot.reply_to(message, f"❌ Error: {e}", reply_markup=get_main_menu(message.from_user.id))

        @bot.message_handler(func=lambda m: m.text == "⏳ Expiry Bot Time" and m.from_user.id == MASTER_ADMIN_ID)
        def check_exp_1(message):
            msg = bot.reply_to(message, "🤖 Bot ka Token bhejo:", reply_markup=telebot.types.ReplyKeyboardRemove())
            bot.register_next_step_handler(msg, check_exp_2)
            
        def check_exp_2(message):
            if message.text.lower() == 'cancel': return bot.send_message(message.chat.id, "❌ Cancelled.", reply_markup=get_main_menu(message.from_user.id))
            token = message.text.strip()
            conn = get_db_connection()
            c = conn.cursor()
            c.execute("SELECT expiry_date, owner_id FROM clone_bots WHERE bot_token=?", (token,))
            row = c.fetchone()
            conn.close()
            if row:
                rem = int((row[0] - time.time()) / 86400)
                bot.reply_to(message, f"✅ **Bot Details:**\nOwner UID: `{row[1]}`\nDays Left: `{max(0, rem)}` Days", parse_mode="Markdown", reply_markup=get_main_menu(message.from_user.id))
            else:
                bot.reply_to(message, "❌ Bot database mein nahi mila.", reply_markup=get_main_menu(message.from_user.id))

        @bot.message_handler(func=lambda m: m.text == "⚙️ Premium Feature Check" and m.from_user.id == MASTER_ADMIN_ID)
        def check_feats_step1(message):
            msg = bot.reply_to(message, "🤖 Bot ka Token bhejo (Cancel ke liye 'cancel'):", reply_markup=telebot.types.ReplyKeyboardRemove())
            bot.register_next_step_handler(msg, check_feats_step2)
            
        def check_feats_step2(message):
            if message.text.lower() == 'cancel': return bot.send_message(message.chat.id, "❌ Cancelled.", reply_markup=get_main_menu(message.from_user.id))
            token = message.text.strip()
            admin_editing_bot[message.chat.id] = token
            send_feature_panel(message.chat.id, token)

        def send_feature_panel(chat_id, token):
            conn = get_db_connection()
            c = conn.cursor()
            c.execute("SELECT features FROM clone_bots WHERE bot_token=?", (token,))
            row = c.fetchone()
            conn.close()
            if not row: return bot.send_message(chat_id, "❌ Bot not found in DB.")
            
            feats = json.loads(row[0]) if row[0] else {"auto_approve": False, "welcome_msg": False, "reject_premium": False, "channel_cleaner": False}

            markup = telebot.types.InlineKeyboardMarkup()
            def btn_text(key, name): return f"{'✅' if feats.get(key) else '❌'} {name}"
            
            markup.add(telebot.types.InlineKeyboardButton(text=btn_text("auto_approve", "Auto-Approve"), callback_data="tf_auto_approve"))
            markup.add(telebot.types.InlineKeyboardButton(text=btn_text("welcome_msg", "Welcome Msg Setup"), callback_data="tf_welcome_msg"))
            markup.add(telebot.types.InlineKeyboardButton(text=btn_text("reject_premium", "Reject Premium"), callback_data="tf_reject_premium"))
            markup.add(telebot.types.InlineKeyboardButton(text=btn_text("channel_cleaner", "Channel Cleaner (PR)"), callback_data="tf_channel_cleaner"))
            markup.add(telebot.types.InlineKeyboardButton(text="✅ DONE", callback_data="tf_done"))
            
            bot.send_message(chat_id, f"⚙️ **Features for Bot:** `{token.split(':')[0]}...`\nNiche button click karke features ON/OFF karein:", reply_markup=markup, parse_mode="Markdown")

        @bot.callback_query_handler(func=lambda call: call.data.startswith("tf_"))
        def feature_toggle_callback(call):
            chat_id = call.message.chat.id
            token = admin_editing_bot.get(chat_id)
            if not token: return bot.answer_callback_query(call.id, "❌ Session expired.")
            
            action = call.data.replace("tf_", "")
            if action == "done":
                bot.delete_message(chat_id, call.message.message_id)
                bot.send_message(chat_id, "✅ Setup Complete!", reply_markup=get_main_menu(chat_id))
                return
                
            conn = get_db_connection()
            c = conn.cursor()
            c.execute("SELECT features FROM clone_bots WHERE bot_token=?", (token,))
            row = c.fetchone()
            if row:
                feats = json.loads(row[0]) if row[0] else {}
                feats[action] = not feats.get(action, False)
                c.execute("UPDATE clone_bots SET features=? WHERE bot_token=?", (json.dumps(feats), token))
                conn.commit()
                conn.close()
                
                markup = telebot.types.InlineKeyboardMarkup()
                def btn_text(key, name): return f"{'✅' if feats.get(key) else '❌'} {name}"
                markup.add(telebot.types.InlineKeyboardButton(text=btn_text("auto_approve", "Auto-Approve"), callback_data="tf_auto_approve"))
                markup.add(telebot.types.InlineKeyboardButton(text=btn_text("welcome_msg", "Welcome Msg Setup"), callback_data="tf_welcome_msg"))
                markup.add(telebot.types.InlineKeyboardButton(text=btn_text("reject_premium", "Reject Premium"), callback_data="tf_reject_premium"))
                markup.add(telebot.types.InlineKeyboardButton(text=btn_text("channel_cleaner", "Channel Cleaner (PR)"), callback_data="tf_channel_cleaner"))
                markup.add(telebot.types.InlineKeyboardButton(text="✅ DONE", callback_data="tf_done"))
                bot.edit_message_reply_markup(chat_id=chat_id, message_id=call.message.message_id, reply_markup=markup)
            else:
                conn.close()

    # ==========================================
    # 👑 ADMIN PANEL & TOGGLES (ORIGINAL)
    # ==========================================
    if IS_MASTER:
        @bot.message_handler(func=lambda message: message.text == "👑 Advance Premium Panel" and message.from_user.id == MASTER_ADMIN_ID)
        def advance_panel_prompt(message):
            msg = bot.reply_to(message, "👑 **Advance Premium Panel**\n\nUser ki Telegram User ID bhejo:")
            bot.register_next_step_handler(msg, get_target_user_id)

        def get_target_user_id(message):
            if message.text and message.text.lower() == 'cancel':
                bot.send_message(message.chat.id, "❌ Cancelled.", reply_markup=get_main_menu(message.from_user.id))
                return
            try:
                target_id = int(message.text.strip())
                admin_target_users[message.from_user.id] = target_id
                conn = get_db_connection()
                cursor = conn.cursor()

                cursor.execute("SELECT uc_expiry, rp_expiry FROM owners WHERE owner_id = ?", (target_id,))
                data = cursor.fetchone()
                cursor.execute("SELECT user_id FROM vip_users WHERE user_id = ?", (target_id,))
                vip_data = cursor.fetchone()
                cursor.execute("SELECT expiry_date FROM premium_customers WHERE owner_id = ?", (target_id,))
                pr_data = cursor.fetchone()

                conn.close()
                now = time.time()

                uc_active = "ON 🟢" if (data and data[0] and now < data[0]) else "OFF 🔴"
                rp_active = "ON 🟢" if (data and data[1] and now < data[1]) else "OFF 🔴"
                vip_active = "ON 🌟" if vip_data else "OFF ⚪"
                pr_active = "ON 🟢" if (pr_data and pr_data[0] and now < pr_data[0]) else "OFF 🔴"

                markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
                markup.row(f"🔑 Toggle Channel PR [{pr_active}]")  
                markup.row(f"🔑 Toggle Users Check [{uc_active}]")
                markup.row(f"🔑 Toggle Reject Premium [{rp_active}]")
                markup.row(f"🌟 Toggle VIP (Anti-Reject/Kick) [{vip_active}]")
                markup.row("🔙 Back to Main Menu")
                bot.send_message(message.chat.id, f"⚙️ User ID: `{target_id}` options:", reply_markup=markup, parse_mode="Markdown")
            except:
                msg = bot.reply_to(message, "❌ Sahi ID bhejo:")
                bot.register_next_step_handler(msg, get_target_user_id)

        @bot.message_handler(func=lambda message: "Toggle Channel PR" in message.text and message.from_user.id == MASTER_ADMIN_ID)
        def toggle_pr_feature(message):
            admin_id = message.from_user.id
            target_id = admin_target_users.get(admin_id)
            if not target_id: return
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT expiry_date FROM premium_customers WHERE owner_id = ?", (target_id,))
            data = cursor.fetchone()
            now = int(time.time())
            if data and data[0] and now < data[0]:
                cursor.execute("UPDATE premium_customers SET expiry_date = 0 WHERE owner_id = ?", (target_id,))
                status = "OFF 🔴"
            else:
                expiry = now + 2592000 
                if not data: cursor.execute("INSERT INTO premium_customers (owner_id, expiry_date) VALUES (?, ?)", (target_id, expiry))
                else: cursor.execute("UPDATE premium_customers SET expiry_date = ? WHERE owner_id = ?", (expiry, target_id))
                status = "ON 🟢"
            conn.commit()
            conn.close()
            bot.send_message(message.chat.id, f"✅ Channel Premium Remove: {status}", reply_markup=get_main_menu(admin_id))

        @bot.message_handler(func=lambda message: "Toggle VIP" in message.text and message.from_user.id == MASTER_ADMIN_ID)
        def toggle_vip_feature(message):
            admin_id = message.from_user.id
            if admin_id not in admin_target_users: return
            target_id = admin_target_users[admin_id]
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT user_id FROM vip_users WHERE user_id = ?", (target_id,))
            if cursor.fetchone():
                cursor.execute("DELETE FROM vip_users WHERE user_id = ?", (target_id,))
                status = "OFF ⚪"
            else:
                cursor.execute("INSERT INTO vip_users (user_id) VALUES (?)", (target_id,))
                status = "ON 🌟"
            conn.commit()
            conn.close()
            bot.send_message(message.chat.id, f"✅ VIP status: {status}", reply_markup=get_main_menu(admin_id))

        @bot.message_handler(func=lambda message: "Toggle Users Check" in message.text and message.from_user.id == MASTER_ADMIN_ID)
        def toggle_uc_feature(message):
            admin_id = message.from_user.id
            target_id = admin_target_users.get(admin_id)
            if not target_id: return
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT uc_expiry FROM owners WHERE owner_id = ?", (target_id,))
            data = cursor.fetchone()
            now = time.time()
            if data and data[0] and now < data[0]:
                cursor.execute("UPDATE owners SET uc_expiry = 0 WHERE owner_id = ?", (target_id,))
                status = "OFF 🔴"
            else:
                expiry = int(now) + 2592000
                if not data: cursor.execute("INSERT INTO owners (owner_id, uc_expiry, reminder_sent) VALUES (?, ?, 0)", (target_id, expiry))
                else: cursor.execute("UPDATE owners SET uc_expiry = ?, reminder_sent = 0 WHERE owner_id = ?", (expiry, target_id))
                status = "ON 🟢"
            conn.commit()
            conn.close()
            bot.send_message(message.chat.id, f"✅ Users Check: {status}", reply_markup=get_main_menu(admin_id))

        @bot.message_handler(func=lambda message: "Toggle Reject Premium" in message.text and message.from_user.id == MASTER_ADMIN_ID)
        def toggle_rp_feature(message):
            admin_id = message.from_user.id
            target_id = admin_target_users.get(admin_id)
            if not target_id: return
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT rp_expiry FROM owners WHERE owner_id = ?", (target_id,))
            data = cursor.fetchone()
            now = time.time()
            if data and data[0] and now < data[0]:
                cursor.execute("UPDATE owners SET rp_expiry = 0 WHERE owner_id = ?", (target_id,))
                status = "OFF 🔴"
            else:
                expiry = int(now) + 2592000
                if not data: cursor.execute("INSERT INTO owners (owner_id, rp_expiry, reminder_sent) VALUES (?, ?, 0)", (target_id, expiry))
                else: cursor.execute("UPDATE owners SET rp_expiry = ?, reminder_sent = 0 WHERE owner_id = ?", (expiry, target_id))
                status = "ON 🟢"
            conn.commit()
            conn.close()
            bot.send_message(message.chat.id, f"✅ Reject Premium: {status}", reply_markup=get_main_menu(admin_id))

        @bot.message_handler(func=lambda message: message.text == "🔙 Back to Main Menu" and message.from_user.id == MASTER_ADMIN_ID)
        def back_to_main(message):
            if message.from_user.id in admin_target_users: del admin_target_users[message.from_user.id]
            bot.send_message(message.chat.id, "🏠 Main Menu", reply_markup=get_main_menu(message.from_user.id))

    # ==========================================
    # 🚀 LAYER 2 INSTANT KICKER (PERMANENT BAN)
    # ==========================================
    @bot.chat_member_handler()
    def instant_join_kicker(update):
        if update.new_chat_member.status == 'member' and update.old_chat_member.status != 'member':
            user = update.new_chat_member.user
            channel_id = update.chat.id
            if user.is_bot: return
            
            if getattr(user, 'is_premium', False):
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT reject_premium FROM owners WHERE channel_id = ?", (channel_id,))
                owner_data = cursor.fetchone()
                cursor.execute("SELECT * FROM vip_users WHERE user_id = ?", (user.id,))
                is_vip = cursor.fetchone()
                conn.close()
                
                if owner_data and owner_data[0] and not is_vip:
                    try:
                        bot.ban_chat_member(channel_id, user.id)
                    except: pass

    # ==========================================
    # 🚀 CORE HANDLERS (JOIN, MESSAGES, SETTINGS)
    # ==========================================
    @bot.my_chat_member_handler()
    def handle_my_chat_member(update):
        new_status = update.new_chat_member.status
        if new_status in ['administrator', 'creator']:
            owner_id = update.from_user.id
            channel_id = update.chat.id
            channel_name = update.chat.title
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM owners WHERE owner_id = ?", (owner_id,))
            if cursor.fetchone():
                cursor.execute("UPDATE owners SET channel_id = ?, channel_name = ? WHERE owner_id = ?", (channel_id, channel_name, owner_id))
            else:
                cursor.execute("INSERT INTO owners (owner_id, channel_id, channel_name) VALUES (?, ?, ?)", (owner_id, channel_id, channel_name))
            conn.commit()
            conn.close()
            try: bot.send_message(owner_id, f"✅ Bot {channel_name} mein admin ban gaya hai!", reply_markup=get_main_menu(owner_id))
            except: pass

    @bot.message_handler(commands=['start'])
    def send_welcome(message):
        user_id = message.from_user.id
        text_parts = message.text.split()
        if len(text_parts) > 1 and text_parts[1].startswith("unlock_"):
            try:
                owner_id = int(text_parts[1].split("_")[1])
                if user_id in user_locked_msgs and user_locked_msgs[user_id].get('owner_id') == owner_id:
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    cursor.execute("SELECT btn_1, btn_2, btn_3 FROM owners WHERE owner_id = ?", (owner_id,))
                    btns_data = cursor.fetchone()
                    conn.close()
                    if btns_data:
                        for m_idx in [1, 2, 3]:
                            if m_idx in user_locked_msgs[user_id]:
                                msg_id_to_edit = user_locked_msgs[user_id][m_idx]
                                btn_json = btns_data[m_idx - 1]
                                if btn_json:
                                    try:
                                        btns = json.loads(btn_json)
                                        markup = telebot.types.InlineKeyboardMarkup()
                                        for b in btns:
                                            markup.add(telebot.types.InlineKeyboardButton(text=b['name'], url=b['url']))
                                        bot.edit_message_reply_markup(chat_id=user_id, message_id=msg_id_to_edit, reply_markup=markup)
                                    except: pass
                    return
            except: pass

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT channel_name FROM owners WHERE owner_id = ?", (user_id,))
        owner_data = cursor.fetchone()
        conn.close()
        
        if user_id == MASTER_ADMIN_ID or owner_data or (not IS_MASTER and not is_bot_expired()):
            bot.send_message(message.chat.id, f"Control Panel:\nChannel: {owner_data[0] if owner_data else 'None'}", reply_markup=get_main_menu(user_id))
        else:
            bot.send_message(message.chat.id, "⚠️ **Pehle bot ko apne channel mein admin banao!**", parse_mode="Markdown")

    def delayed_welcome(user_id, owner_id):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT msg_1, msg_2, msg_3, delay, btn_1, btn_2, btn_3 FROM owners WHERE owner_id = ?", (owner_id,))
        data = cursor.fetchone()
        conn.close()
        if not data: return
        msg_1, msg_2, msg_3, delay, btn_1, btn_2, btn_3 = data
        bot_info = bot.get_me()
        user_locked_msgs[user_id] = {'owner_id': owner_id}

        def send_msg_with_locked_btns(msg_id, btn_json, m_idx):
            if not msg_id: return
            markup = telebot.types.InlineKeyboardMarkup()
            if btn_json:
                try:
                    btns = json.loads(btn_json)
                    deep_link = f"https://t.me/{bot_info.username}?start=unlock_{owner_id}"
                    for b in btns:
                        markup.add(telebot.types.InlineKeyboardButton(text=f"🔒 {b['name']}", url=deep_link))
                except: pass
            try:
                res = bot.copy_message(chat_id=user_id, from_chat_id=owner_id, message_id=msg_id, reply_markup=markup)
                user_locked_msgs[user_id][m_idx] = res.message_id
            except: pass

        if msg_1:
            send_msg_with_locked_btns(msg_1, btn_1, 1)
            if msg_2:
                if delay > 0: time.sleep(delay)
                send_msg_with_locked_btns(msg_2, btn_2, 2)
            if msg_3:
                if delay > 0: time.sleep(delay)
                send_msg_with_locked_btns(msg_3, btn_3, 3)

    @bot.chat_join_request_handler()
    def handle_join_request(request):
        channel_id = request.chat.id
        user = request.from_user
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO global_users (user_id) VALUES (?)", (user.id,))
        conn.commit()
        cursor.execute("SELECT owner_id, auto_approve, reject_premium, msg_1, msg_2, msg_3 FROM owners WHERE channel_id = ?", (channel_id,))
        owner_data = cursor.fetchone()
        if owner_data:
            owner_id, auto_approve, reject_premium, msg_1, msg_2, msg_3 = owner_data
            if reject_premium and getattr(user, 'is_premium', False) and (msg_1 or msg_2 or msg_3):
                cursor.execute("SELECT * FROM vip_users WHERE user_id = ?", (user.id,))
                if not cursor.fetchone():
                    try: bot.decline_chat_join_request(channel_id, user.id)
                    except: pass
                    conn.close()
                    return
            conn.close()
            try: threading.Thread(target=delayed_welcome, args=(user.id, owner_id)).start()
            except: pass
            if auto_approve:
                try: bot.approve_chat_join_request(channel_id, user.id)
                except: pass
        else:
            conn.close()

    def update_owner_setting(owner_id, column, value):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(f"UPDATE owners SET {column} = ? WHERE owner_id = ?", (value, owner_id))
        conn.commit()
        conn.close()

    @bot.message_handler(func=lambda message: message.text in ["1️⃣ Setup Msg 1", "2️⃣ Setup Msg 2", "3️⃣ Setup Msg 3"])
    def setup_msg(message):
        if not IS_MASTER:
            status = verify_feature(message.from_user.id, "welcome_msg")
            if not status or status == "EXPIRED": return send_premium_warning(message, "Setup Msg")
            
        col = 'msg_1' if "1" in message.text else 'msg_2' if "2" in message.text else 'msg_3'
        name = f"Message {col[-1]}"
        msg = bot.reply_to(message, f"➡️ Apna {name} bhejein:")
        bot.register_next_step_handler(msg, lambda m: save_msg_and_ask_boxes(m, col, name))

    def save_msg_and_ask_boxes(message, column, name):
        update_owner_setting(message.from_user.id, column, message.message_id)
        setup_states[message.from_user.id] = {'column': column, 'name': name, 'btns': [], 'current': 1}
        msg = bot.send_message(message.chat.id, f"📦 Kitne Box (Buttons) lagane hain? (0 se 5):")
        bot.register_next_step_handler(msg, get_box_count)

    def get_box_count(message):
        user_id = message.from_user.id
        try:
            count = int(message.text.strip())
            if count == 0:
                if user_id in setup_states: del setup_states[user_id]
                return bot.send_message(message.chat.id, "✅ Set ho gaya!", reply_markup=get_main_menu(user_id))
            if count > 5 or count < 0: raise ValueError()
            setup_states[user_id]['total'] = count
            msg = bot.send_message(message.chat.id, f"📦 **Box 1** ka Naam likho:", parse_mode="Markdown")
            bot.register_next_step_handler(msg, get_box_name)
        except:
            msg = bot.send_message(message.chat.id, "❌ 0 se 5 ke beech number likhein:")
            bot.register_next_step_handler(msg, get_box_count)

    def get_box_name(message):
        user_id = message.from_user.id
        if user_id not in setup_states:
            return bot.send_message(message.chat.id, "⚠️ Session refresh ho gaya! Dobara shuru karein.", reply_markup=get_main_menu(user_id))
        if not message.text:
            msg = bot.send_message(message.chat.id, "❌ Naam khali nahi ho sakta:")
            return bot.register_next_step_handler(msg, get_box_name)
        setup_states[user_id]['temp_name'] = message.text
        msg = bot.send_message(message.chat.id, f"🔗 **Box {setup_states[user_id]['current']}** ka Link ya Text bhejo (Koi pabandi nahi):", parse_mode="Markdown")
        bot.register_next_step_handler(msg, get_box_link)

    def get_box_link(message):
        user_id = message.from_user.id
        if user_id not in setup_states:
            return bot.send_message(message.chat.id, "⚠️ Session refresh ho gaya! Dobara shuru karein.", reply_markup=get_main_menu(user_id))

        raw_text = message.text or message.caption or ""
        link_text = raw_text.strip().replace("[", "").replace("]", "")
        if not link_text:
            msg = bot.send_message(message.chat.id, "❌ Kuch toh likho:")
            return bot.register_next_step_handler(msg, get_box_link)

        state = setup_states[user_id]
        state['btns'].append({"name": state['temp_name'], "url": link_text})

        if state['current'] < state['total']:
            state['current'] += 1
            msg = bot.send_message(message.chat.id, f"📦 **Box {state['current']}** ka Naam likho:", parse_mode="Markdown")
            bot.register_next_step_handler(msg, get_box_name)
        else:
            btn_col = state['column'].replace('msg_', 'btn_')
            update_owner_setting(user_id, btn_col, json.dumps(state['btns']))
            del setup_states[user_id]
            bot.send_message(message.chat.id, f"✅ **{state['name']}** aur uske boxes set ho gaye!", reply_markup=get_main_menu(user_id), parse_mode="Markdown")

    @bot.message_handler(func=lambda message: "Auto-Approve:" in message.text)
    def toggle_auto_approve(message):
        if not IS_MASTER:
            status = verify_feature(message.from_user.id, "auto_approve")
            if not status or status == "EXPIRED": return send_premium_warning(message, "Auto-Approve")
            
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT auto_approve FROM owners WHERE owner_id = ?", (message.from_user.id,))
        data = cursor.fetchone()
        if data:
            new_val = 0 if data[0] else 1
            cursor.execute("UPDATE owners SET auto_approve = ? WHERE owner_id = ?", (new_val, message.from_user.id))
            conn.commit()
            bot.send_message(message.chat.id, "✅ Auto-Approve update ho gaya!", reply_markup=get_main_menu(message.from_user.id))
        conn.close()

    @bot.message_handler(func=lambda message: "⏱️ Setup Delay" in message.text)
    def setup_delay_prompt(message):
        if not IS_MASTER:
            status = verify_feature(message.from_user.id, "welcome_msg")
            if not status or status == "EXPIRED": return send_premium_warning(message, "Setup Delay")
            
        msg = bot.reply_to(message, "⏱️ Seconds likho:")
        bot.register_next_step_handler(msg, save_delay)

    def save_delay(message):
        try:
            seconds = int(message.text.strip())
            update_owner_setting(message.from_user.id, 'delay', seconds)
            bot.send_message(message.chat.id, f"✅ Delay {seconds} sec set ho gaya!", reply_markup=get_main_menu(message.from_user.id))
        except:
            bot.send_message(message.chat.id, "❌ Sirf number daalna tha.", reply_markup=get_main_menu(message.from_user.id))

    @bot.message_handler(func=lambda message: "Reject Premium:" in message.text)
    def toggle_reject_premium(message):
        if IS_MASTER:
            if not check_access(message.from_user.id, 'rp_expiry'):
                return send_premium_warning(message, "Reject Premium")
        else:
            status = verify_feature(message.from_user.id, "reject_premium")
            if not status or status == "EXPIRED": return send_premium_warning(message, "Reject Premium")
            
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT reject_premium FROM owners WHERE owner_id = ?", (message.from_user.id,))
        data = cursor.fetchone()
        if data:
            new_val = 0 if data[0] else 1
            cursor.execute("UPDATE owners SET reject_premium = ? WHERE owner_id = ?", (new_val, message.from_user.id))
            conn.commit()
            bot.send_message(message.chat.id, "✅ Reject Premium update ho gaya!", reply_markup=get_main_menu(message.from_user.id))
        conn.close()

    @bot.message_handler(func=lambda message: message.text == "👥 Users Check")
    def check_users(message):
        if not IS_MASTER: return 
        if not check_access(message.from_user.id, 'uc_expiry'):
            return send_premium_warning(message, "Users Check")
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM global_users")
        total_users = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM owners")
        total_channels = cursor.fetchone()[0]
        conn.close()
        bot.reply_to(message, f"🔥 **Database:**\nChannels: {total_channels}\nUsers: {total_users}", parse_mode="Markdown")

    @bot.message_handler(func=lambda message: message.text == "📢 Broadcast")
    def broadcast_prompt(message):
        if not IS_MASTER: return 
        markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        markup.row("📢 Broadcast to Owners", "📢 Broadcast to Users")
        markup.row("Cancel")
        bot.reply_to(message, "Kisko broadcast karna hai?", reply_markup=markup)

    @bot.message_handler(func=lambda message: message.text in ["📢 Broadcast to Owners", "📢 Broadcast to Users"])
    def ask_broadcast_msg(message):
        if not IS_MASTER: return 
        target = "owners" if "Owners" in message.text else "users"
        msg = bot.reply_to(message, f"📢 Message bhejo (Cancel ke liye 'cancel'):", reply_markup=telebot.types.ReplyKeyboardRemove())
        bot.register_next_step_handler(msg, lambda m: process_broadcast_live(m, target))

    def process_broadcast_live(message, target):
        if message.text and message.text.lower() == 'cancel':
            return bot.send_message(message.chat.id, "❌ Cancelled.", reply_markup=get_main_menu(message.from_user.id))
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT owner_id FROM owners" if target == "owners" else "SELECT user_id FROM global_users")
        users = cursor.fetchall()
        conn.close()
        status_msg = bot.send_message(message.chat.id, f"⏳ **Broadcasting...** Sent: 0", parse_mode="Markdown")
        success, failed = 0, 0
        for user in users:
            try:
                bot.copy_message(chat_id=user[0], from_chat_id=message.chat.id, message_id=message.message_id)
                success += 1
            except: failed += 1
            if success > 0 and success % 10 == 0:
                try: bot.edit_message_text(f"⏳ **Broadcasting...** Sent: {success}", message.chat.id, status_msg.message_id, parse_mode="Markdown")
                except: pass
        bot.edit_message_text(f"✅ **Done!** Sent: {success}, Failed: {failed}", message.chat.id, status_msg.message_id, parse_mode="Markdown")
        bot.send_message(message.chat.id, "Main Menu:", reply_markup=get_main_menu(message.from_user.id))

    # ==========================================
    # 🚀 PREMIUM SCANNER: CHANNEL PREMIUM REMOVE
    # ==========================================
    @bot.message_handler(func=lambda message: message.text == "🧹 Channel Premium Remove")
    def start_premium_remove(message):
        user_id = message.from_user.id
        if IS_MASTER:
            if not check_pr_access(user_id):
                return send_premium_warning(message, "Channel Premium Remove")
        else:
            status = verify_feature(user_id, "channel_cleaner")
            if not status or status == "EXPIRED": return send_premium_warning(message, "Channel Premium Remove")

        text = (
            "🛡️ **Channel Premium Remove Setup** 🛡️\n\n"
            "Apne channel se anjaan Premium members ko auto-kick karne ke liye apna Telegram number bhejein.\n\n"
            "👉 **Example:** `+919876543210`\n"
            "(Cancel karne ke liye 'Cancel' likhein)"
        )
        markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.row("Cancel")
        msg = bot.send_message(user_id, text, parse_mode="Markdown", reply_markup=markup)
        bot.register_next_step_handler(msg, get_pr_number)

    def get_pr_number(message):
        user_id = message.from_user.id
        text_input = message.text.strip()

        if text_input.lower() in ["cancel", "/start"]:
            if user_id in premium_setup_states: del premium_setup_states[user_id]
            return bot.send_message(user_id, "❌ Setup Cancelled.", reply_markup=get_main_menu(user_id))

        phone = text_input
        status_msg = bot.send_message(user_id, "⏳ Telegram se OTP mangwa raha hoon, kripya wait karein...")

        try:
            async def send_code_async():
                client = Client(f"mem_{user_id}_{bot_id}", api_id=API_ID, api_hash=API_HASH, in_memory=True)
                await client.connect()
                sent_code = await client.send_code(phone)
                return client, sent_code.phone_code_hash

            client, code_hash = run_async(send_code_async())
            premium_setup_states[user_id] = {'phone': phone, 'hash': code_hash, 'client': client}

            bot.delete_message(user_id, status_msg.message_id)
            markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
            markup.row("Cancel")
            msg = bot.send_message(user_id, "✅ **OTP Sent successfully!**\nAb 5-digit OTP bina space ke bhejein. (Jaise: `80513`)", parse_mode="Markdown", reply_markup=markup)
            bot.register_next_step_handler(msg, get_pr_otp)
        except Exception as e:
            bot.delete_message(user_id, status_msg.message_id)
            bot.send_message(user_id, f"❌ Error: `{e}`\nSahi number likhein.", reply_markup=get_main_menu(user_id))

    def get_pr_otp(message):
        user_id = message.from_user.id
        text_input = message.text.strip()

        if text_input.lower() in ["cancel", "/start"]:
            if user_id in premium_setup_states:
                try: run_async(premium_setup_states[user_id]['client'].disconnect())
                except: pass
                del premium_setup_states[user_id]
            return bot.send_message(user_id, "❌ Process Cancelled.", reply_markup=get_main_menu(user_id))

        safe_otp = text_input.replace(" ", "").replace("-", "")

        if len(safe_otp) == 5 and safe_otp.isdigit() and user_id in premium_setup_states:
            status_msg = bot.send_message(user_id, "⏳ OTP verify kar raha hoon...")
            try:
                async def verify_otp_async():
                    client = premium_setup_states[user_id]['client']
                    await client.sign_in(phone_number=premium_setup_states[user_id]['phone'],
                                         phone_code_hash=premium_setup_states[user_id]['hash'],
                                         phone_code=safe_otp)
                    session_string = await client.export_session_string()
                    await client.disconnect()
                    return session_string

                session_string = run_async(verify_otp_async())
                premium_setup_states[user_id]['session'] = session_string
                bot.delete_message(user_id, status_msg.message_id)
                markup = telebot.types.InlineKeyboardMarkup()
                markup.add(telebot.types.InlineKeyboardButton(text="✅ YES (Admin Bana Diya)", callback_data="pr_admin_yes"))
                bot.send_message(user_id, "✅ **Login Successful!**\nMujhe apne channel mein **Admin** banayein. Fir niche **YES** dabayein.", reply_markup=markup, parse_mode="Markdown")

            except SessionPasswordNeeded:
                bot.delete_message(user_id, status_msg.message_id)
                msg = bot.send_message(user_id, "🔐 **2-Step Verification (Password) Laga Hai!**\n\nKripya apna Telegram ka password yahan bhejein:")
                bot.register_next_step_handler(msg, get_pr_password)
            except Exception as e:
                bot.delete_message(user_id, status_msg.message_id)
                msg = bot.send_message(user_id, f"❌ Error: `{e}`\nGalat OTP. Wapas daalein.")
                bot.register_next_step_handler(msg, get_pr_otp)
        else:
            msg = bot.send_message(user_id, "❌ Galat format. 5 digit bina space ke bhejein.")
            bot.register_next_step_handler(msg, get_pr_otp)

    def get_pr_password(message):
        user_id = message.from_user.id
        password_input = message.text.strip()

        if password_input.lower() in ["cancel", "/start"]:
            if user_id in premium_setup_states:
                try: run_async(premium_setup_states[user_id]['client'].disconnect())
                except: pass
                del premium_setup_states[user_id]
            return bot.send_message(user_id, "❌ Process Cancelled.", reply_markup=get_main_menu(user_id))

        status_msg = bot.send_message(user_id, "⏳ Password verify kar raha hoon...")
        try:
            async def verify_password_async():
                client = premium_setup_states[user_id]['client']
                await client.check_password(password_input)
                session_string = await client.export_session_string()
                await client.disconnect()
                return session_string

            session_string = run_async(verify_password_async())
            premium_setup_states[user_id]['session'] = session_string
            bot.delete_message(user_id, status_msg.message_id)
            markup = telebot.types.InlineKeyboardMarkup()
            markup.add(telebot.types.InlineKeyboardButton(text="✅ YES (Admin Bana Diya)", callback_data="pr_admin_yes"))
            bot.send_message(user_id, "✅ **Login Successful!**\nMujhe apne channel mein **Admin** banayein. Fir niche **YES** dabayein.", reply_markup=markup, parse_mode="Markdown")

        except Exception as e:
            bot.delete_message(user_id, status_msg.message_id)
            msg = bot.send_message(user_id, f"❌ Error: `{e}`\nGalat password. Wapas try karein ya 'Cancel' likhein.")
            bot.register_next_step_handler(msg, get_pr_password)

    @bot.callback_query_handler(func=lambda call: call.data == "pr_admin_yes")
    def pr_admin_yes_callback(call):
        bot.answer_callback_query(call.id)
        msg = bot.send_message(call.message.chat.id, "Perfect! ✅\nAb us channel se koi bhi ek message yahan **Forward** karo.")
        bot.register_next_step_handler(msg, get_pr_forwarded_msg)

    def get_pr_forwarded_msg(message):
        user_id = message.from_user.id
        if message.text and message.text.strip().lower() in ["cancel", "/start"]:
            if user_id in premium_setup_states: del premium_setup_states[user_id]
            return bot.send_message(user_id, "❌ Cancelled.", reply_markup=get_main_menu(user_id))

        if message.forward_from_chat and message.forward_from_chat.type == 'channel':
            channel_uid = message.forward_from_chat.id
            channel_name = message.forward_from_chat.title
            phone = premium_setup_states.get(user_id, {}).get('phone', 'Unknown')
            session_str = premium_setup_states.get(user_id, {}).get('session', '')

            conn = get_db_connection()
            cursor = conn.cursor()

            cursor.execute("SELECT owner_id FROM premium_customers WHERE owner_id = ?", (user_id,))
            if cursor.fetchone():
                cursor.execute("UPDATE premium_customers SET phone_number = ?, channel_uid = ?, session_string = ? WHERE owner_id = ?",
                               (phone, channel_uid, session_str, user_id))
            else:
                expiry = int(time.time()) + (30 * 24 * 60 * 60)
                cursor.execute("INSERT INTO premium_customers (owner_id, phone_number, channel_uid, session_string, expiry_date) VALUES (?, ?, ?, ?, ?)",
                               (user_id, phone, channel_uid, session_str, expiry))

            conn.commit()
            conn.close()

            success_text = (
                f"🎉 **Setup Successful!**\n\n"
                f"Aapka **Channel Premium Remove & Live Stream Bouncer** system chalu ho gaya hai.\n"
                f"📢 **Channel:** {channel_name}\n"
                f"⏱️ **Scan Timer:** Har 5 minute mein channel clean hoga.\n"
                f"🎙 **Live Security:** 24/7 ACTIVE."
            )
            bot.send_message(user_id, success_text, parse_mode="Markdown", reply_markup=get_main_menu(user_id))
            if user_id in premium_setup_states: del premium_setup_states[user_id]
        else:
            msg = bot.send_message(user_id, "❌ Aapne channel se message forward nahi kiya. Wapas forward karein:")
            bot.register_next_step_handler(msg, get_pr_forwarded_msg)

    return bot

# ==========================================
# 🧹 BACKGROUND AUTO-SCANNER & LIVE BOUNCER
# ==========================================
def premium_cleaner_worker():
    worker_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(worker_loop)
    
    active_clients = {}
    
    async def main_manager():
        while True:
            conn = get_db_connection()
            cursor = conn.cursor()
            now = int(time.time())
            cursor.execute("SELECT owner_id, channel_uid, session_string FROM premium_customers WHERE expiry_date > ? AND session_string IS NOT NULL", (now,))
            customers = cursor.fetchall()
            
            # 1. 24/7 LIVE STREAM BOUNCER SETUP (KABHI NAHI SOTA)
            for owner_id, channel_uid, session_string in customers:
                if owner_id not in active_clients:
                    try:
                        client = Client(f"live_cleaner_{owner_id}", session_string=session_string, api_id=API_ID, api_hash=API_HASH, in_memory=True)
                        
                        @client.on_raw_update()
                        async def live_stream_kicker(cli, update, users, chats, o_id=owner_id, c_uid=channel_uid):
                            if isinstance(update, UpdateGroupCallParticipants):
                                for participant in update.participants:
                                    peer = participant.peer
                                    user_id = getattr(peer, 'user_id', None)
                                    if not user_id: continue
                                    
                                    user = users.get(user_id)
                                    if user and getattr(user, 'premium', False):
                                        c2 = get_db_connection()
                                        cur2 = c2.cursor()
                                        cur2.execute("SELECT * FROM vip_users WHERE user_id = ?", (user_id,))
                                        is_vip = cur2.fetchone()
                                        c2.close()
                                        
                                        if not is_vip:
                                            try:
                                                await cli.ban_chat_member(c_uid, user_id)
                                                try:
                                                    m_bot = telebot.TeleBot(MASTER_TOKEN)
                                                    m_bot.send_message(o_id, f"🎙 **Live Stream Bouncer:**\n🗑 Ek Premium user (`{user_id}`) ko Live Stream join karte hi turant BAN kar diya gaya hai!")
                                                except: pass
                                            except: pass

                        await client.start()
                        active_clients[owner_id] = client
                    except Exception: pass

            # 2. BACKGROUND SWEEPER (RAAT 12 BJE SE SUBAH 6 BJE TAK SOTA HAI)
            current_hour = datetime.datetime.now().hour
            if current_hour >= 6:
                cursor.execute("SELECT user_id FROM vip_users")
                vip_list = [row[0] for row in cursor.fetchall()]
                
                for owner_id, channel_uid, session_string in customers:
                    client = active_clients.get(owner_id)
                    if not client: continue
                    
                    try:
                        kicked_count = 0
                        async for _ in client.get_dialogs(limit=50): pass
                        async for member in client.get_chat_members(channel_uid):
                            await asyncio.sleep(0.05)
                            user = member.user
                            if user and getattr(user, 'is_premium', False) and member.status not in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
                                if user.id not in vip_list:
                                    try:
                                        await client.ban_chat_member(channel_uid, user.id)
                                        kicked_count += 1
                                        await asyncio.sleep(6)
                                    except FloodWait as e: await asyncio.sleep(e.value)
                                    except Exception: pass
                                    
                        if kicked_count > 0:
                            try: 
                                m_bot = telebot.TeleBot(MASTER_TOKEN)
                                m_bot.send_message(owner_id, f"✅ **Auto-Scan Complete!**\n🗑 Bot ne abhi `{kicked_count}` Premium members ko channel se remove kiya hai.")
                            except: pass
                    except Exception: pass
                    
            cursor.close()
            conn.close()
            
            # Har 5 minute wait karega
            await asyncio.sleep(300) 
            
    worker_loop.run_until_complete(main_manager())

threading.Thread(target=premium_cleaner_worker, daemon=True).start()

# ==========================================
# 🏁 IGNITION ENGINE (START ALL BOTS)
# ==========================================
print("🔥 Master Bot + SaaS Factory is starting...")

master_bot = run_bot_instance(MASTER_TOKEN, IS_MASTER=True)
active_bots[MASTER_TOKEN] = master_bot

def poll_bot(b_obj):
    # Webhook error hatane ka fix[span_0](start_span)[span_0](end_span)
    try:
        b_obj.remove_webhook()
    except Exception: pass
        
    while True:
        try:
            b_obj.infinity_polling(allowed_updates=telebot.util.update_types)
        except Exception as e:
            time.sleep(5)

threading.Thread(target=poll_bot, args=(master_bot,), daemon=True).start()

conn = get_db_connection()
cursor = conn.cursor()
cursor.execute("SELECT bot_token FROM clone_bots")
clones = cursor.fetchall()
conn.close()

for row in clones:
    clone_token = row[0]
    c_bot = run_bot_instance(clone_token, IS_MASTER=False)
    active_bots[clone_token] = c_bot
    threading.Thread(target=poll_bot, args=(c_bot,), daemon=True).start()

print("🚀 ALL BOTS ARE ONLINE AND READY!")

while True:
    time.sleep(1000)
