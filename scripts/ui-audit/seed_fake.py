# FAKE data for the UI audit — runs ONLY inside the isolated ui-audit stack
# (scripts/ui-audit/stack.sh, settings `config.settings.test`, whose guard
# refuses any DB other than `test-db`). Piped into `manage.py shell`.
# Accounts (fake, test stack only):
#   customer  audit-user   / audit-pass-123
#   staff     audit-admin  / audit-pass-123   (superadmin)
import io
import random
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import connection
from django.utils import timezone

assert settings.DATABASES["default"]["HOST"] == "test-db", "fake data only in the isolated stack"
assert connection.settings_dict["HOST"] == "test-db"

from PIL import Image, ImageDraw  # noqa: E402

from apps.accounts.deletion import delete_user  # noqa: E402
from apps.accounts.models import Staff, User  # noqa: E402
from apps.notifications.models import Notification, NotificationDelivery  # noqa: E402
from apps.ops.models import BackupLog, HealthCheck, ResourceStat  # noqa: E402
from apps.orders.models import Order  # noqa: E402
from apps.panel.models import Panel, Service  # noqa: E402
from apps.payments_sms.models import BankCard, Payment, SmsAppDevice, SmsMessage, SmsSource  # noqa: E402
from apps.plans.models import Plan  # noqa: E402

rnd = random.Random(7)
now = timezone.now()
GB = 1024 ** 3
PW = "audit-pass-123"


def ago(**kw):
    return now - timedelta(**kw)


def receipt_png(n, amount):
    img = Image.new("RGB", (540, 860), (246, 248, 251))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 540, 120], fill=(20, 100, 186))
    d.text((30, 45), f"BANK RECEIPT #{n}", fill=(255, 255, 255))
    for i, line in enumerate(["Transfer successful", f"Amount: {amount:,} IRR", "From: 6037-****-****-1234",
                              "To: 6219-****-****-5678", f"Ref: {100000 + n * 37}", "2026/09/26 14:3{n % 10}"]):
        d.text((30, 170 + i * 60), line, fill=(11, 18, 32))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return ContentFile(buf.getvalue(), name=f"receipt-{n}.png")


# ---- staff ----
admin, _ = Staff.objects.get_or_create(username="audit-admin", defaults={"is_superadmin": True})
admin.is_superadmin = True
admin.set_password(PW)
admin.save()

# ---- panels ----
panels = []
for name, host in [("Germany-1", "panel-de.invalid"), ("Finland-2", "panel-fi.invalid"), ("Netherlands-3", "panel-nl.invalid")]:
    p, _ = Panel.objects.get_or_create(name=name, defaults={
        "base_url": f"https://{host}", "admin_username": "fake", "admin_password_enc": "fake-not-a-secret",
        "subscription_base_url": f"https://sub.{host}", "default_group_ids": [1]})
    panels.append(p)

# ---- plans ----
plans = []
for i, (fa, en, cat_fa, cat_en, gb, days, dev, price, disc) in enumerate([
    ("اقتصادی ۳۰", "Economy 30", "ماهانه", "Monthly", 30, 30, 2, 95000, 0),
    ("استاندارد ۶۰", "Standard 60", "ماهانه", "Monthly", 60, 30, 3, 165000, 10),
    ("نامحدود ماهانه", "Unlimited monthly", "ماهانه", "Monthly", None, 30, 2, 240000, 0),
    ("سه‌ماهه ۱۵۰", "Quarterly 150", "سه‌ماهه", "Quarterly", 150, 90, 4, 420000, 15),
]):
    p, _ = Plan.objects.get_or_create(name_fa=fa.replace("۳", "3").replace("۶", "6").replace("۱", "1").replace("۵", "5").replace("۰", "0"), defaults={
        "name_en": en, "category_fa": cat_fa, "category_en": cat_en, "type": "fixed",
        "desc_fa": "مناسب استفادهٔ روزمره، استریم و شبکه‌های اجتماعی با سرعت پایدار.",
        "desc_en": "Everyday browsing, streaming and social apps at a steady speed.",
        "data_limit": gb * GB if gb else None, "duration_days": days, "device_limit": dev,
        "price": Decimal(price), "discount_percent": Decimal(disc), "sort_order": i, "panel": panels[0]})
    plans.append(p)
custom, _ = Plan.objects.get_or_create(name_fa="حجم دلخواه", defaults={
    "name_en": "Custom volume", "category_fa": "دلخواه", "category_en": "Custom", "type": "custom_volume",
    "desc_fa": "حجم را خودتان انتخاب کنید.", "desc_en": "Pick your own volume.", "duration_days": 30,
    "min_gb": 10, "max_gb": 200, "price": Decimal(20000), "price_per_gb": Decimal(2900), "sort_order": 9,
    "panel": panels[0]})

# ---- bank cards / sms ----
cards = []
for num, holder, bank in [("6037991234567890", "پویا کاظمی", "ملی"), ("6219861234567812", "سارا احمدی", "سامان"),
                          ("5022291234567843", "علی رضایی", "پاسارگاد")]:
    c, _ = BankCard.objects.get_or_create(card_number=num, defaults={"holder_name": holder, "bank_name": bank})
    cards.append(c)
src, _ = SmsSource.objects.get_or_create(phone_number="+98700011", defaults={"description": "Bank SMS line"})
dev, _ = SmsAppDevice.objects.get_or_create(name="Galaxy A54 (operator)")
SmsAppDevice.objects.get_or_create(name="iPhone 13 Shortcut")

# ---- customers ----
def mk_user(username, **kw):
    u, created = User.objects.get_or_create(username=username, defaults=kw)
    if created:
        u.set_password(PW)
        u.terms_accepted_at = now
        u.save()
    return u


me = mk_user("audit-user", name="پویا تستی", phone="09120000001", email="audit-user@example.test", email_verified=True)
FIRST = ["علی", "سارا", "رضا", "مریم", "حسین", "نگار", "امیر", "زهرا", "مهدی", "لیلا", "کاوه", "نازنین"]
LAST = ["احمدی", "رضایی", "کریمی", "موسوی", "حسینی", "جعفری", "صادقی", "رحیمی"]
others = []
for i in range(34):
    bot = i % 3 == 0
    u = mk_user(f"tg_{5100200 + i}" if bot else f"user{i:02d}",
                name=f"{rnd.choice(FIRST)} {rnd.choice(LAST)}", phone=f"0912{1000000 + i * 7331:07d}",
                source="bot" if bot else "site", telegram_id=(5100200 + i) if bot else None,
                telegram_username=f"tguser{i}" if bot else None, is_active=(i % 11 != 5))
    others.append(u)
User.objects.filter(pk__in=[u.pk for u in others]).update(created_at=ago(days=40))
for k, u in enumerate(others):
    User.objects.filter(pk=u.pk).update(created_at=ago(days=rnd.randint(0, 60), hours=k))

# ---- services ----
def mk_svc(user, uname, status, *, used_gb, limit_gb, expire_days, plan, panel=None, online=True):
    s, _ = Service.objects.get_or_create(user=user, panel_username=uname, defaults={
        "panel": panel or panels[0], "status": status, "current_plan": plan,
        "subscription_url": f"https://sub.panel-de.invalid/sub/{uname}-{rnd.randint(10**11, 10**12)}",
        "data_limit": int(limit_gb * GB) if limit_gb else 0, "data_used": int(used_gb * GB),
        "expire_at": (now + timedelta(days=expire_days)) if expire_days is not None else None,
        "on_hold_duration": 30 if status == "on_hold" else None,
        "online_at": ago(minutes=3) if online else ago(days=4), "last_synced_at": ago(minutes=2),
        "device_limit": plan.device_limit, "expire_strategy": "on_hold" if status == "on_hold" else "fixed_date"})
    return s


my_active = mk_svc(me, "pouya_main", "active", used_gb=12.4, limit_gb=60, expire_days=18, plan=plans[1])
my_hold = mk_svc(me, "pouya_phone", "on_hold", used_gb=0, limit_gb=30, expire_days=None, plan=plans[0], online=False)
my_exp = mk_svc(me, "pouya_old", "expired", used_gb=29.8, limit_gb=30, expire_days=-6, plan=plans[0], online=False)
my_lim = mk_svc(me, "pouya_tv", "limited", used_gb=150, limit_gb=150, expire_days=41, plan=plans[3])
svcs = [my_active, my_hold, my_exp, my_lim]
STATES = ["active"] * 6 + ["on_hold", "expired", "limited", "disabled"]
for i, u in enumerate(others[:26]):
    st = STATES[i % len(STATES)]
    plan = plans[i % 4]
    lim = (plan.data_limit or 0) / GB
    svcs.append(mk_svc(u, f"{u.username.replace('tg_', 'tg')}_{i}", st, used_gb=round(rnd.uniform(0, lim or 80), 1),
                       limit_gb=lim, expire_days=None if st == "on_hold" else rnd.randint(-10, 80), plan=plan,
                       panel=panels[i % 3], online=i % 2 == 0))

# ---- orders + payments ----
seq = [0]


def mk_order(user, plan, status, *, svc=None, typ="new", pay=None, days_ago=1, reject="", receipt=True, card=None):
    seq[0] += 1
    n = seq[0]
    amount = plan.final_price if hasattr(plan, "final_price") else plan.price
    amount = Decimal(int(amount))
    o = Order(user=user, plan=plan, service=svc, type=typ, amount=amount,
              amount_unique=amount + 200 + n * 7, status=status,
              requested_account_name=(svc.panel_username if svc else f"acc{n}"),
              unique_expire_at=now + timedelta(hours=6) if status == "pending_payment" else ago(days=days_ago),
              source=user.source)
    o.sync_unique_lock()
    o.save()
    Order.objects.filter(pk=o.pk).update(created_at=ago(days=days_ago, minutes=n))
    if pay:
        p = Payment(order=o, method="card_manual", amount=o.amount_unique, status=pay, bank_card=card or cards[n % 3],
                    reject_reason=reject)
        if pay != "pending":
            p.confirmed_by = "admin"
            p.confirmed_by_staff = admin
            p.confirmed_at = ago(days=days_ago)
        if receipt:
            p.receipt_image = receipt_png(n, int(o.amount_unique) * 10)
        p.save()
        Payment.objects.filter(pk=p.pk).update(created_at=ago(days=days_ago, minutes=n))
    return o


# the audit customer: every order state
mk_order(me, plans[1], "completed", svc=my_active, pay="approved", days_ago=12)
mk_order(me, plans[0], "completed", svc=my_exp, pay="approved", days_ago=36)
mk_order(me, plans[3], "completed", svc=my_lim, typ="renew", pay="approved", days_ago=20)
mk_order(me, plans[0], "completed", svc=my_hold, pay="approved", days_ago=2)
mk_order(me, plans[1], "rejected", pay="rejected", days_ago=5, reject="مبلغ واریزی با فاکتور مطابقت ندارد")
mk_order(me, plans[2], "expired", days_ago=8)
mk_order(me, plans[0], "failed", pay="approved", days_ago=15)
pending_mine = mk_order(me, plans[1], "pending_payment", svc=my_active, typ="renew", days_ago=0)
mk_order(me, plans[3], "paid", pay="pending", days_ago=0)
# other customers: history + a pending-receipt queue for the admin
for i, u in enumerate(others[:26]):
    mk_order(u, plans[i % 4], "completed", svc=svcs[4 + i], pay="approved", days_ago=rnd.randint(1, 28))
    if i % 4 == 1:
        mk_order(u, plans[(i + 1) % 4], "paid", pay="pending", days_ago=0)
    if i % 7 == 3:
        mk_order(u, plans[i % 4], "rejected", pay="rejected", days_ago=3, reject="رسید نامعتبر")
SmsMessage.objects.get_or_create(raw_text="واریز 1,652,210 ریال به حساب", defaults={"sms_source": src, "device": dev,
                                                                                    "parsed_amount": Decimal(165221)})

# ---- notifications ----
for i, (fa, en) in enumerate([("سرویس شما فعال شد", "Your service is active"),
                              ("۲۰٪ حجم باقی مانده".replace("۲", "2").replace("۰", "0"), "20% data left"),
                              ("به‌روزرسانی سرورها امشب", "Server maintenance tonight")]):
    n, created = Notification.objects.get_or_create(title=fa, defaults={
        "type": "admin_broadcast" if i == 2 else "service_ready", "body": fa + " — جزئیات در داشبورد.",
        "title_en": en, "body_en": en + " — details on the dashboard.", "target_user": None if i == 2 else me,
        "created_by_staff": admin if i == 2 else None})
    if created:
        NotificationDelivery.objects.create(notification=n, user=me, channel="site", status="read" if i == 0 else "sent")

# ---- ops: health / resources / backups ----
if not HealthCheck.objects.exists():
    for t in ["site", "mysql", "redis", "celery_worker", "celery_beat", "bot_sales", "bot_backup", "mail"]:
        HealthCheck.objects.create(target=t, is_up=t != "bot_backup", latency_ms=rnd.randint(3, 60))
    for p in panels:
        HealthCheck.objects.create(target="panel", panel=p, is_up=True, latency_ms=rnd.randint(40, 180))
    HealthCheck.objects.create(target="panel", is_up=True, latency_ms=90)
    for h in range(24):
        r = ResourceStat.objects.create(cpu_percent=rnd.uniform(8, 60), ram_percent=rnd.uniform(35, 70),
                                        disk_percent=41.5, net_in=rnd.randint(10**8, 10**9), net_out=rnd.randint(10**8, 10**9))
        ResourceStat.objects.filter(pk=r.pk).update(sampled_at=ago(hours=h))
    BackupLog.objects.create(filename="backup-2026-09-26.sql.gz", size=48 * 1024 ** 2, sent_to_telegram=True)

# ---- one soft-deleted customer (archive page) ----
gone = mk_user("left_user", name="کاربر حذف‌شده", phone="09350000009")
if gone.deleted_at is None and not gone.services.exists():
    delete_user(gone, staff=admin, reason="درخواست حذف حساب توسط خود کاربر")

print("fake data:", {"users": User.objects.count(), "services": Service.objects.count(), "orders": Order.objects.count(),
                     "payments": Payment.objects.count(), "pending_order": pending_mine.pk})
