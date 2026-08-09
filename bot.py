#!/usr/bin/env python
# -*- coding: utf-8 -*-

import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
import sqlite3
import logging
from datetime import datetime, timedelta
import time
import re
import random
import string

# ---------- تنظیمات جدید ----------
TOKEN = "8624374078:AAEGS5-fs9NeYUMwbVrvIq3RoETJjEHX83c"
MASTER_ADMIN_ID = 8828921082
ADMIN_USERNAME = "itgvpn_suport"
SUPPORT_LINK = "https://t.me/itgvpn_suport"
CARD_NUMBER = "5892101721379440"
CHANNEL_ID = "@ITGVPN1"
CHANNEL_LINK = "https://t.me/ITGVPN1"
CHANNEL2_ID = "@give100vip"
CHANNEL2_LINK = "https://t.me/give100vip"

SECRET_ADMIN_COMMAND = "/alaoeiejeuu3uw93j3bw8i3b3hshwi3jsadminpr"

# ---------- قیمت‌ها (از دیتابیس خوانده می‌شوند) ----------
# حجم‌های عادی
DEFAULT_VOLUMES = [5, 10, 20, 30]
# حجم‌های اقتصادی
ECONOMICAL_VOLUMES = [100, 150, 250, 300]
# قیمت‌های پیش‌فرض (قیمت هر گیگ ۶۰۰۰ تومان برای عادی، و قیمت‌های ویژه برای اقتصادی)
DEFAULT_PRICES = {
    # عادی
    5: 30000,
    10: 60000,
    20: 120000,
    30: 180000,
    # اقتصادی
    100: 300000,
    150: 380000,
    250: 420000,
    300: 500000,
}
PRICES = DEFAULT_PRICES.copy()
UNLIMITED_PRICES = {'single': 150000, 'double': 200000, 'triple': 250000}
PRICE_PER_GB = 6000
CUSTOM_PRICE_PER_GB = 6000

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")
temp_actions = {}

# ---------- دیتابیس ----------
def get_db():
    return sqlite3.connect('mota_vpn_bot.db', check_same_thread=False)

def init_db():
    conn = get_db()
    c = conn.cursor()
    
    # جدول users
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        joined_date TEXT,
        balance INTEGER DEFAULT 0,
        is_blocked INTEGER DEFAULT 0)''')
    
    # جدول orders
    c.execute('''CREATE TABLE IF NOT EXISTS orders (
        order_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        volume REAL,
        price INTEGER,
        payment_method TEXT,
        status TEXT DEFAULT 'pending',
        receipt_photo_id TEXT,
        config TEXT,
        order_date TEXT,
        verified_date TEXT,
        is_custom INTEGER DEFAULT 0,
        is_test INTEGER DEFAULT 0,
        account_name TEXT,
        expiry_date TEXT,
        is_unlimited INTEGER DEFAULT 0,
        unlimited_period TEXT,
        discount_code TEXT,
        discount_amount INTEGER DEFAULT 0,
        final_price INTEGER,
        tracking_code TEXT)''')
    
    # جدول discount_codes
    c.execute('''CREATE TABLE IF NOT EXISTS discount_codes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE,
        discount_amount INTEGER,
        max_usage INTEGER DEFAULT 1,
        used_count INTEGER DEFAULT 0,
        created_by INTEGER,
        created_at TEXT,
        is_active INTEGER DEFAULT 1)''')
    
    # جدول recharge_requests
    c.execute('''CREATE TABLE IF NOT EXISTS recharge_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        amount INTEGER,
        receipt_photo_id TEXT,
        status TEXT DEFAULT 'pending',
        request_date TEXT)''')
    
    # جدول user_messages
    c.execute('''CREATE TABLE IF NOT EXISTS user_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        admin_replied INTEGER DEFAULT 0,
        message_text TEXT,
        message_type TEXT,
        file_id TEXT,
        caption TEXT,
        date TEXT)''')
    
    # ---------- جدول جدید برای قیمت‌ها ----------
    c.execute('''CREATE TABLE IF NOT EXISTS prices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        key TEXT UNIQUE,
        value INTEGER,
        description TEXT)''')
    
    # اضافه کردن ستون‌های جدید به orders در صورت نبودن
    columns = [
        ('discount_code', 'TEXT'),
        ('discount_amount', 'INTEGER DEFAULT 0'),
        ('final_price', 'INTEGER'),
        ('tracking_code', 'TEXT')
    ]
    for col, dtype in columns:
        try:
            c.execute(f'ALTER TABLE orders ADD COLUMN {col} {dtype}')
        except sqlite3.OperationalError:
            pass
    
    conn.commit()
    
    # مقداردهی اولیه قیمت‌ها در دیتابیس (در صورت خالی بودن)
    c.execute("SELECT COUNT(*) FROM prices")
    if c.fetchone()[0] == 0:
        default_prices = [
            ('price_per_gb', 6000, 'قیمت هر گیگابایت برای حجم دلخواه'),
            ('custom_price_per_gb', 6000, 'قیمت هر گیگابایت برای حجم دلخواه (همان)'),
        ]
        # عادی
        for gb in DEFAULT_VOLUMES:
            default_prices.append((f'price_{gb}g', gb * 6000, f'قیمت {gb} گیگابایت'))
        # اقتصادی
        for gb in ECONOMICAL_VOLUMES:
            default_prices.append((f'price_{gb}g', DEFAULT_PRICES[gb], f'قیمت {gb} گیگابایت (اقتصادی)'))
        # نامحدود
        default_prices.append(('unlimited_single', 150000, 'پنل نامحدود تک کاربره'))
        default_prices.append(('unlimited_double', 200000, 'پنل نامحدود دو کاربره'))
        default_prices.append(('unlimited_triple', 250000, 'پنل نامحدود سه کاربره'))
        for key, value, desc in default_prices:
            c.execute("INSERT INTO prices (key, value, description) VALUES (?,?,?)", (key, value, desc))
        conn.commit()
    
    conn.close()
    # بارگذاری قیمت‌ها در متغیرهای سراسری
    load_prices_from_db()

# ---------- توابع مدیریت قیمت‌ها ----------
def load_prices_from_db():
    """بارگذاری قیمت‌ها از دیتابیس به متغیرهای سراسری"""
    global PRICES, UNLIMITED_PRICES, PRICE_PER_GB, CUSTOM_PRICE_PER_GB
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT key, value FROM prices")
    rows = c.fetchall()
    conn.close()
    
    price_dict = {row[0]: row[1] for row in rows}
    
    # به‌روزرسانی متغیرها
    PRICE_PER_GB = price_dict.get('price_per_gb', 6000)
    CUSTOM_PRICE_PER_GB = price_dict.get('custom_price_per_gb', 6000)
    
    # بارگذاری تمام حجم‌ها (عادی و اقتصادی)
    all_volumes = set(DEFAULT_VOLUMES + ECONOMICAL_VOLUMES)
    for gb in all_volumes:
        key = f'price_{gb}g'
        PRICES[gb] = price_dict.get(key, gb * 6000)  # fallback
    
    UNLIMITED_PRICES['single'] = price_dict.get('unlimited_single', 150000)
    UNLIMITED_PRICES['double'] = price_dict.get('unlimited_double', 200000)
    UNLIMITED_PRICES['triple'] = price_dict.get('unlimited_triple', 250000)

def update_price_key(key, new_value):
    """بروزرسانی یک قیمت در دیتابیس و بارگذاری مجدد"""
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE prices SET value = ? WHERE key = ?", (new_value, key))
    conn.commit()
    conn.close()
    load_prices_from_db()

def get_price_key(key):
    """دریافت مقدار یک قیمت از دیتابیس"""
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT value FROM prices WHERE key = ?", (key,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

# ---------- توابع کمکی دیتابیس ----------
def register_user(user_id, username, first_name):
    conn = get_db()
    c = conn.cursor()
    c.execute('INSERT OR IGNORE INTO users (user_id, username, first_name, joined_date) VALUES (?,?,?,?)',
              (user_id, username, first_name, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def get_user_balance(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else 0

def update_balance(user_id, amount):
    conn = get_db()
    c = conn.cursor()
    c.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (amount, user_id))
    conn.commit()
    conn.close()

def is_user_blocked(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT is_blocked FROM users WHERE user_id = ?', (user_id,))
    row = c.fetchone()
    conn.close()
    return row and row[0] == 1

# ---------- توابع تخفیف و کد پیگیری ----------
def generate_tracking_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))

def create_discount_code(code, amount, max_usage=1, admin_id=MASTER_ADMIN_ID):
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute('INSERT INTO discount_codes (code, discount_amount, max_usage, created_by, created_at) VALUES (?,?,?,?,?)',
                  (code, amount, max_usage, admin_id, datetime.now().isoformat()))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def get_discount_code(code):
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM discount_codes WHERE code = ? AND is_active = 1', (code,))
    row = c.fetchone()
    conn.close()
    return row

def use_discount_code(code):
    conn = get_db()
    c = conn.cursor()
    c.execute('UPDATE discount_codes SET used_count = used_count + 1 WHERE code = ?', (code,))
    conn.commit()
    conn.close()

def delete_discount_code(code):
    conn = get_db()
    c = conn.cursor()
    c.execute('UPDATE discount_codes SET is_active = 0 WHERE code = ?', (code,))
    conn.commit()
    conn.close()

def list_discount_codes():
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM discount_codes WHERE is_active = 1 ORDER BY created_at DESC')
    rows = c.fetchall()
    conn.close()
    return rows

def save_order(user_id, volume, price, payment_method, is_custom=0, is_test=0, account_name=None, is_unlimited=0, unlimited_period=None, discount_code=None, discount_amount=0, final_price=None):
    conn = get_db()
    c = conn.cursor()
    tracking = generate_tracking_code()
    if final_price is None:
        final_price = price - discount_amount
    c.execute('''INSERT INTO orders 
                (user_id, volume, price, payment_method, order_date, is_custom, is_test, account_name, is_unlimited, unlimited_period, discount_code, discount_amount, final_price, tracking_code)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
              (user_id, volume, price, payment_method, datetime.now().isoformat(),
               is_custom, is_test, account_name, is_unlimited, unlimited_period, discount_code, discount_amount, final_price, tracking))
    order_id = c.lastrowid
    conn.commit()
    conn.close()
    return order_id

def update_order_receipt(order_id, receipt_photo_id):
    conn = get_db()
    c = conn.cursor()
    c.execute('UPDATE orders SET receipt_photo_id = ?, status = "waiting_verification" WHERE order_id = ?',
              (receipt_photo_id, order_id))
    conn.commit()
    conn.close()

def get_order(order_id):
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM orders WHERE order_id = ?', (order_id,))
    row = c.fetchone()
    conn.close()
    return row

def verify_order(order_id, config_url):
    conn = get_db()
    c = conn.cursor()
    c.execute('UPDATE orders SET status = "verified", config = ?, verified_date = ? WHERE order_id = ?',
              (config_url, datetime.now().isoformat(), order_id))
    conn.commit()
    conn.close()

def reject_order(order_id):
    conn = get_db()
    c = conn.cursor()
    c.execute('UPDATE orders SET status = "rejected" WHERE order_id = ?', (order_id,))
    conn.commit()
    conn.close()

def get_pending_orders():
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM orders WHERE status IN ("pending", "waiting_verification") AND is_test = 0 ORDER BY order_date DESC')
    rows = c.fetchall()
    conn.close()
    return rows

def get_pending_test_orders():
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM orders WHERE status = "pending" AND is_test = 1 ORDER BY order_date DESC')
    rows = c.fetchall()
    conn.close()
    return rows

def get_user_orders(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM orders WHERE user_id = ? ORDER BY order_date DESC', (user_id,))
    rows = c.fetchall()
    conn.close()
    return rows

def get_all_users():
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM users')
    total = c.fetchone()[0]
    conn.close()
    return total

def get_total_sales():
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM orders WHERE status = "verified" AND is_test = 0')
    count = c.fetchone()[0]
    c.execute('SELECT SUM(final_price) FROM orders WHERE status = "verified" AND is_test = 0')
    revenue = c.fetchone()[0] or 0
    conn.close()
    return count, revenue

def get_user_purchase_count(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM orders WHERE user_id = ? AND status = "verified" AND is_test = 0', (user_id,))
    count = c.fetchone()[0]
    conn.close()
    return count

def block_user(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute('UPDATE users SET is_blocked = 1 WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()

def unblock_user(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute('UPDATE users SET is_blocked = 0 WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()

def add_recharge_request(user_id, amount, receipt_photo_id):
    conn = get_db()
    c = conn.cursor()
    c.execute('INSERT INTO recharge_requests (user_id, amount, receipt_photo_id, request_date) VALUES (?,?,?,?)',
              (user_id, amount, receipt_photo_id, datetime.now().isoformat()))
    req_id = c.lastrowid
    conn.commit()
    conn.close()
    return req_id

def get_pending_recharges():
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM recharge_requests WHERE status = "pending" ORDER BY request_date DESC')
    rows = c.fetchall()
    conn.close()
    return rows

def approve_recharge(req_id):
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT user_id, amount FROM recharge_requests WHERE id = ?', (req_id,))
    row = c.fetchone()
    if row:
        user_id, amount = row
        c.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (amount, user_id))
        c.execute('UPDATE recharge_requests SET status = "approved" WHERE id = ?', (req_id,))
        conn.commit()
        conn.close()
        return user_id, amount
    conn.close()
    return None, None

def save_user_message(user_id, message_text, message_type, file_id=None, caption=None):
    conn = get_db()
    c = conn.cursor()
    c.execute('INSERT INTO user_messages (user_id, message_text, message_type, file_id, caption, date) VALUES (?,?,?,?,?,?)',
              (user_id, message_text, message_type, file_id, caption, datetime.now().isoformat()))
    msg_id = c.lastrowid
    conn.commit()
    conn.close()
    return msg_id

def mark_message_replied(msg_id):
    conn = get_db()
    c = conn.cursor()
    c.execute('UPDATE user_messages SET admin_replied = 1 WHERE id = ?', (msg_id,))
    conn.commit()
    conn.close()

def get_unreplied_messages():
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM user_messages WHERE admin_replied = 0 ORDER BY date ASC')
    rows = c.fetchall()
    conn.close()
    return rows

def get_all_users_list():
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT user_id, username, first_name, balance, is_blocked FROM users ORDER BY joined_date DESC')
    rows = c.fetchall()
    conn.close()
    return rows

# ---------- عضویت اجباری ----------
def is_user_member(user_id):
    try:
        member = bot.get_chat_member(CHANNEL_ID, user_id)
        if member.status not in ['member', 'administrator', 'creator']:
            return False
    except Exception as e:
        logger.error(f"عضویت خطا ({CHANNEL_ID}): {e}")
        if "bot is not a member" in str(e):
            bot.send_message(MASTER_ADMIN_ID, f"⚠️ ربات در کانال {CHANNEL_ID} عضو نیست! لطفاً ربات را به عنوان ادمین به کانال اضافه کنید.")
        return False

    try:
        member2 = bot.get_chat_member(CHANNEL2_ID, user_id)
        if member2.status not in ['member', 'administrator', 'creator']:
            return False
    except Exception as e:
        logger.error(f"عضویت خطا ({CHANNEL2_ID}): {e}")
        if "bot is not a member" in str(e):
            bot.send_message(MASTER_ADMIN_ID, f"⚠️ ربات در کانال {CHANNEL2_ID} عضو نیست! لطفاً ربات را به عنوان ادمین به کانال اضافه کنید.")
        return False

    return True

def send_subscription_request(user_id, next_action=None, data=None):
    temp_actions[user_id] = {'action': next_action, 'data': data} if next_action else None
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("📢 عضویت در کانال اول", url=CHANNEL_LINK, style='primary'))
    markup.add(InlineKeyboardButton("📢 عضویت در کانال دوم", url=CHANNEL2_LINK, style='primary'))
    markup.add(InlineKeyboardButton("✅ بررسی عضویت", callback_data="check_subscription", style='success'))
    text = ("⚠️ <b>کاربر گرامی؛ شما عضو کانال‌های ما نیستید</b>\n\n"
            "از طریق دکمه‌های زیر وارد هر دو کانال شده و عضو شوید.\n"
            "پس از عضویت، دکمه <b>بررسی عضویت</b> را کلیک کنید.")
    bot.send_message(user_id, text, reply_markup=markup)

# ---------- کیبوردها ----------
def main_menu_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("🛒 خرید سرویس", callback_data="main_buy", style='primary'),
        InlineKeyboardButton("🧪 اکانت تست", callback_data="main_test", style='primary')
    )
    keyboard.add(
        InlineKeyboardButton("📊 تعرفه‌ها", callback_data="main_pricing", style='primary'),
        InlineKeyboardButton("💰 کیف پول", callback_data="main_wallet", style='primary')
    )
    keyboard.add(
        InlineKeyboardButton("📱 اپلیکیشن‌ها و آموزش", callback_data="main_apps", style='primary'),
        InlineKeyboardButton("🤝 پنل همکاری", callback_data="main_partner", style='primary')
    )
    keyboard.add(
        InlineKeyboardButton("🆘 پشتیبانی", callback_data="main_support", style='primary')
    )
    return keyboard

def buy_type_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("📦 پنل حجمی", callback_data="buy_type_volume", style='primary'),
        InlineKeyboardButton("♾️ پنل نامحدود", callback_data="buy_type_unlimited", style='success')
    )
    keyboard.add(InlineKeyboardButton("🔙 بازگشت", callback_data="back_main", style='danger'))
    return keyboard

def volume_plans_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=2)
    # بخش عادی
    keyboard.add(InlineKeyboardButton("📌 <b>پکیج‌های عادی</b>", callback_data="dummy", style='primary'))
    for gb in DEFAULT_VOLUMES:
        price = PRICES[gb]
        keyboard.add(InlineKeyboardButton(f"📦 {gb}G\n{price:,} ت", callback_data=f"buy_volume_{gb}", style='primary'))
    # بخش اقتصادی
    keyboard.add(InlineKeyboardButton("💰 <b>پکیج‌های اقتصادی</b>", callback_data="dummy", style='success'))
    for gb in ECONOMICAL_VOLUMES:
        price = PRICES[gb]
        keyboard.add(InlineKeyboardButton(f"💎 {gb}G\n{price:,} ت", callback_data=f"buy_volume_{gb}", style='success'))
    keyboard.add(InlineKeyboardButton("✨ حجم دلخواه", callback_data="buy_volume_custom", style='primary'))
    keyboard.add(InlineKeyboardButton("🔙 بازگشت", callback_data="buy_back", style='danger'))
    return keyboard

def unlimited_plans_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("♾️ تک کاربره\n{:,} ت".format(UNLIMITED_PRICES['single']), callback_data="buy_unlimited_single", style='primary'),
        InlineKeyboardButton("♾️ دو کاربره\n{:,} ت".format(UNLIMITED_PRICES['double']), callback_data="buy_unlimited_double", style='primary'),
        InlineKeyboardButton("♾️ سه کاربره\n{:,} ت".format(UNLIMITED_PRICES['triple']), callback_data="buy_unlimited_triple", style='primary')
    )
    keyboard.add(InlineKeyboardButton("🔙 بازگشت", callback_data="buy_back", style='danger'))
    return keyboard

def payment_method_keyboard(order_id, discount_applied=False):
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("💳 پرداخت از کیف پول", callback_data=f"pay_wallet_{order_id}", style='success'),
        InlineKeyboardButton("🏧 کارت به کارت + ارسال رسید", callback_data=f"pay_card_{order_id}", style='primary')
    )
    if not discount_applied:
        keyboard.add(InlineKeyboardButton("🎟️ اعمال کد تخفیف", callback_data=f"apply_discount_{order_id}", style='primary'))
    keyboard.add(InlineKeyboardButton("🔙 انصراف", callback_data="back_main", style='danger'))
    return keyboard

def send_receipt_keyboard(order_id):
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("📸 ارسال رسید پرداخت", callback_data=f"send_receipt_{order_id}", style='success'))
    keyboard.add(InlineKeyboardButton("❌ لغو سفارش", callback_data=f"cancel_order_{order_id}", style='danger'))
    return keyboard

def wallet_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("📸 افزایش موجودی", callback_data="wallet_increase", style='success'),
        InlineKeyboardButton("📊 تاریخچه تراکنش‌ها", callback_data="wallet_history", style='primary')
    )
    keyboard.add(InlineKeyboardButton("🔙 بازگشت", callback_data="back_main", style='danger'))
    return keyboard

def support_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(InlineKeyboardButton("📨 ارسال مستقیم پیام به پشتیبانی", url=SUPPORT_LINK, style='primary'))
    keyboard.add(InlineKeyboardButton("🔙 بازگشت", callback_data="back_main", style='danger'))
    return keyboard

def admin_main_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("📋 سفارشات", callback_data="admin_orders", style='primary'),
        InlineKeyboardButton("🧪 تست‌ها", callback_data="admin_tests", style='primary')
    )
    keyboard.add(
        InlineKeyboardButton("💰 افزایش موجودی", callback_data="admin_recharges", style='primary'),
        InlineKeyboardButton("👥 کاربران", callback_data="admin_users", style='primary')
    )
    keyboard.add(
        InlineKeyboardButton("✏️ تغییر موجودی", callback_data="admin_change_balance", style='primary'),
        InlineKeyboardButton("📨 تیکت‌ها", callback_data="admin_messages", style='primary')
    )
    keyboard.add(
        InlineKeyboardButton("🎟️ مدیریت تخفیف‌ها", callback_data="admin_discounts", style='primary'),
        InlineKeyboardButton("📢 پیام همگانی", callback_data="admin_broadcast", style='primary')
    )
    keyboard.add(
        InlineKeyboardButton("📊 آمار", callback_data="admin_stats", style='primary'),
        InlineKeyboardButton("💰 مدیریت قیمت‌ها", callback_data="admin_prices", style='primary')
    )
    keyboard.add(
        InlineKeyboardButton("🔍 جستجوی سفارش", callback_data="admin_search_order", style='primary')
    )
    keyboard.add(InlineKeyboardButton("🚪 خروج", callback_data="admin_exit", style='danger'))
    return keyboard

def admin_discounts_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("➕ ساخت کد تخفیف", callback_data="admin_discount_create", style='success'),
        InlineKeyboardButton("📋 لیست کدها", callback_data="admin_discount_list", style='primary')
    )
    keyboard.add(InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back_main", style='danger'))
    return keyboard

def discount_list_keyboard(codes, page=0):
    keyboard = InlineKeyboardMarkup(row_width=1)
    start = page * 5
    end = start + 5
    for code in codes[start:end]:
        cid, code_str, amount, max_usage, used, created_by, created_at, active = code
        keyboard.add(InlineKeyboardButton(f"🎟️ {code_str} - {amount:,} ت (مصرف {used}/{max_usage})", callback_data=f"admin_discount_detail_{code_str}", style='primary'))
    nav = []
    if start > 0:
        nav.append(InlineKeyboardButton("⬅️ قبلی", callback_data=f"admin_discount_page_{page-1}", style='primary'))
    if end < len(codes):
        nav.append(InlineKeyboardButton("➡️ بعدی", callback_data=f"admin_discount_page_{page+1}", style='primary'))
    if nav:
        keyboard.row(*nav)
    keyboard.add(InlineKeyboardButton("🔙 بازگشت", callback_data="admin_discounts", style='danger'))
    return keyboard

def discount_detail_keyboard(code):
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("❌ حذف کد", callback_data=f"admin_discount_delete_{code}", style='danger'))
    keyboard.add(InlineKeyboardButton("🔙 بازگشت", callback_data="admin_discount_list", style='danger'))
    return keyboard

def users_list_keyboard(users, page=0):
    keyboard = InlineKeyboardMarkup(row_width=1)
    start = page * 5
    end = start + 5
    for user in users[start:end]:
        user_id, username, first_name, balance, blocked = user
        status = "🚫" if blocked else "✅"
        display = f"{status} {user_id} - {first_name or username or 'بدون نام'} - {balance:,} ت"
        keyboard.add(InlineKeyboardButton(display, callback_data=f"admin_user_{user_id}", style='primary'))
    nav = []
    if start > 0:
        nav.append(InlineKeyboardButton("⬅️ قبلی", callback_data=f"admin_users_page_{page-1}", style='primary'))
    if end < len(users):
        nav.append(InlineKeyboardButton("➡️ بعدی", callback_data=f"admin_users_page_{page+1}", style='primary'))
    if nav:
        keyboard.row(*nav)
    keyboard.add(InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back_main", style='danger'))
    return keyboard

def user_manage_keyboard(user_id):
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("🚫 مسدود", callback_data=f"admin_block_{user_id}", style='danger'),
        InlineKeyboardButton("🔓 رفع مسدودی", callback_data=f"admin_unblock_{user_id}", style='success')
    )
    keyboard.add(
        InlineKeyboardButton("💰 تغییر موجودی", callback_data=f"admin_balance_{user_id}", style='primary'),
        InlineKeyboardButton("📨 ارسال پیام", callback_data=f"admin_msg_{user_id}", style='primary')
    )
    keyboard.add(InlineKeyboardButton("🔙 بازگشت", callback_data="admin_users", style='danger'))
    return keyboard

def pending_orders_keyboard(orders, order_type='order'):
    keyboard = InlineKeyboardMarkup(row_width=1)
    for order in orders:
        order_id = order[0]
        user_id = order[1]
        volume = order[2]
        price = order[3]
        final_price = order[15] if len(order) > 15 and order[15] else price
        tracking = order[16] if len(order) > 16 else "-----"
        if order_type == 'test':
            label = f"🧪 تست - {tracking} - کاربر {user_id}"
        else:
            if len(order) > 12 and order[12] == 1:
                period = order[13]
                if period == 'single':
                    plan = "تک کاربره"
                elif period == 'double':
                    plan = "دو کاربره"
                elif period == 'triple':
                    plan = "سه کاربره"
                else:
                    plan = period
                label = f"♾️ {plan} - {tracking} - {final_price:,} ت"
            else:
                label = f"📦 {volume}G - {tracking} - {final_price:,} ت"
        keyboard.add(InlineKeyboardButton(label, callback_data=f"admin_{order_type}_{order_id}", style='primary'))
    keyboard.add(InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back_main", style='danger'))
    return keyboard

def order_action_keyboard(order_id, is_test=False):
    keyboard = InlineKeyboardMarkup(row_width=2)
    prefix = "test" if is_test else "order"
    keyboard.add(
        InlineKeyboardButton("✅ تایید و ارسال", callback_data=f"admin_verify_{prefix}_{order_id}", style='success'),
        InlineKeyboardButton("❌ رد سفارش", callback_data=f"admin_reject_{prefix}_{order_id}", style='danger')
    )
    keyboard.add(InlineKeyboardButton("🔙 برگشت", callback_data="admin_orders" if not is_test else "admin_tests", style='danger'))
    return keyboard

def pending_recharges_keyboard(recharges):
    keyboard = InlineKeyboardMarkup(row_width=1)
    for req in recharges:
        req_id = req[0]
        user_id = req[1]
        amount = req[2]
        keyboard.add(InlineKeyboardButton(f"💰 #{req_id} - کاربر {user_id} - {amount:,} ت", callback_data=f"admin_recharge_{req_id}", style='primary'))
    keyboard.add(InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back_main", style='danger'))
    return keyboard

def recharge_action_keyboard(req_id):
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("✅ تایید", callback_data=f"admin_approve_recharge_{req_id}", style='success'),
        InlineKeyboardButton("❌ رد", callback_data=f"admin_reject_recharge_{req_id}", style='danger')
    )
    keyboard.add(InlineKeyboardButton("🔙 برگشت", callback_data="admin_recharges", style='danger'))
    return keyboard

def unreplied_messages_keyboard(messages):
    keyboard = InlineKeyboardMarkup(row_width=1)
    for msg in messages:
        msg_id = msg[0]
        user_id = msg[1]
        msg_text = msg[3][:30] + "..." if len(msg[3]) > 30 else msg[3]
        keyboard.add(InlineKeyboardButton(f"📨 از {user_id}: {msg_text}", callback_data=f"admin_reply_msg_{msg_id}", style='primary'))
    keyboard.add(InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back_main", style='danger'))
    return keyboard

def reply_message_keyboard(user_id, msg_id):
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("✏️ پاسخ", callback_data=f"admin_reply_send_{user_id}_{msg_id}", style='success'))
    keyboard.add(InlineKeyboardButton("🔙 بازگشت", callback_data="admin_messages", style='danger'))
    return keyboard

def get_main_reply_keyboard():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    keyboard.add(
        KeyboardButton("🛒 خرید سرویس"),
        KeyboardButton("🧪 اکانت تست"),
        KeyboardButton("📊 تعرفه‌ها"),
        KeyboardButton("💰 کیف پول"),
        KeyboardButton("📱 اپلیکیشن‌ها و آموزش"),
        KeyboardButton("🤝 پنل همکاری"),
        KeyboardButton("🆘 پشتیبانی")
    )
    return keyboard

def get_admin_reply_keyboard():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    keyboard.add(KeyboardButton("🔧 پنل مدیریت"), KeyboardButton("🔙 منوی کاربری"))
    return keyboard

def apps_platform_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("📱 اندروید", callback_data="apps_android", style='primary'),
        InlineKeyboardButton("🍏 آیفون", callback_data="apps_ios", style='primary')
    )
    keyboard.add(InlineKeyboardButton("🔙 بازگشت", callback_data="back_main", style='danger'))
    return keyboard

def apps_android_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("🌐 HTTP Injector", callback_data="app_android_http", style='primary'),
        InlineKeyboardButton("🔒 Npv Tunnel", callback_data="app_android_npv", style='primary')
    )
    keyboard.add(InlineKeyboardButton("🔙 بازگشت", callback_data="apps_back", style='danger'))
    return keyboard

def apps_ios_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("🌐 HTTP Injector", callback_data="app_ios_http", style='primary'),
        InlineKeyboardButton("🔒 Npv Tunnel", callback_data="app_ios_npv", style='primary')
    )
    keyboard.add(InlineKeyboardButton("🔙 بازگشت", callback_data="apps_back", style='danger'))
    return keyboard

def admin_prices_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("📦 قیمت حجم‌ها", callback_data="admin_prices_volume", style='primary'),
        InlineKeyboardButton("♾️ قیمت نامحدود", callback_data="admin_prices_unlimited", style='primary')
    )
    keyboard.add(
        InlineKeyboardButton("📊 قیمت هر گیگ (دلخواه)", callback_data="admin_prices_per_gb", style='primary'),
        InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back_main", style='danger')
    )
    return keyboard

def admin_volume_prices_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=1)
    # عادی
    keyboard.add(InlineKeyboardButton("📌 عادی", callback_data="dummy", style='primary'))
    for gb in DEFAULT_VOLUMES:
        price = PRICES[gb]
        keyboard.add(InlineKeyboardButton(f"{gb} GB: {price:,} تومان", callback_data=f"admin_price_edit_volume_{gb}", style='primary'))
    # اقتصادی
    keyboard.add(InlineKeyboardButton("💰 اقتصادی", callback_data="dummy", style='success'))
    for gb in ECONOMICAL_VOLUMES:
        price = PRICES[gb]
        keyboard.add(InlineKeyboardButton(f"{gb} GB: {price:,} تومان", callback_data=f"admin_price_edit_volume_{gb}", style='success'))
    keyboard.add(InlineKeyboardButton("🔙 بازگشت", callback_data="admin_prices", style='danger'))
    return keyboard

def admin_unlimited_prices_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(InlineKeyboardButton(f"تک کاربره: {UNLIMITED_PRICES['single']:,} تومان", callback_data="admin_price_edit_unlimited_single", style='primary'))
    keyboard.add(InlineKeyboardButton(f"دو کاربره: {UNLIMITED_PRICES['double']:,} تومان", callback_data="admin_price_edit_unlimited_double", style='primary'))
    keyboard.add(InlineKeyboardButton(f"سه کاربره: {UNLIMITED_PRICES['triple']:,} تومان", callback_data="admin_price_edit_unlimited_triple", style='primary'))
    keyboard.add(InlineKeyboardButton("🔙 بازگشت", callback_data="admin_prices", style='danger'))
    return keyboard

# ---------- توابع اطلاع‌رسانی به ادمین ----------
def notify_admin(text, photo_id=None, reply_markup=None):
    try:
        if photo_id:
            bot.send_photo(MASTER_ADMIN_ID, photo_id, caption=text, parse_mode="HTML", reply_markup=reply_markup)
        else:
            bot.send_message(MASTER_ADMIN_ID, text, parse_mode="HTML", reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"ارسال به ادمین خطا: {e}")

def generate_invoice_text(order):
    order_id = order[0]
    volume = order[2]
    price = order[3]
    final_price = order[15] if len(order) > 15 and order[15] else price
    discount_amount = order[14] if len(order) > 14 and order[14] else 0
    tracking = order[16] if len(order) > 16 else ""
    is_unlimited = order[12] if len(order) > 12 else 0
    unlimited_period = order[13] if len(order) > 13 else None

    if is_unlimited:
        if unlimited_period == 'single':
            plan_name = "تک کاربره"
        elif unlimited_period == 'double':
            plan_name = "دو کاربره"
        elif unlimited_period == 'triple':
            plan_name = "سه کاربره"
        else:
            plan_name = unlimited_period
        service_type = f"پنل نامحدود ({plan_name})"
        volume_text = "نامحدود"
        duration = "۳۰ روز"
    else:
        service_type = f"{volume} گیگابایت"
        volume_text = f"{volume} گیگابایت"
        duration = "۳۰ روز"

    discount_line = ""
    if discount_amount > 0:
        discount_line = f"🎟️ تخفیف: -{discount_amount:,} تومان\n"

    text = (f"🛒 <b>خرید اشتراک</b>\n"
            f"🕐 {datetime.now().strftime('%H:%M')}\n\n"
            f"📄 <b>پیش فاکتور شماره {order_id}</b>\n"
            f"📌 <b>سروز:</b> vip\n"
            f"📦 <b>نوع سرویس:</b> {service_type}\n"
            f"⏳ <b>مدت اعتبار:</b> {duration}\n"
            f"📊 <b>حجم بسته:</b> {volume_text}\n"
            f"{discount_line}"
            f"💰 <b>مبلغ قابل پرداخت:</b> {final_price:,} تومان\n\n"
            f"🔑 <b>کد پیگیری:</b> <code>{tracking}</code>\n\n"
            f"✅ <b>سفارش شما آماده پرداخت است</b>")
    return text

# ---------- هندلرها ----------
@bot.message_handler(commands=['start'])
def cmd_start(message):
    user_id = message.from_user.id
    username = message.from_user.username or ""
    first_name = message.from_user.first_name or ""
    register_user(user_id, username, first_name)
    if is_user_blocked(user_id):
        bot.send_message(user_id, "⛔ شما مسدود شده‌اید.")
        return
    if not is_user_member(user_id):
        send_subscription_request(user_id, 'start')
        return
    welcome_text = ("✨ <b>به ربات رسمی ITGVPN خوش آمدید</b> ✨\n\n"
                    "🔹 <b>ارائه‌دهنده سرورهای اختصاصی با بهترین کیفیت</b>\n"
                    "🔹 <b>مولتی لوکیشن</b>\n"
                    "🔹 <b>بدون ضریب و مصرف اضافه</b>\n"
                    "🔹 <b>لینک ساب رایگان</b>\n"
                    "🔹 <b>پشتیبانی ۲۴ ساعته</b>\n\n"
                    "👇 <b>از دکمه‌های زیر استفاده کنید</b> 👇")
    bot.send_message(user_id, welcome_text, reply_markup=main_menu_keyboard())
    bot.send_message(user_id, "🔽 <b>منوی اصلی</b> 🔽", reply_markup=get_main_reply_keyboard())
    notify_admin(f"🔰 کاربر جدید: {user_id} (@{username}) وارد ربات شد.")

@bot.message_handler(commands=[SECRET_ADMIN_COMMAND.lstrip('/')])
def secret_admin_panel(message):
    if message.from_user.id == MASTER_ADMIN_ID:
        bot.send_message(MASTER_ADMIN_ID, "🔐 <b>پنل مدیریت فعال شد</b>", reply_markup=get_admin_reply_keyboard())
        bot.send_message(MASTER_ADMIN_ID, "🔧 <b>منوی مدیریت:</b>", reply_markup=admin_main_keyboard())
    else:
        bot.send_message(message.chat.id, "⛔ <b>دسترسی غیرمجاز!</b>")

@bot.callback_query_handler(func=lambda call: call.data == "check_subscription")
def check_subscription_callback(call):
    user_id = call.from_user.id
    if is_user_member(user_id):
        bot.answer_callback_query(call.id, "✅ عضویت تایید شد!")
        bot.delete_message(call.message.chat.id, call.message.message_id)
        if user_id in temp_actions and temp_actions[user_id]:
            action = temp_actions[user_id]['action']
            del temp_actions[user_id]
            if action == 'start':
                cmd_start(call.message)
            elif action == 'buy':
                bot.send_message(user_id, "📦 <b>نوع پنل مورد نظر خود را انتخاب کنید:</b>", reply_markup=buy_type_keyboard())
            elif action == 'test':
                send_test_info(user_id)
            elif action == 'wallet':
                show_wallet(user_id)
            elif action == 'pricing':
                show_pricing(user_id)
            elif action == 'apps':
                show_apps_menu(user_id)
            elif action == 'support':
                bot.send_message(user_id, "🆘 <b>پشتیبانی</b>\n\nارتباط با ادمین:", reply_markup=support_keyboard())
            elif action == 'partner':
                show_partner_info(user_id)
        else:
            cmd_start(call.message)
    else:
        bot.answer_callback_query(call.id, "❌ هنوز عضو نشده‌اید!", show_alert=True)

def send_test_info(user_id):
    text = ("🧪 <b>اکانت تست ITGVPN</b>\n\n"
            "🔹 برای دریافت اکانت تست، ابتدا در کانال زیر عضو شوید.\n"
            "🔹 پس از عضویت، از ادمین درخواست تست دهید.\n"
            "🔹 اکانت تست با حجم <b>۱۰۰ مگابایت</b> و اعتبار <b>۲۴ ساعته</b> ارائه می‌شود.\n\n"
            f"📢 <b>کانال ما:</b> {CHANNEL_LINK}\n\n"
            "👇 <b>برای عضویت و دریافت تست روی دکمه زیر کلیک کنید:</b>")
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("📢 عضویت در کانال و دریافت تست", url=CHANNEL_LINK, style='primary'))
    markup.add(InlineKeyboardButton("🔙 بازگشت", callback_data="back_main", style='danger'))
    bot.send_message(user_id, text, reply_markup=markup)

def show_pricing(user_id):
    text = "📊 <b>تعرفه‌های ITGVPN</b>\n\n"
    text += "🔹 <b>پکیج‌های عادی (مولتی لوکیشن)</b>\n"
    for gb in DEFAULT_VOLUMES:
        price = PRICES[gb]
        text += f"💎 {gb} GB ➖ {price:,} تومان\n"
    text += "\n💰 <b>پکیج‌های اقتصادی (حجم بالا)</b>\n"
    for gb in ECONOMICAL_VOLUMES:
        price = PRICES[gb]
        text += f"💎 {gb} GB ➖ {price:,} تومان\n"
    text += f"\n✨ حجم دلخواه: هر گیگ {CUSTOM_PRICE_PER_GB:,} تومان"
    text += "\n\n♾️ <b>پنل نامحدود (حجم و کاربر نامحدود):</b>\n"
    text += f"📦 تک کاربره ➖ {UNLIMITED_PRICES['single']:,} تومان\n"
    text += f"📦 دو کاربره ➖ {UNLIMITED_PRICES['double']:,} تومان\n"
    text += f"📦 سه کاربره ➖ {UNLIMITED_PRICES['triple']:,} تومان"
    bot.send_message(user_id, text, reply_markup=get_main_reply_keyboard())

def show_wallet(user_id):
    balance = get_user_balance(user_id)
    purchase_count = get_user_purchase_count(user_id)
    user_info = bot.get_chat(user_id)
    username = user_info.username or "ندارد"
    first_name = user_info.first_name or "کاربر"
    text = (f"💰 <b>کیف پول شما</b>\n\n"
            f"👤 <b>نام:</b> {first_name}\n"
            f"🆔 <b>آیدی عددی:</b> <code>{user_id}</code>\n"
            f"📛 <b>یوزرنیم:</b> @{username}\n"
            f"💵 <b>موجودی:</b> {balance:,} تومان\n"
            f"📊 <b>تعداد خرید:</b> {purchase_count} مورد\n"
            f"🕐 <b>آخرین بروزرسانی:</b> {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
            "برای افزایش موجودی، مبلغ را به کارت زیر واریز کرده و رسید را ارسال کنید:\n"
            f"<code>{CARD_NUMBER}</code>\n\n"
            "⚠️ <b>توجه:</b> فقط کارت به کارت قابل قبول است. در صورت اشتباه در واریز، مسئولیت با خود شماست.")
    bot.send_message(user_id, text, reply_markup=wallet_keyboard())

def show_apps_menu(user_id):
    text = "📱 <b>انتخاب سیستمعامل:</b>\n\nلطفاً سیستمعامل خود را انتخاب کنید تا برنامه‌های مناسب را مشاهده کنید."
    bot.send_message(user_id, text, reply_markup=apps_platform_keyboard())

def show_partner_info(user_id):
    text = ("🤝 <b>پنل همکاری ITGVPN</b>\n\n"
            "🔹 <b>قیمت هر گیگ برای همکاران:</b> ۴,۰۰۰ تومان\n"
            "🔹 <b>ربات اختصاصی فروش</b> (مشابه همین ربات)\n"
            "🔹 <b>پنل مدیریت کانفیگ</b> با قابلیت ساخت نامحدود کانفیگ\n"
            "🔹 <b>هزینه پنل ماهانه:</b> ۱,۲۸۰,۰۰۰ تومان\n\n"
            "📌 برای ثبت‌نام و دریافت اطلاعات بیشتر، با ادمین تماس بگیرید:\n"
            f"{SUPPORT_LINK}")
    bot.send_message(user_id, text, reply_markup=get_main_reply_keyboard())

# ---------- دکمه‌های ریپلای ----------
@bot.message_handler(func=lambda m: m.text == "🛒 خرید سرویس")
def user_buy_button(message):
    user_id = message.from_user.id
    if is_user_blocked(user_id):
        bot.send_message(user_id, "⛔ شما مسدود شده‌اید.")
        return
    if not is_user_member(user_id):
        send_subscription_request(user_id, 'buy')
        return
    bot.send_message(user_id, "📦 <b>نوع پنل مورد نظر خود را انتخاب کنید:</b>", reply_markup=buy_type_keyboard())

@bot.message_handler(func=lambda m: m.text == "🧪 اکانت تست")
def user_test_button(message):
    user_id = message.from_user.id
    if is_user_blocked(user_id):
        bot.send_message(user_id, "⛔ شما مسدود شده‌اید.")
        return
    if not is_user_member(user_id):
        send_subscription_request(user_id, 'test')
        return
    send_test_info(user_id)

@bot.message_handler(func=lambda m: m.text == "📊 تعرفه‌ها")
def user_pricing_button(message):
    user_id = message.from_user.id
    if is_user_blocked(user_id):
        bot.send_message(user_id, "⛔ شما مسدود شده‌اید.")
        return
    if not is_user_member(user_id):
        send_subscription_request(user_id, 'pricing')
        return
    show_pricing(user_id)

@bot.message_handler(func=lambda m: m.text == "💰 کیف پول")
def user_wallet_button(message):
    user_id = message.from_user.id
    if is_user_blocked(user_id):
        bot.send_message(user_id, "⛔ شما مسدود شده‌اید.")
        return
    if not is_user_member(user_id):
        send_subscription_request(user_id, 'wallet')
        return
    show_wallet(user_id)

@bot.message_handler(func=lambda m: m.text == "📱 اپلیکیشن‌ها و آموزش")
def user_apps_button(message):
    user_id = message.from_user.id
    if is_user_blocked(user_id):
        bot.send_message(user_id, "⛔ شما مسدود شده‌اید.")
        return
    if not is_user_member(user_id):
        send_subscription_request(user_id, 'apps')
        return
    show_apps_menu(user_id)

@bot.message_handler(func=lambda m: m.text == "🤝 پنل همکاری")
def user_partner_button(message):
    user_id = message.from_user.id
    if is_user_blocked(user_id):
        bot.send_message(user_id, "⛔ شما مسدود شده‌اید.")
        return
    if not is_user_member(user_id):
        send_subscription_request(user_id, 'partner')
        return
    show_partner_info(user_id)

@bot.message_handler(func=lambda m: m.text == "🆘 پشتیبانی")
def user_support_button(message):
    user_id = message.from_user.id
    if is_user_blocked(user_id):
        bot.send_message(user_id, "⛔ شما مسدود شده‌اید.")
        return
    if not is_user_member(user_id):
        send_subscription_request(user_id, 'support')
        return
    bot.send_message(user_id, "🆘 <b>پشتیبانی</b>\n\nارتباط با ادمین:", reply_markup=support_keyboard())

@bot.message_handler(func=lambda m: m.text == "🔧 پنل مدیریت" and m.from_user.id == MASTER_ADMIN_ID)
def admin_panel_button(message):
    bot.send_message(MASTER_ADMIN_ID, "🔧 <b>منوی مدیریت:</b>", reply_markup=admin_main_keyboard())

@bot.message_handler(func=lambda m: m.text == "🔙 منوی کاربری" and m.from_user.id == MASTER_ADMIN_ID)
def back_to_user_menu(message):
    bot.send_message(MASTER_ADMIN_ID, "🔽 <b>منوی کاربری:</b>", reply_markup=get_main_reply_keyboard())
    cmd_start(message)

# ---------- ذخیره پیام‌های کاربران ----------
@bot.message_handler(func=lambda m: m.from_user.id != MASTER_ADMIN_ID and m.text not in ["🛒 خرید سرویس", "🧪 اکانت تست", "📊 تعرفه‌ها", "💰 کیف پول", "📱 اپلیکیشن‌ها و آموزش", "🤝 پنل همکاری", "🆘 پشتیبانی"] and not m.text.startswith('/'))
def handle_user_messages(message):
    user_id = message.from_user.id
    if is_user_blocked(user_id):
        return
    if not is_user_member(user_id):
        send_subscription_request(user_id, None)
        return
    msg_type = "text"
    file_id = None
    caption = None
    text = message.text or ""
    if message.content_type == "photo":
        msg_type = "photo"
        file_id = message.photo[-1].file_id
        text = message.caption or "عکس"
    elif message.content_type == "document":
        msg_type = "document"
        file_id = message.document.file_id
        text = message.caption or f"فایل: {message.document.file_name}"
    elif message.content_type == "video":
        msg_type = "video"
        file_id = message.video.file_id
        text = message.caption or "ویدئو"
    elif message.content_type == "voice":
        msg_type = "voice"
        file_id = message.voice.file_id
        text = "پیام صوتی"
    elif message.content_type == "sticker":
        msg_type = "sticker"
        file_id = message.sticker.file_id
        text = f"استیکر: {message.sticker.emoji}"
    msg_id = save_user_message(user_id, text, msg_type, file_id, caption)
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("✏️ پاسخ", callback_data=f"admin_reply_send_{user_id}_{msg_id}", style='success'))
    if msg_type == "text":
        notify_admin(f"📩 <b>پیام از کاربر</b> {user_id}:\n\n{text}", reply_markup=keyboard)
    elif msg_type == "photo":
        bot.send_photo(MASTER_ADMIN_ID, file_id, caption=f"📩 <b>پیام از کاربر</b> {user_id}:\n\n{text}", reply_markup=keyboard)
    elif msg_type == "document":
        bot.send_document(MASTER_ADMIN_ID, file_id, caption=f"📩 <b>پیام از کاربر</b> {user_id}:\n\n{text}", reply_markup=keyboard)
    elif msg_type == "video":
        bot.send_video(MASTER_ADMIN_ID, file_id, caption=f"📩 <b>پیام از کاربر</b> {user_id}:\n\n{text}", reply_markup=keyboard)
    elif msg_type == "voice":
        bot.send_voice(MASTER_ADMIN_ID, file_id, caption=f"📩 <b>پیام از کاربر</b> {user_id}:\n\n{text}", reply_markup=keyboard)
    elif msg_type == "sticker":
        bot.send_sticker(MASTER_ADMIN_ID, file_id, reply_markup=keyboard)

# ---------- هندلرهای کالبک ----------
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    user_id = call.from_user.id
    data = call.data

    if data == "dummy":
        bot.answer_callback_query(call.id)
        return

    if not is_user_member(user_id) and data not in ["check_subscription", "back_main", "apps_back", "buy_back", "admin_discounts", "admin_discount_create", "admin_discount_list", "admin_discount_page", "admin_discount_detail", "admin_discount_delete", "admin_prices", "admin_prices_volume", "admin_prices_unlimited", "admin_prices_per_gb", "admin_price_edit_volume", "admin_price_edit_unlimited"]:
        bot.answer_callback_query(call.id, "🔒 ابتدا عضو کانال شوید!", show_alert=True)
        send_subscription_request(user_id, None)
        return

    if data == "back_main":
        bot.edit_message_text("🔽 <b>منوی اصلی</b> 🔽", call.message.chat.id, call.message.message_id, reply_markup=main_menu_keyboard())
        bot.answer_callback_query(call.id)
        return

    if data == "buy_back":
        bot.edit_message_text("📦 <b>نوع پنل مورد نظر خود را انتخاب کنید:</b>", call.message.chat.id, call.message.message_id, reply_markup=buy_type_keyboard())
        bot.answer_callback_query(call.id)
        return

    if data == "main_buy":
        bot.edit_message_text("📦 <b>نوع پنل مورد نظر خود را انتخاب کنید:</b>", call.message.chat.id, call.message.message_id, reply_markup=buy_type_keyboard())
        bot.answer_callback_query(call.id)
        return

    if data == "main_test":
        send_test_info(user_id)
        bot.delete_message(call.message.chat.id, call.message.message_id)
        bot.answer_callback_query(call.id)
        return

    if data == "main_pricing":
        show_pricing_inline(call)
        return

    if data == "main_wallet":
        show_wallet_inline(call)
        return

    if data == "main_apps":
        show_apps_inline(call)
        return

    if data == "main_partner":
        show_partner_inline(call)
        return

    if data == "main_support":
        bot.edit_message_text("🆘 <b>پشتیبانی</b>\n\nارتباط با ادمین:", call.message.chat.id, call.message.message_id, reply_markup=support_keyboard())
        bot.answer_callback_query(call.id)
        return

    if data == "buy_type_volume":
        bot.edit_message_text("📦 <b>انتخاب حجم:</b>", call.message.chat.id, call.message.message_id, reply_markup=volume_plans_keyboard())
        bot.answer_callback_query(call.id)
        return

    if data == "buy_type_unlimited":
        bot.edit_message_text("♾️ <b>انتخاب پنل نامحدود:</b>", call.message.chat.id, call.message.message_id, reply_markup=unlimited_plans_keyboard())
        bot.answer_callback_query(call.id)
        return

    if data.startswith("buy_volume_"):
        volume_str = data.split("_")[2]
        if volume_str == "custom":
            msg = bot.send_message(call.message.chat.id, "📝 <b>لطفاً حجم مورد نظر را به گیگابایت وارد کنید (عدد):</b>")
            bot.register_next_step_handler(msg, process_custom_volume)
            bot.answer_callback_query(call.id)
            return
        try:
            volume = int(volume_str)
            price = PRICES.get(volume)
            if not price:
                raise ValueError
        except:
            bot.answer_callback_query(call.id, "❌ مقدار نامعتبر!", show_alert=True)
            return
        order_id = save_order(user_id, volume, price, None, is_custom=0)
        invoice_text = generate_invoice_text(get_order(order_id))
        bot.edit_message_text(invoice_text, call.message.chat.id, call.message.message_id, reply_markup=payment_method_keyboard(order_id, discount_applied=False))
        bot.answer_callback_query(call.id)
        return

    if data.startswith("buy_unlimited_"):
        period = data.split("_")[2]
        price = UNLIMITED_PRICES[period]
        order_id = save_order(user_id, 0, price, None, is_unlimited=1, unlimited_period=period)
        invoice_text = generate_invoice_text(get_order(order_id))
        bot.edit_message_text(invoice_text, call.message.chat.id, call.message.message_id, reply_markup=payment_method_keyboard(order_id, discount_applied=False))
        bot.answer_callback_query(call.id)
        return

    if data.startswith("apply_discount_"):
        order_id = int(data.split("_")[2])
        order = get_order(order_id)
        if not order:
            bot.answer_callback_query(call.id, "❌ سفارش یافت نشد!", show_alert=True)
            return
        if order[5] != 'pending':
            bot.answer_callback_query(call.id, "❌ سفارش قابل تغییر نیست!", show_alert=True)
            return
        temp_actions[user_id] = {'action': 'discount', 'order_id': order_id}
        msg = bot.send_message(call.message.chat.id, "🎟️ <b>کد تخفیف خود را وارد کنید:</b>")
        bot.register_next_step_handler(msg, process_discount_code)
        bot.answer_callback_query(call.id)
        return

    if data.startswith("pay_wallet_"):
        order_id = int(data.split("_")[2])
        order = get_order(order_id)
        if not order:
            bot.answer_callback_query(call.id, "❌ سفارش یافت نشد!", show_alert=True)
            return
        final_price = order[15] if len(order) > 15 and order[15] else order[3]
        balance = get_user_balance(user_id)
        if balance >= final_price:
            update_balance(user_id, -final_price)
            conn = get_db()
            c = conn.cursor()
            c.execute('UPDATE orders SET status = "verified", payment_method = "wallet", verified_date = ? WHERE order_id = ?',
                      (datetime.now().isoformat(), order_id))
            conn.commit()
            conn.close()
            if len(order) > 12 and order[12] == 1:
                period = order[13]
                if period == 'single':
                    plan_name = "تک کاربره"
                elif period == 'double':
                    plan_name = "دو کاربره"
                elif period == 'triple':
                    plan_name = "سه کاربره"
                else:
                    plan_name = period
                product_name = f"پنل نامحدود ({plan_name})"
            else:
                product_name = f"{order[2]} GB"
            bot.edit_message_text(
                f"✅ <b>پرداخت موفق!</b>\nسفارش #{order_id} ({product_name}) تایید شد.\nدر انتظار ارسال کانفیگ از طرف ادمین.",
                call.message.chat.id, call.message.message_id, reply_markup=main_menu_keyboard())
            notify_admin(
                f"🛍️ <b>سفارش #{order_id} با کیف پول پرداخت شد.</b>\nکاربر: {user_id}\nمحصول: {product_name}\nمبلغ: {final_price:,} تومان\nلطفاً کانفیگ را ارسال کنید.",
                reply_markup=order_action_keyboard(order_id, is_test=False))
        else:
            bot.answer_callback_query(call.id, f"❌ موجودی کافی نیست! موجودی: {balance:,} تومان", show_alert=True)
        return

    if data.startswith("pay_card_"):
        order_id = int(data.split("_")[2])
        order = get_order(order_id)
        if not order:
            bot.answer_callback_query(call.id, "❌ سفارش یافت نشد!", show_alert=True)
            return
        final_price = order[15] if len(order) > 15 and order[15] else order[3]
        if len(order) > 12 and order[12] == 1:
            period = order[13]
            if period == 'single':
                plan_name = "تک کاربره"
            elif period == 'double':
                plan_name = "دو کاربره"
            elif period == 'triple':
                plan_name = "سه کاربره"
            else:
                plan_name = period
            product_name = f"پنل نامحدود ({plan_name})"
        else:
            product_name = f"{order[2]} GB"
        text = (f"🧾 <b>سفارش #{order_id}</b>\n"
                f"📦 محصول: {product_name}\n"
                f"💰 مبلغ قابل پرداخت: {final_price:,} تومان\n\n"
                f"💳 <b>شماره کارت:</b>\n<code>{CARD_NUMBER}</code>\n\n"
                f"پس از واریز دقیقاً {final_price:,} تومان، روی دکمه زیر کلیک کرده و رسید را ارسال کنید.\n\n"
                f"⚠️ <b>توجه:</b> فقط کارت به کارت قابل قبول است. در صورت اشتباه در واریز، مسئولیت با خود شماست.")
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="HTML", reply_markup=send_receipt_keyboard(order_id))
        bot.answer_callback_query(call.id)
        return

    if data.startswith("send_receipt_"):
        order_id = int(data.split("_")[2])
        msg = bot.send_message(call.message.chat.id, "🖼️ <b>تصویر رسید را ارسال کنید (فقط عکس):</b>")
        bot.register_next_step_handler(msg, lambda m: save_order_receipt(m, order_id, call.message.chat.id, call.message.message_id))
        bot.answer_callback_query(call.id)
        return

    if data.startswith("cancel_order_"):
        order_id = int(data.split("_")[2])
        bot.edit_message_text(f"❌ <b>سفارش #{order_id} لغو شد.</b>", call.message.chat.id, call.message.message_id, reply_markup=main_menu_keyboard())
        bot.answer_callback_query(call.id)
        return

    if data == "wallet_increase":
        msg = bot.send_message(call.message.chat.id, "💰 <b>مبلغ مورد نظر را به تومان وارد کنید (عدد):</b>")
        bot.register_next_step_handler(msg, process_balance_amount)
        bot.answer_callback_query(call.id)
        return

    if data == "wallet_history":
        orders = get_user_orders(user_id)
        if not orders:
            bot.answer_callback_query(call.id, "📭 هیچ تراکنشی ندارید.", show_alert=True)
            return
        text = "📊 <b>تاریخچه تراکنش‌ها</b>\n\n"
        for order in orders[:20]:
            status = "✅" if order[5]=='verified' else "⏳"
            if len(order) > 12 and order[12] == 1:
                period = order[13]
                if period == 'single':
                    plan = "نامحدود (تک)"
                elif period == 'double':
                    plan = "نامحدود (دو)"
                elif period == 'triple':
                    plan = "نامحدود (سه)"
                else:
                    plan = f"نامحدود ({period})"
            else:
                plan = f"{order[2]} GB"
            final_price = order[15] if len(order) > 15 and order[15] else order[3]
            text += f"{status} {plan} - {final_price:,} ت\n"
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=wallet_keyboard())
        bot.answer_callback_query(call.id)
        return

    # ---------- بخش ادمین ----------
    if user_id != MASTER_ADMIN_ID:
        bot.answer_callback_query(call.id, "⛔ دسترسی غیرمجاز!", show_alert=True)
        return

    if data == "admin_discounts":
        bot.edit_message_text("🎟️ <b>مدیریت کدهای تخفیف</b>", call.message.chat.id, call.message.message_id, reply_markup=admin_discounts_keyboard())
        bot.answer_callback_query(call.id)
        return

    if data == "admin_discount_create":
        msg = bot.send_message(MASTER_ADMIN_ID, "🎟️ <b>ساخت کد تخفیف جدید</b>\n\nلطفاً اطلاعات را به صورت زیر وارد کنید:\n<code>کد مبلغ تعداد_استفاده</code>\nمثال: <code>SAVE20 20000 5</code>\n(تعداد استفاده پیش‌فرض 1)")
        bot.register_next_step_handler(msg, admin_create_discount)
        bot.answer_callback_query(call.id)
        return

    if data == "admin_discount_list":
        codes = list_discount_codes()
        if not codes:
            bot.edit_message_text("📭 <b>هیچ کد تخفیفی وجود ندارد.</b>", call.message.chat.id, call.message.message_id, reply_markup=admin_discounts_keyboard())
        else:
            bot.edit_message_text("🎟️ <b>لیست کدهای تخفیف فعال:</b>", call.message.chat.id, call.message.message_id, reply_markup=discount_list_keyboard(codes, 0))
        bot.answer_callback_query(call.id)
        return

    if data.startswith("admin_discount_page_"):
        page = int(data.split("_")[-1])
        codes = list_discount_codes()
        bot.edit_message_text("🎟️ <b>لیست کدهای تخفیف فعال:</b>", call.message.chat.id, call.message.message_id, reply_markup=discount_list_keyboard(codes, page))
        bot.answer_callback_query(call.id)
        return

    if data.startswith("admin_discount_detail_"):
        code = data.split("_", 3)[-1]
        codes = list_discount_codes()
        found = next((c for c in codes if c[1] == code), None)
        if not found:
            bot.answer_callback_query(call.id, "❌ کد یافت نشد!", show_alert=True)
            return
        cid, code_str, amount, max_usage, used, created_by, created_at, active = found
        text = (f"🎟️ <b>جزئیات کد تخفیف</b>\n"
                f"🔑 کد: <code>{code_str}</code>\n"
                f"💰 مبلغ تخفیف: {amount:,} تومان\n"
                f"📊 تعداد استفاده: {used}/{max_usage}\n"
                f"👤 ساخته شده توسط: {created_by}\n"
                f"🕐 تاریخ ساخت: {created_at}")
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=discount_detail_keyboard(code_str))
        bot.answer_callback_query(call.id)
        return

    if data.startswith("admin_discount_delete_"):
        code = data.split("_", 3)[-1]
        delete_discount_code(code)
        notify_admin(f"❌ کد تخفیف {code} حذف شد.")
        bot.edit_message_text(f"✅ <b>کد {code} با موفقیت حذف شد.</b>", call.message.chat.id, call.message.message_id, reply_markup=admin_discounts_keyboard())
        bot.answer_callback_query(call.id)
        return

    if data == "admin_orders":
        orders = get_pending_orders()
        if not orders:
            bot.edit_message_text("✅ <b>هیچ سفارش در انتظاری نیست.</b>", call.message.chat.id, call.message.message_id, reply_markup=admin_main_keyboard())
        else:
            bot.edit_message_text("📋 <b>سفارشات در انتظار:</b>", call.message.chat.id, call.message.message_id, reply_markup=pending_orders_keyboard(orders, 'order'))
        bot.answer_callback_query(call.id)
        return

    if data.startswith("admin_order_"):
        order_id = int(data.split("_")[-1])
        show_order_detail(call, order_id, is_test=False)
        return

    if data == "admin_tests":
        tests = get_pending_test_orders()
        if not tests:
            bot.edit_message_text("✅ <b>هیچ درخواست تستی در انتظار نیست.</b>", call.message.chat.id, call.message.message_id, reply_markup=admin_main_keyboard())
        else:
            bot.edit_message_text("🧪 <b>درخواست‌های تست:</b>", call.message.chat.id, call.message.message_id, reply_markup=pending_orders_keyboard(tests, 'test'))
        bot.answer_callback_query(call.id)
        return

    if data.startswith("admin_test_"):
        order_id = int(data.split("_")[-1])
        show_order_detail(call, order_id, is_test=True)
        return

    if data.startswith("admin_send_test_"):
        order_id = int(data.split("_")[-1])
        msg = bot.send_message(MASTER_ADMIN_ID, f"🧪 <b>لطفاً لینک سابسکرایبشن اکانت تست #{order_id} را وارد کنید:</b>")
        bot.register_next_step_handler(msg, lambda m: get_test_config(m, order_id, 'sub'))
        bot.answer_callback_query(call.id)
        return

    if data.startswith("admin_verify_"):
        parts = data.split("_")
        prefix = parts[2]
        order_id = int(parts[3])
        is_test = (prefix == 'test')
        msg = bot.send_message(MASTER_ADMIN_ID, f"📝 <b>لطفاً لینک سابسکرایبشن {'تست' if is_test else 'سفارش'} #{order_id} را وارد کنید:</b>")
        bot.register_next_step_handler(msg, lambda m: get_config(m, order_id, is_test, 'sub'))
        bot.answer_callback_query(call.id)
        return

    if data.startswith("admin_reject_"):
        parts = data.split("_")
        prefix = parts[2]
        order_id = int(parts[3])
        reject_order(order_id)
        order = get_order(order_id)
        if order:
            bot.send_message(order[1], f"❌ <b>{'تست' if order[9]==1 else 'سفارش'} #{order_id} رد شد.</b>\nلطفاً با پشتیبانی تماس بگیرید.")
        notify_admin(f"❌ <b>{'تست' if order[9]==1 else 'سفارش'} #{order_id} رد شد.</b>")
        bot.edit_message_text(f"❌ <b>رد شد.</b>", call.message.chat.id, call.message.message_id, reply_markup=admin_main_keyboard())
        bot.answer_callback_query(call.id)
        return

    if data == "admin_recharges":
        recharges = get_pending_recharges()
        if not recharges:
            bot.edit_message_text("✅ <b>هیچ درخواستی در انتظار نیست.</b>", call.message.chat.id, call.message.message_id, reply_markup=admin_main_keyboard())
        else:
            bot.edit_message_text("💰 <b>درخواست‌های افزایش موجودی:</b>", call.message.chat.id, call.message.message_id, reply_markup=pending_recharges_keyboard(recharges))
        bot.answer_callback_query(call.id)
        return

    if data.startswith("admin_recharge_"):
        req_id = int(data.split("_")[-1])
        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT * FROM recharge_requests WHERE id = ?', (req_id,))
        req = c.fetchone()
        conn.close()
        if not req:
            bot.answer_callback_query(call.id, "❌ درخواست یافت نشد!", show_alert=True)
            return
        text = f"💰 <b>درخواست #{req_id}</b>\n👤 کاربر: {req[1]}\n💵 مبلغ: {req[2]:,} تومان"
        bot.send_photo(MASTER_ADMIN_ID, req[3], caption=text, parse_mode="HTML", reply_markup=recharge_action_keyboard(req_id))
        bot.delete_message(call.message.chat.id, call.message.message_id)
        bot.answer_callback_query(call.id)
        return

    if data.startswith("admin_approve_recharge_"):
        req_id = int(data.split("_")[-1])
        uid, amt = approve_recharge(req_id)
        if uid:
            bot.send_message(uid, f"💰 <b>موجودی کیف پول شما {amt:,} تومان افزایش یافت.</b>\nموجودی جدید: {get_user_balance(uid):,} تومان")
            notify_admin(f"✅ <b>درخواست #{req_id} تایید شد.</b>\nکاربر {uid} - مبلغ {amt:,} تومان")
            bot.edit_message_text(f"✅ <b>تایید شد.</b>", call.message.chat.id, call.message.message_id, reply_markup=admin_main_keyboard())
        else:
            bot.answer_callback_query(call.id, "❌ خطا!", show_alert=True)
        return

    if data.startswith("admin_reject_recharge_"):
        req_id = int(data.split("_")[-1])
        conn = get_db()
        c = conn.cursor()
        c.execute('UPDATE recharge_requests SET status = "rejected" WHERE id = ?', (req_id,))
        conn.commit()
        conn.close()
        bot.edit_message_text(f"❌ <b>درخواست #{req_id} رد شد.</b>", call.message.chat.id, call.message.message_id, reply_markup=admin_main_keyboard())
        notify_admin(f"❌ <b>درخواست #{req_id} رد شد.</b>")
        bot.answer_callback_query(call.id)
        return

    if data == "admin_users":
        users = get_all_users_list()
        bot.edit_message_text("👥 <b>لیست کاربران:</b>", call.message.chat.id, call.message.message_id, reply_markup=users_list_keyboard(users, 0))
        bot.answer_callback_query(call.id)
        return

    if data.startswith("admin_users_page_"):
        page = int(data.split("_")[-1])
        users = get_all_users_list()
        bot.edit_message_text("👥 <b>لیست کاربران:</b>", call.message.chat.id, call.message.message_id, reply_markup=users_list_keyboard(users, page))
        bot.answer_callback_query(call.id)
        return

    if data.startswith("admin_user_"):
        target_id = int(data.split("_")[-1])
        users = get_all_users_list()
        user_data = next((u for u in users if u[0] == target_id), None)
        if user_data:
            uid, username, fname, balance, blocked = user_data
            status = "🚫 مسدود" if blocked else "✅ فعال"
            text = (f"👤 <b>اطلاعات کاربر</b>\n"
                    f"🆔 {uid}\n"
                    f"👤 نام: {fname or 'نامشخص'}\n"
                    f"📛 یوزرنیم: @{username or 'ندارد'}\n"
                    f"💰 موجودی: {balance:,} تومان\n"
                    f"⚡ وضعیت: {status}")
            bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=user_manage_keyboard(target_id))
        else:
            bot.answer_callback_query(call.id, "❌ کاربر یافت نشد!", show_alert=True)
        return

    if data.startswith("admin_block_"):
        target_id = int(data.split("_")[-1])
        block_user(target_id)
        bot.answer_callback_query(call.id, f"🚫 کاربر {target_id} مسدود شد.")
        bot.send_message(target_id, "⛔ <b>حساب شما مسدود شد.</b>")
        notify_admin(f"🚫 <b>کاربر {target_id} مسدود شد.</b>")
        users = get_all_users_list()
        bot.edit_message_text("👥 <b>لیست کاربران:</b>", call.message.chat.id, call.message.message_id, reply_markup=users_list_keyboard(users, 0))
        return

    if data.startswith("admin_unblock_"):
        target_id = int(data.split("_")[-1])
        unblock_user(target_id)
        bot.answer_callback_query(call.id, f"✅ مسدودی کاربر {target_id} رفع شد.")
        bot.send_message(target_id, "🔓 <b>حساب شما رفع مسدود شد.</b>")
        notify_admin(f"✅ <b>رفع مسدودی کاربر {target_id}</b>")
        users = get_all_users_list()
        bot.edit_message_text("👥 <b>لیست کاربران:</b>", call.message.chat.id, call.message.message_id, reply_markup=users_list_keyboard(users, 0))
        return

    if data.startswith("admin_balance_"):
        target_id = int(data.split("_")[-1])
        msg = bot.send_message(MASTER_ADMIN_ID, f"💰 <b>مقدار تغییر موجودی برای کاربر {target_id} را وارد کنید (مثبت یا منفی):</b>")
        bot.register_next_step_handler(msg, lambda m: change_user_balance(m, target_id))
        bot.answer_callback_query(call.id)
        return

    if data.startswith("admin_msg_"):
        target_id = int(data.split("_")[-1])
        msg = bot.send_message(MASTER_ADMIN_ID, f"📨 <b>متن پیام برای کاربر {target_id} را وارد کنید:</b>")
        bot.register_next_step_handler(msg, lambda m: send_message_to_user(m, target_id))
        bot.answer_callback_query(call.id)
        return

    if data == "admin_change_balance":
        msg = bot.send_message(MASTER_ADMIN_ID, "💰 <b>آیدی عددی کاربر و مقدار تغییر را وارد کنید (مثال: 123456 +50000):</b>")
        bot.register_next_step_handler(msg, admin_change_balance_manual)
        bot.answer_callback_query(call.id)
        return

    if data == "admin_messages":
        msgs = get_unreplied_messages()
        if not msgs:
            bot.edit_message_text("📭 <b>هیچ پیام پاسخ‌داده‌نشده‌ای نیست.</b>", call.message.chat.id, call.message.message_id, reply_markup=admin_main_keyboard())
        else:
            bot.edit_message_text("📨 <b>پیام‌های دریافتی:</b>", call.message.chat.id, call.message.message_id, reply_markup=unreplied_messages_keyboard(msgs))
        bot.answer_callback_query(call.id)
        return

    if data.startswith("admin_reply_msg_"):
        msg_id = int(data.split("_")[-1])
        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT user_id, message_text, message_type, file_id, caption FROM user_messages WHERE id = ?', (msg_id,))
        row = c.fetchone()
        conn.close()
        if row:
            uid, txt, mtype, fid, cap = row
            if mtype == "text":
                bot.send_message(MASTER_ADMIN_ID, f"📩 <b>پیام از کاربر {uid}:</b>\n\n{txt}", reply_markup=reply_message_keyboard(uid, msg_id))
            elif mtype == "photo":
                bot.send_photo(MASTER_ADMIN_ID, fid, caption=f"📩 <b>پیام از کاربر {uid}:</b>\n\n{txt}", reply_markup=reply_message_keyboard(uid, msg_id))
            elif mtype == "document":
                bot.send_document(MASTER_ADMIN_ID, fid, caption=f"📩 <b>پیام از کاربر {uid}:</b>\n\n{txt}", reply_markup=reply_message_keyboard(uid, msg_id))
            elif mtype == "video":
                bot.send_video(MASTER_ADMIN_ID, fid, caption=f"📩 <b>پیام از کاربر {uid}:</b>\n\n{txt}", reply_markup=reply_message_keyboard(uid, msg_id))
            elif mtype == "voice":
                bot.send_voice(MASTER_ADMIN_ID, fid, caption=f"📩 <b>پیام از کاربر {uid}:</b>\n\n{txt}", reply_markup=reply_message_keyboard(uid, msg_id))
            elif mtype == "sticker":
                bot.send_sticker(MASTER_ADMIN_ID, fid, reply_markup=reply_message_keyboard(uid, msg_id))
            bot.delete_message(call.message.chat.id, call.message.message_id)
        else:
            bot.answer_callback_query(call.id, "❌ پیام یافت نشد!", show_alert=True)
        return

    if data.startswith("admin_reply_send_"):
        parts = data.split("_")
        target_id = int(parts[3])
        msg_id = int(parts[4])
        msg = bot.send_message(MASTER_ADMIN_ID, f"✏️ <b>پاسخ خود را برای کاربر {target_id} ارسال کنید (متن، عکس، فایل):</b>")
        bot.register_next_step_handler(msg, lambda m: send_reply_to_user(m, target_id, msg_id))
        bot.answer_callback_query(call.id)
        return

    if data == "admin_broadcast":
        msg = bot.send_message(MASTER_ADMIN_ID, "📢 <b>متن پیام همگانی را ارسال کنید:</b>")
        bot.register_next_step_handler(msg, admin_broadcast_message)
        bot.answer_callback_query(call.id)
        return

    if data == "admin_stats":
        total_users = get_all_users()
        sales_count, revenue = get_total_sales()
        pending_orders = len(get_pending_orders())
        pending_tests = len(get_pending_test_orders())
        text = (f"📊 <b>آمار ربات ITGVPN</b>\n\n"
                f"👥 کل کاربران: {total_users}\n"
                f"✅ سفارشات موفق: {sales_count}\n"
                f"💰 کل فروش: {revenue:,} تومان\n"
                f"⏳ سفارشات در انتظار: {pending_orders}\n"
                f"🧪 تست‌های در انتظار: {pending_tests}")
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=admin_main_keyboard())
        bot.answer_callback_query(call.id)
        return

    # ---------- مدیریت قیمت‌ها ----------
    if data == "admin_prices":
        bot.edit_message_text("💰 <b>مدیریت قیمت‌ها</b>\n\nلطفاً یکی از گزینه‌های زیر را انتخاب کنید:", 
                              call.message.chat.id, call.message.message_id, reply_markup=admin_prices_keyboard())
        bot.answer_callback_query(call.id)
        return

    if data == "admin_prices_volume":
        bot.edit_message_text("📦 <b>قیمت پلن‌های حجمی</b>\n\nروی هر گزینه کلیک کنید تا قیمت آن را ویرایش کنید:",
                              call.message.chat.id, call.message.message_id, reply_markup=admin_volume_prices_keyboard())
        bot.answer_callback_query(call.id)
        return

    if data == "admin_prices_unlimited":
        bot.edit_message_text("♾️ <b>قیمت پلن‌های نامحدود</b>\n\nروی هر گزینه کلیک کنید تا قیمت آن را ویرایش کنید:",
                              call.message.chat.id, call.message.message_id, reply_markup=admin_unlimited_prices_keyboard())
        bot.answer_callback_query(call.id)
        return

    if data == "admin_prices_per_gb":
        msg = bot.send_message(MASTER_ADMIN_ID, "📊 <b>قیمت هر گیگابایت برای حجم دلخواه</b>\n\nقیمت جدید را به تومان وارد کنید:")
        bot.register_next_step_handler(msg, lambda m: edit_price(m, 'custom_price_per_gb', 'قیمت هر گیگ (دلخواه)'))
        bot.answer_callback_query(call.id)
        return

    if data.startswith("admin_price_edit_volume_"):
        gb = int(data.split("_")[-1])
        key = f'price_{gb}g'
        msg = bot.send_message(MASTER_ADMIN_ID, f"📦 <b>ویرایش قیمت {gb} گیگابایت</b>\n\nقیمت جدید را به تومان وارد کنید:")
        bot.register_next_step_handler(msg, lambda m: edit_price(m, key, f'قیمت {gb} GB'))
        bot.answer_callback_query(call.id)
        return

    if data.startswith("admin_price_edit_unlimited_"):
        period = data.split("_")[-1]
        key = f'unlimited_{period}'
        if period == 'single':
            period_name = "تک کاربره"
        elif period == 'double':
            period_name = "دو کاربره"
        elif period == 'triple':
            period_name = "سه کاربره"
        else:
            period_name = period
        msg = bot.send_message(MASTER_ADMIN_ID, f"♾️ <b>ویرایش قیمت پنل نامحدود {period_name}</b>\n\nقیمت جدید را به تومان وارد کنید:")
        bot.register_next_step_handler(msg, lambda m: edit_price(m, key, f'پنل نامحدود {period_name}'))
        bot.answer_callback_query(call.id)
        return

    # ---------- جستجوی سفارش با کد پیگیری ----------
    if data == "admin_search_order":
        msg = bot.send_message(MASTER_ADMIN_ID, "🔍 <b>کد پیگیری سفارش را وارد کنید:</b>")
        bot.register_next_step_handler(msg, admin_search_order_by_tracking)
        bot.answer_callback_query(call.id)
        return

    if data == "admin_back_main":
        bot.edit_message_text("🔧 <b>منوی مدیریت:</b>", call.message.chat.id, call.message.message_id, reply_markup=admin_main_keyboard())
        bot.answer_callback_query(call.id)
        return

    if data == "admin_exit":
        bot.edit_message_text("🚪 <b>خروج از پنل مدیریت.</b>", call.message.chat.id, call.message.message_id, reply_markup=get_main_reply_keyboard())
        cmd_start(call.message)
        bot.answer_callback_query(call.id)
        return

    if data == "apps_back":
        show_apps_inline(call)
        return

    if data == "apps_android":
        bot.edit_message_text("📱 <b>انتخاب برنامه برای اندروید:</b>", call.message.chat.id, call.message.message_id, reply_markup=apps_android_keyboard())
        bot.answer_callback_query(call.id)
        return

    if data == "apps_ios":
        bot.edit_message_text("🍏 <b>انتخاب برنامه برای آیفون:</b>", call.message.chat.id, call.message.message_id, reply_markup=apps_ios_keyboard())
        bot.answer_callback_query(call.id)
        return

    if data.startswith("app_android_"):
        app = data.split("_")[2]
        if app == "http":
            link = "https://play.google.com/store/apps/details?id=com.evozi.injector"
            app_name = "HTTP Injector"
            tutorial = ("📘 <b>آموزش اضافه کردن کانفیگ در HTTP Injector (اندروید):</b>\n\n"
                        "1️⃣ برنامه را از لینک زیر نصب کنید.\n"
                        "2️⃣ کانفیگ دریافتی (لینک ساب یا کد) را کپی کنید.\n"
                        "3️⃣ در برنامه، روی گزینه «Import» یا «➕» بزنید.\n"
                        "4️⃣ لینک ساب را در قسمت «URL» قرار دهید و ذخیره کنید.\n"
                        "5️⃣ سپس روی دکمه «Connect» بزنید تا اتصال برقرار شود.\n\n"
                        "✅ در صورت نیاز، می‌توانید از کد کانفیگ نیز استفاده کنید (بخش «Manual Config»).")
        else:
            link = "https://play.google.com/store/apps/details?id=com.napsternetlabs.napsternetv"
            app_name = "Npv Tunnel"
            tutorial = ("📘 <b>آموزش اضافه کردن کانفیگ در Npv Tunnel (اندروید):</b>\n\n"
                        "1️⃣ برنامه را از لینک زیر نصب کنید.\n"
                        "2️⃣ کانفیگ دریافتی (لینک ساب یا کد) را کپی کنید.\n"
                        "3️⃣ در برنامه، روی آیکون «➕» یا «Import» بزنید.\n"
                        "4️⃣ گزینه «Subscription» را انتخاب کنید و لینک ساب را وارد کنید.\n"
                        "5️⃣ پس از ذخیره، روی کانفیگ ضربه بزنید و «Connect» را بزنید.\n\n"
                        "✅ همچنین می‌توانید کد کانفیگ را به صورت دستی در بخش «Manual» وارد کنید.")
        text = f"📱 <b>{app_name} برای اندروید</b>\n\n🔗 لینک دانلود:\n{link}\n\n{tutorial}"
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="HTML", reply_markup=apps_android_keyboard())
        bot.answer_callback_query(call.id)
        return

    if data.startswith("app_ios_"):
        app = data.split("_")[2]
        if app == "http":
            link = "https://apps.apple.com/us/app/http-injector/id1659992827"
            app_name = "HTTP Injector"
            tutorial = ("📘 <b>آموزش اضافه کردن کانفیگ در HTTP Injector (آیفون):</b>\n\n"
                        "1️⃣ برنامه را از اپ استور نصب کنید.\n"
                        "2️⃣ کانفیگ دریافتی (لینک ساب یا کد) را کپی کنید.\n"
                        "3️⃣ در برنامه، به بخش «Subscriptions» بروید.\n"
                        "4️⃣ گزینه «Add Subscription» را بزنید و لینک ساب را وارد کنید.\n"
                        "5️⃣ ذخیره کنید و سپس از طریق «Connect» اتصال را برقرار کنید.\n\n"
                        "✅ در صورت استفاده از کد کانفیگ، از بخش «Manual Config» استفاده نمایید.")
        else:
            link = "https://apps.apple.com/us/app/npv-tunnel/id1629465476"
            app_name = "Npv Tunnel"
            tutorial = ("📘 <b>آموزش اضافه کردن کانفیگ در Npv Tunnel (آیفون):</b>\n\n"
                        "1️⃣ برنامه را از اپ استور نصب کنید.\n"
                        "2️⃣ کانفیگ دریافتی (لینک ساب یا کد) را کپی کنید.\n"
                        "3️⃣ در برنامه، روی «➕» بزنید و «Subscription» را انتخاب کنید.\n"
                        "4️⃣ لینک ساب را در قسمت «URL» وارد کرده و ذخیره کنید.\n"
                        "5️⃣ سپس روی کانفیگ ضربه بزنید و «Connect» را بزنید.\n\n"
                        "✅ همچنین کد کانفیگ را می‌توانید به صورت دستی در بخش «Manual» وارد کنید.")
        text = f"🍏 <b>{app_name} برای آیفون</b>\n\n🔗 لینک دانلود:\n{link}\n\n{tutorial}"
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="HTML", reply_markup=apps_ios_keyboard())
        bot.answer_callback_query(call.id)
        return

    bot.answer_callback_query(call.id, "❌ دستور نامعتبر!")

# ---------- توابع نمایش درون‌خطی ----------
def show_pricing_inline(call):
    text = "📊 <b>تعرفه‌های ITGVPN</b>\n\n"
    text += "🔹 <b>پکیج‌های عادی (مولتی لوکیشن)</b>\n"
    for gb in DEFAULT_VOLUMES:
        price = PRICES[gb]
        text += f"💎 {gb} GB ➖ {price:,} تومان\n"
    text += "\n💰 <b>پکیج‌های اقتصادی (حجم بالا)</b>\n"
    for gb in ECONOMICAL_VOLUMES:
        price = PRICES[gb]
        text += f"💎 {gb} GB ➖ {price:,} تومان\n"
    text += f"\n✨ حجم دلخواه: هر گیگ {CUSTOM_PRICE_PER_GB:,} تومان"
    text += "\n\n♾️ <b>پنل نامحدود (حجم و کاربر نامحدود):</b>\n"
    text += f"📦 تک کاربره ➖ {UNLIMITED_PRICES['single']:,} تومان\n"
    text += f"📦 دو کاربره ➖ {UNLIMITED_PRICES['double']:,} تومان\n"
    text += f"📦 سه کاربره ➖ {UNLIMITED_PRICES['triple']:,} تومان"
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=main_menu_keyboard())
    bot.answer_callback_query(call.id)

def show_wallet_inline(call):
    user_id = call.from_user.id
    balance = get_user_balance(user_id)
    purchase_count = get_user_purchase_count(user_id)
    user_info = bot.get_chat(user_id)
    username = user_info.username or "ندارد"
    first_name = user_info.first_name or "کاربر"
    text = (f"💰 <b>کیف پول شما</b>\n\n"
            f"👤 <b>نام:</b> {first_name}\n"
            f"🆔 <b>آیدی عددی:</b> <code>{user_id}</code>\n"
            f"📛 <b>یوزرنیم:</b> @{username}\n"
            f"💵 <b>موجودی:</b> {balance:,} تومان\n"
            f"📊 <b>تعداد خرید:</b> {purchase_count} مورد\n"
            f"🕐 <b>آخرین بروزرسانی:</b> {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
            "برای افزایش موجودی، مبلغ را به کارت زیر واریز کرده و رسید را ارسال کنید:\n"
            f"<code>{CARD_NUMBER}</code>\n\n"
            "⚠️ <b>توجه:</b> فقط کارت به کارت قابل قبول است. در صورت اشتباه در واریز، مسئولیت با خود شماست.")
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="HTML", reply_markup=wallet_keyboard())
    bot.answer_callback_query(call.id)

def show_apps_inline(call):
    text = "📱 <b>انتخاب سیستمعامل:</b>\n\nلطفاً سیستمعامل خود را انتخاب کنید تا برنامه‌های مناسب را مشاهده کنید."
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=apps_platform_keyboard())
    bot.answer_callback_query(call.id)

def show_partner_inline(call):
    text = ("🤝 <b>پنل همکاری ITGVPN</b>\n\n"
            "🔹 <b>قیمت هر گیگ برای همکاران:</b> ۴,۰۰۰ تومان\n"
            "🔹 <b>ربات اختصاصی فروش</b> (مشابه همین ربات)\n"
            "🔹 <b>پنل مدیریت کانفیگ</b> با قابلیت ساخت نامحدود کانفیگ\n"
            "🔹 <b>هزینه پنل ماهانه:</b> ۱,۲۸۰,۰۰۰ تومان\n\n"
            "📌 برای ثبت‌نام و دریافت اطلاعات بیشتر، با ادمین تماس بگیرید:\n"
            f"{SUPPORT_LINK}")
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=main_menu_keyboard())
    bot.answer_callback_query(call.id)

def show_order_detail(call, order_id, is_test):
    show_order_detail_for_admin(call.message.chat.id, order_id, is_test, edit_mode=False)
    bot.delete_message(call.message.chat.id, call.message.message_id)
    bot.answer_callback_query(call.id)

def show_order_detail_for_admin(chat_id, order_id, is_test, edit_mode=False):
    order = get_order(order_id)
    if not order:
        bot.send_message(chat_id, "❌ سفارش یافت نشد!", reply_markup=admin_main_keyboard())
        return
    status_text = "⏳ در انتظار" if order[5]=='pending' else "🖼️ منتظر رسید"
    label = "🧪 تست" if is_test else "🛒 سفارش"
    if len(order) > 12 and order[12] == 1:
        period = order[13]
        if period == 'single':
            plan = "تک کاربره"
        elif period == 'double':
            plan = "دو کاربره"
        elif period == 'triple':
            plan = "سه کاربره"
        else:
            plan = period
        product = f"پنل نامحدود ({plan})"
    else:
        product = f"{order[2]} GB"
    final_price = order[15] if len(order) > 15 and order[15] else order[3]
    tracking = order[16] if len(order) > 16 else "ندارد"
    text = (f"{label} #{order_id}\n"
            f"👤 کاربر: {order[1]}\n"
            f"📦 محصول: {product}\n"
            f"💰 مبلغ نهایی: {final_price:,} تومان\n"
            f"🔑 کد پیگیری: <code>{tracking}</code>\n"
            f"⚡ وضعیت: {status_text}")
    if len(order) > 10 and order[10] == 1:
        text += f"\n📛 نام اکانت: {order[11]}"
    if order[6]:
        bot.send_photo(chat_id, order[6], caption=text, parse_mode="HTML", reply_markup=order_action_keyboard(order_id, is_test))
    else:
        bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=order_action_keyboard(order_id, is_test))

# ---------- توابع کمکی برای دریافت کانفیگ ----------
def get_config(message, order_id, is_test, step):
    if step == 'sub':
        sub_link = message.text.strip()
        if not sub_link.startswith('http'):
            bot.send_message(MASTER_ADMIN_ID, "❌ لینک نامعتبر! لطفاً یک لینک معتبر وارد کنید.")
            return
        temp_actions[MASTER_ADMIN_ID] = {'order_id': order_id, 'is_test': is_test, 'sub': sub_link}
        msg = bot.send_message(MASTER_ADMIN_ID, "📝 <b>لطفاً کد کانفیگ را وارد کنید:</b>")
        bot.register_next_step_handler(msg, lambda m: get_config(m, order_id, is_test, 'code'))
    elif step == 'code':
        config_code = message.text.strip()
        data = temp_actions.get(MASTER_ADMIN_ID, {})
        if not data:
            bot.send_message(MASTER_ADMIN_ID, "❌ خطا! دوباره تلاش کنید.")
            return
        order_id = data['order_id']
        is_test = data['is_test']
        sub_link = data['sub']
        config_full = f"{sub_link}\n{config_code}"
        verify_order(order_id, config_full)
        order = get_order(order_id)
        user_id = order[1]
        user_info = bot.get_chat(user_id)
        username = user_info.username or f"کاربر{user_id}"
        first_name = user_info.first_name or "کاربر"
        if is_test:
            expiry = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d %H:%M")
            delivery_text = (f"🧪 <b>اکانت تست شما ساخته شد.</b>\n\n"
                             f"👤 <b>نام کاربری:</b> {first_name} (@{username})\n"
                             f"📦 <b>حجم:</b> ۱۰۰ مگابایت\n"
                             f"⏳ <b>اعتبار:</b> تا {expiry}\n\n"
                             f"🔗 <b>لینک سابسکرایبشن:</b>\n<code>{sub_link}</code>\n\n"
                             f"🔰 <b>کد کانفیگ:</b>\n<code>{config_code}</code>\n\n"
                             f"✅ <b>موفق باشید</b>")
        else:
            if len(order) > 12 and order[12] == 1:
                period = order[13]
                if period == 'single':
                    plan = "تک کاربره"
                elif period == 'double':
                    plan = "دو کاربره"
                elif period == 'triple':
                    plan = "سه کاربره"
                else:
                    plan = period
                product = f"پنل نامحدود ({plan})"
            else:
                product = f"{order[2]} GB"
            delivery_text = (f"🔑 <b>اشتراک شما با موفقیت ساخته شد.</b>\n\n"
                             f"👤 <b>نام کاربری:</b> {first_name} (@{username})\n"
                             f"📦 <b>محصول:</b> {product}\n\n"
                             f"🔗 <b>لینک سابسکرایبشن:</b>\n<code>{sub_link}</code>\n\n"
                             f"🔰 <b>کد کانفیگ:</b>\n<code>{config_code}</code>\n\n"
                             f"✅ <b>موفق باشید</b>")
        bot.send_message(user_id, delivery_text, parse_mode="HTML")
        bot.send_message(MASTER_ADMIN_ID, f"✅ <b>{'تست' if is_test else 'سفارش'} #{order_id} تایید و ارسال شد.</b>")
        if MASTER_ADMIN_ID in temp_actions:
            del temp_actions[MASTER_ADMIN_ID]

def get_test_config(message, order_id, step):
    if step == 'sub':
        sub_link = message.text.strip()
        if not sub_link.startswith('http'):
            bot.send_message(MASTER_ADMIN_ID, "❌ لینک نامعتبر!")
            return
        temp_actions[MASTER_ADMIN_ID] = {'order_id': order_id, 'sub': sub_link}
        msg = bot.send_message(MASTER_ADMIN_ID, "📝 <b>لطفاً کد کانفیگ تست را وارد کنید:</b>")
        bot.register_next_step_handler(msg, lambda m: get_test_config(m, order_id, 'code'))
    elif step == 'code':
        config_code = message.text.strip()
        data = temp_actions.get(MASTER_ADMIN_ID, {})
        if not data:
            bot.send_message(MASTER_ADMIN_ID, "❌ خطا!")
            return
        order_id = data['order_id']
        sub_link = data['sub']
        config_full = f"{sub_link}\n{config_code}"
        verify_order(order_id, config_full)
        user_id = get_order(order_id)[1]
        user_info = bot.get_chat(user_id)
        username = user_info.username or f"کاربر{user_id}"
        first_name = user_info.first_name or "کاربر"
        expiry = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d %H:%M")
        delivery_text = (f"🧪 <b>اکانت تست شما ساخته شد.</b>\n\n"
                         f"👤 <b>نام کاربری:</b> {first_name} (@{username})\n"
                         f"📦 <b>حجم:</b> ۱۰۰ مگابایت\n"
                         f"⏳ <b>اعتبار:</b> تا {expiry}\n\n"
                         f"🔗 <b>لینک سابسکرایبشن:</b>\n<code>{sub_link}</code>\n\n"
                         f"🔰 <b>کد کانفیگ:</b>\n<code>{config_code}</code>\n\n"
                         f"✅ <b>موفق باشید</b>")
        bot.send_message(user_id, delivery_text, parse_mode="HTML")
        bot.send_message(MASTER_ADMIN_ID, f"✅ <b>تست #{order_id} ارسال شد.</b>")
        if MASTER_ADMIN_ID in temp_actions:
            del temp_actions[MASTER_ADMIN_ID]

# ---------- توابع کمکی دیگر ----------
def process_discount_code(message):
    user_id = message.from_user.id
    code = message.text.strip().upper()
    if user_id not in temp_actions or temp_actions[user_id].get('action') != 'discount':
        bot.send_message(user_id, "❌ زمان اعتبارسنجی کد تمام شد. لطفاً دوباره سفارش دهید.")
        return
    order_id = temp_actions[user_id]['order_id']
    discount_row = get_discount_code(code)
    if not discount_row:
        bot.send_message(user_id, "❌ کد تخفیف نامعتبر یا منقضی شده است.")
        return
    cid, code_str, amount, max_usage, used, created_by, created_at, active = discount_row
    if used >= max_usage:
        bot.send_message(user_id, "❌ این کد تخفیف قبلاً به حداکثر تعداد استفاده رسیده است.")
        return
    order = get_order(order_id)
    if not order:
        bot.send_message(user_id, "❌ سفارش یافت نشد!")
        return
    if order[5] != 'pending':
        bot.send_message(user_id, "❌ این سفارش قابل تغییر نیست.")
        return
    price = order[3]
    final_price = price - amount
    if final_price < 0:
        final_price = 0
    # بروزرسانی سفارش
    conn = get_db()
    c = conn.cursor()
    c.execute('UPDATE orders SET discount_code = ?, discount_amount = ?, final_price = ? WHERE order_id = ?',
              (code, amount, final_price, order_id))
    conn.commit()
    conn.close()
    # افزایش مصرف کد
    use_discount_code(code)
    # ارسال پیام جدید
    order_updated = get_order(order_id)
    invoice_text = generate_invoice_text(order_updated)
    try:
        bot.edit_message_text(invoice_text, message.chat.id, message.message_id, reply_markup=payment_method_keyboard(order_id, discount_applied=True))
        bot.send_message(user_id, f"✅ کد تخفیف {code} با مبلغ {amount:,} تومان اعمال شد.")
    except Exception as e:
        logger.error(f"خطا در ویرایش پیام: {e}")
        # اگر پیام قابل ویرایش نبود، پیام جدید ارسال می‌کنیم
        bot.send_message(user_id, invoice_text, reply_markup=payment_method_keyboard(order_id, discount_applied=True))
        bot.send_message(user_id, f"✅ کد تخفیف {code} با مبلغ {amount:,} تومان اعمال شد.")
    if user_id in temp_actions:
        del temp_actions[user_id]

def admin_create_discount(message):
    try:
        parts = message.text.strip().split()
        if len(parts) < 2 or len(parts) > 3:
            raise ValueError("تعداد پارامترها نامعتبر است")
        code = parts[0].upper()
        amount = int(parts[1])
        max_usage = int(parts[2]) if len(parts) == 3 else 1
        if amount <= 0 or max_usage <= 0:
            raise ValueError("مقدار باید مثبت باشد")
    except Exception as e:
        bot.send_message(MASTER_ADMIN_ID, f"❌ فرمت نامعتبر! مثال: SAVE20 20000 5\nخطا: {e}", reply_markup=admin_discounts_keyboard())
        return
    success = create_discount_code(code, amount, max_usage, MASTER_ADMIN_ID)
    if success:
        bot.send_message(MASTER_ADMIN_ID, f"✅ کد تخفیف <code>{code}</code> با مبلغ {amount:,} تومان و {max_usage} بار استفاده ساخته شد.", reply_markup=admin_discounts_keyboard())
        notify_admin(f"🎟️ کد تخفیف جدید ساخته شد: {code} - {amount:,} تومان - {max_usage} بار")
    else:
        bot.send_message(MASTER_ADMIN_ID, "❌ کد تکراری است یا خطایی رخ داده. لطفاً از کد دیگری استفاده کنید.", reply_markup=admin_discounts_keyboard())

def edit_price(message, key, description):
    try:
        new_value = int(message.text.strip())
        if new_value <= 0:
            raise ValueError
    except:
        bot.send_message(MASTER_ADMIN_ID, "❌ عدد معتبر وارد کنید (بزرگتر از صفر).", reply_markup=admin_prices_keyboard())
        return
    update_price_key(key, new_value)
    bot.send_message(MASTER_ADMIN_ID, f"✅ <b>{description}</b> با موفقیت به {new_value:,} تومان تغییر یافت.", reply_markup=admin_prices_keyboard())
    notify_admin(f"💰 قیمت {description} به {new_value:,} تومان تغییر یافت.")

def process_custom_volume(message):
    user_id = message.from_user.id
    try:
        volume = int(message.text.strip())
        if volume <= 0:
            raise ValueError
    except:
        bot.send_message(user_id, "❌ <b>عدد معتبر وارد کنید.</b>", reply_markup=get_main_reply_keyboard())
        return
    price = volume * CUSTOM_PRICE_PER_GB
    order_id = save_order(user_id, volume, price, None, is_custom=1)
    invoice_text = generate_invoice_text(get_order(order_id))
    bot.send_message(user_id, invoice_text, reply_markup=payment_method_keyboard(order_id, discount_applied=False))

def process_balance_amount(message):
    user_id = message.from_user.id
    try:
        amount = int(message.text.strip())
        if amount <= 0:
            raise ValueError
    except:
        bot.send_message(user_id, "❌ <b>مبلغ نامعتبر.</b>", reply_markup=get_main_reply_keyboard())
        return
    bot.send_message(user_id, f"💰 <b>مبلغ {amount:,} تومان ثبت شد.</b>\nلطفاً تصویر رسید را ارسال کنید.")
    bot.register_next_step_handler(message, lambda m: save_recharge_receipt(m, amount))

def save_recharge_receipt(message, amount):
    user_id = message.from_user.id
    if message.content_type != 'photo':
        bot.send_message(user_id, "❌ <b>تصویر معتبر ارسال کنید.</b>", reply_markup=get_main_reply_keyboard())
        return
    photo_id = message.photo[-1].file_id
    req_id = add_recharge_request(user_id, amount, photo_id)
    notify_admin(f"💰 <b>درخواست افزایش موجودی #{req_id}</b>\nکاربر: {user_id}\nمبلغ: {amount:,} تومان", photo_id)
    bot.send_message(user_id, f"✅ <b>رسید دریافت شد.</b>\nدرخواست #{req_id} ثبت شد.", reply_markup=get_main_reply_keyboard())

def save_order_receipt(message, order_id, chat_id, msg_id):
    user_id = message.from_user.id
    if message.content_type != 'photo':
        bot.send_message(user_id, "❌ <b>تصویر معتبر ارسال کنید.</b>", reply_markup=get_main_reply_keyboard())
        return
    photo_id = message.photo[-1].file_id
    update_order_receipt(order_id, photo_id)
    order = get_order(order_id)
    if order:
        if len(order) > 12 and order[12] == 1:
            period = order[13]
            if period == 'single':
                plan = "تک کاربره"
            elif period == 'double':
                plan = "دو کاربره"
            elif period == 'triple':
                plan = "سه کاربره"
            else:
                plan = period
            product_name = f"پنل نامحدود ({plan})"
        else:
            product_name = f"{order[2]} GB"
        notify_admin(f"🆕 <b>سفارش #{order_id} نیاز به تایید دارد</b>\nکاربر: {user_id}\nمحصول: {product_name}\nمبلغ: {order[3]:,} تومان",
                     photo_id, reply_markup=order_action_keyboard(order_id, is_test=False))
    bot.send_message(user_id, f"✅ <b>رسید سفارش #{order_id} دریافت شد.</b>\nدر انتظار تایید ادمین.", reply_markup=get_main_reply_keyboard())
    try:
        bot.delete_message(chat_id, msg_id)
    except:
        pass

def change_user_balance(message, target_id):
    try:
        amount = int(message.text.strip())
    except:
        bot.send_message(MASTER_ADMIN_ID, "❌ مقدار نامعتبر!", reply_markup=admin_main_keyboard())
        return
    update_balance(target_id, amount)
    new_balance = get_user_balance(target_id)
    bot.send_message(MASTER_ADMIN_ID, f"✅ موجودی کاربر {target_id} به مقدار {amount:,} تومان تغییر کرد. موجودی جدید: {new_balance:,} تومان", reply_markup=admin_main_keyboard())
    bot.send_message(target_id, f"💰 <b>موجودی شما {amount:,} تومان تغییر کرد.</b>\nموجودی جدید: {new_balance:,} تومان")

def admin_change_balance_manual(message):
    try:
        parts = message.text.strip().split()
        user_id = int(parts[0])
        amount = int(parts[1])
    except:
        bot.send_message(MASTER_ADMIN_ID, "❌ فرمت نامعتبر! مثال: 123456 +50000", reply_markup=admin_main_keyboard())
        return
    update_balance(user_id, amount)
    new_balance = get_user_balance(user_id)
    bot.send_message(MASTER_ADMIN_ID, f"✅ موجودی کاربر {user_id} به مقدار {amount:,} تومان تغییر کرد. موجودی جدید: {new_balance:,} تومان", reply_markup=admin_main_keyboard())
    bot.send_message(user_id, f"💰 <b>موجودی شما {amount:,} تومان تغییر کرد.</b>\nموجودی جدید: {new_balance:,} تومان")

def send_message_to_user(message, target_id):
    text = message.text
    bot.send_message(target_id, f"📨 <b>پیام از ادمین:</b>\n\n{text}")
    bot.send_message(MASTER_ADMIN_ID, f"✅ پیام به کاربر {target_id} ارسال شد.", reply_markup=admin_main_keyboard())

def send_reply_to_user(message, target_id, msg_id):
    if message.content_type == "text":
        bot.send_message(target_id, f"📨 <b>پاسخ ادمین:</b>\n\n{message.text}")
    elif message.content_type == "photo":
        bot.send_photo(target_id, message.photo[-1].file_id, caption=f"📨 <b>پاسخ ادمین:</b>\n\n{message.caption or ''}")
    elif message.content_type == "document":
        bot.send_document(target_id, message.document.file_id, caption=f"📨 <b>پاسخ ادمین:</b>\n\n{message.caption or ''}")
    elif message.content_type == "video":
        bot.send_video(target_id, message.video.file_id, caption=f"📨 <b>پاسخ ادمین:</b>\n\n{message.caption or ''}")
    elif message.content_type == "voice":
        bot.send_voice(target_id, message.voice.file_id, caption=f"📨 پاسخ ادمین")
    else:
        bot.send_message(target_id, "📨 <b>پاسخ ادمین ارسال شد.</b>")
    mark_message_replied(msg_id)
    bot.send_message(MASTER_ADMIN_ID, f"✅ پاسخ به کاربر {target_id} ارسال شد.", reply_markup=admin_main_keyboard())

def admin_broadcast_message(message):
    text = message.text
    users = get_all_users_list()
    success = 0
    fail = 0
    for user in users:
        uid = user[0]
        try:
            bot.send_message(uid, f"📢 <b>پیام همگانی:</b>\n\n{text}")
            success += 1
        except:
            fail += 1
        time.sleep(0.05)
    bot.send_message(MASTER_ADMIN_ID, f"✅ <b>پیام همگانی ارسال شد.</b>\nموفق: {success}\nناموفق: {fail}", reply_markup=admin_main_keyboard())

def admin_search_order_by_tracking(message):
    tracking = message.text.strip().upper()
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM orders WHERE tracking_code = ?', (tracking,))
    order = c.fetchone()
    conn.close()
    if not order:
        bot.send_message(MASTER_ADMIN_ID, f"❌ سفارشی با کد پیگیری <code>{tracking}</code> یافت نشد.", reply_markup=admin_main_keyboard())
        return
    order_id = order[0]
    is_test = order[9] == 1
    show_order_detail_for_admin(message.chat.id, order_id, is_test, edit_mode=True)

# ---------- اجرای ربات ----------
if __name__ == "__main__":
    init_db()
    logger.info("ربات ITGVPN راه‌اندازی شد.")
    try:
        bot.send_message(MASTER_ADMIN_ID, "🤖 ربات ITGVPN راه‌اندازی شد.\nلطفاً ربات را به کانال @ITGVPN1 به عنوان ادمین اضافه کنید.")
    except Exception as e:
        logger.error(f"عدم ارسال پیام راه‌اندازی به ادمین: {e}")
    while True:
        try:
            bot.infinity_polling(timeout=60, long_polling_timeout=60)
        except Exception as e:
            logger.error(f"خطا: {e}")
            time.sleep(15)