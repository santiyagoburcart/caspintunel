# انتقال به سرور جدید

English: [migration.md](migration.md)

کل سامانه (دیتابیس، فایل‌های مدیا، تنظیمات، کلیدها، تنظیمات ایمیل و گواهی TLS) با
چند دقیقه قطعی به سرور دیگری منتقل می‌شود و سرور قدیم به‌عنوان راه برگشت آماده
می‌ماند.

| اسکریپت | کجا اجرا می‌شود | کار |
|---|---|---|
| `scripts/migrate-export.sh` | سرور قدیم | یک آرشیو رمزشده + مانیفست؛ با `--final` اول حالت تعمیر و توقف ربات‌ها/celery |
| `scripts/migrate-import.sh` | سرور جدید | بررسی، بازگردانی، مایگریشن، مقایسهٔ تعداد ردیف‌ها؛ ربات‌ها/celery تا `--start-workers` متوقف می‌مانند |
| `scripts/migrate-check.sh` | هر جا | تست سرور جدید قبل از تغییر DNS |
| `scripts/test-migration.sh` | توسعه | تست کامل ابزار روی دو استک موقت |

## چه چیزی منتقل می‌شود و چه چیزی نه

**داخل آرشیو** (AES-256 با رمز عبور): دامپ یکپارچهٔ MySQL، کل مدیا (فیش‌ها، برندینگ،
اپ‌های آپلودشده، پس‌زمینهٔ QR)، فایل `.env`، پوشهٔ `mail/config` (کلیدهای DKIM اگر
وجود داشته باشد)، گواهی‌های TLS و `manifest.json` شامل نسخه، کامیت، تعداد دقیق
ردیف‌های هر جدول، تعداد فایل‌های مدیا، SHA-256 همهٔ اجزا و همهٔ فایل‌های مدیا و هشِ
`SECRET_KEY` و `FIELD_ENCRYPTION_KEY` (فقط هش، برای اثبات یکی بودن کلیدها).

**از `.env` خودِ سرور جدید حفظ می‌شود:** `DB_NAME`، `DB_USER`، `DB_PASSWORD`،
`DB_ROOT_PASSWORD`، `DB_HOST`، `DB_PORT`، `COMPOSE_FILE`، `SERVER_IP`. بقیه — مهم‌تر
از همه `SECRET_KEY` و `FIELD_ENCRYPTION_KEY` — از سرور قدیم می‌آید؛ پس نشست‌های
کاربران معتبر می‌ماند و رمز پنل، توکن ربات‌ها و رمز SMTP همچنان خوانده می‌شوند.

**منتقل نمی‌شود:** Redis (کش؛ خودش ساخته می‌شود)، پوشهٔ قدیمی `backups/` (در صورت
نیاز جداگانه با `rsync` کپی کنید)، صف و لاگ ایمیل، ایمیج‌های Docker (در نصب ساخته
می‌شوند)، خطوط cron سرور، و هر چیز دیگری روی سرور قدیم که جزو caspintunel نیست.

## دو کلید ایمنی

- **حالت تعمیر** — فایل `nginx/flags/maintenance`. تا وقتی این فایل هست همهٔ
  درخواست‌ها صفحهٔ 503 «در حال انتقال به سرور جدید» می‌گیرند و هیچ‌چیز به Django
  نمی‌رسد: نه سفارش، نه فیش، نه پیامک بانکی.
- **توقف ورکرها** — `MIGRATION_HOLD=1` در `.env`. چهار کانتینر `bot_sales`،
  `bot_backup`، `celery_beat` و `celery_worker` بالا می‌آیند ولی بیکار می‌مانند؛ با
  ری‌استارت و `./update.sh` هم همین‌طور می‌مانند. این تضمین می‌کند یک ربات تلگرام
  هیچ‌وقت هم‌زمان از دو سرور اجرا نشود و هیچ کار زمان‌بندی‌شده‌ای وسط کپی داده را
  تغییر ندهد.

`migrate-export.sh --final` هر دو را روی سرور قدیم روشن می‌کند؛ `migrate-import.sh`
توقف را روی سرور جدید نگه می‌دارد تا وقتی `--start-workers` را اجرا کنید.

## مشخصات پیشنهادی سرور

اندازه‌گیری روی سرور فعلی (مهر 1405): کانتینرهای caspintunel حدود **1.2 گیگابایت
رم** مصرف می‌کنند؛ دیتابیس حدود 31 مگابایت، مدیا حدود 15 مگابایت (828 فایل)،
`backups/` حدود 3.3 گیگابایت، ایمیج‌ها و کش بیلد حدود 15 گیگابایت؛ بار CPU حدود
0.2 روی 2 هسته.

| | حداقل | پیشنهادی |
|---|---|---|
| CPU | 2 هسته | 2 تا 4 هسته |
| RAM | 4 گیگابایت (+ 2 گیگابایت swap؛ برای بیلد لازم است) | 8 گیگابایت |
| دیسک سیستم | 40 گیگابایت SSD | 40 تا 60 گیگابایت SSD |
| دیسک داده | — | دیسک جدا 40 تا 50 گیگابایت روی `/data` |
| سیستم‌عامل | Ubuntu 22.04 / 24.04 با Docker Engine و Compose v2 | همان |
| شبکه | پورت 80/443 ورودی؛ **587 خروجی** (رله SMTP)؛ دسترسی به پنل PasarGuard و api.telegram.org (یا `TELEGRAM_PROXY_URL`) | همان |

استفاده از دیسک داده — **قبل از نصب**:

```bash
# /data = دیسک داده
mkdir -p /data/docker /data/caspintunel-backups
echo '{ "data-root": "/data/docker" }' > /etc/docker/daemon.json && systemctl restart docker
git clone https://github.com/santiyagoburcart/caspintunel.git /root/caspintunel
ln -s /data/caspintunel-backups /root/caspintunel/backups
```

## مراحل

قطعی = مراحل 4 تا 7، معمولاً 5 تا 15 دقیقه. مراحل 1 تا 3 را می‌توان چند روز قبل
انجام داد.

### 1. آماده‌سازی (چند روز قبل)

1. سرور قدیم روی آخرین نسخه باشد (`./update.sh`) — ابزار انتقال و حالت تعمیر از
   نسخهٔ 1.8.2 اضافه شده است.
2. Cloudflare ← DNS: مقدار **TTL** رکوردهای `A` (`@`، `www`، `mail`) را دست‌کم یک روز
   قبل روی **1 تا 2 دقیقه** بگذارید. اگر پروکسی (ابر نارنجی) روشن است تغییر آنی
   است و TTL اهمیتی ندارد.
3. سرور جدید: `/data` را آماده کنید (بالا) و **همان نسخه** را نصب کنید:
   ```bash
   cd /root/caspintunel && git checkout v$(ssh root@OLD_IP cat /root/caspintunel/VERSION)
   ./install.sh        # همان دامنه؛ کاربر ادمین هر چه باشد با ایمپورت جایگزین می‌شود
   ```
   صدور Let's Encrypt هنوز ممکن نیست (DNS به سرور قدیم اشاره می‌کند) — طبیعی است؛
   گواهی فعلی با ایمپورت می‌آید.
4. اگر پنل PasarGuard یا سرویس SMTP **لیست IP مجاز** دارد، IP سرور جدید را همین
   حالا اضافه کنید.
5. یک رمز عبور (حداقل 12 کاراکتر) انتخاب و در جای امن نگه دارید؛ روی هر دو سرور:
   `echo 'رمز طولانی شما' > /root/.migrate-pass && chmod 600 /root/.migrate-pass`

### 2. کپی آزمایشی (سایت آنلاین می‌ماند)

```bash
# سرور قدیم — فقط خواندن، بدون قطعی
./scripts/migrate-export.sh --passphrase-file /root/.migrate-pass

# سرور جدید
mkdir -p backups/migration
rsync -avP -e ssh root@OLD_IP:/root/caspintunel/backups/migration/caspintunel-migration-*.tar.enc* backups/migration/
./scripts/migrate-import.sh backups/migration/caspintunel-migration-<…>.tar.enc --passphrase-file /root/.migrate-pass
```

در پایان، وب بالا است و **ربات‌ها و celery متوقف‌اند**. در کپی آزمایشی از سایتِ زنده
ممکن است تعداد ردیف چند جدول پرتردد کمی فرق کند؛ در خروجی نهایی باید دقیقاً برابر
باشد.

### 3. تست سرور جدید قبل از تغییر DNS

```bash
./scripts/migrate-check.sh NEW_IP aicaspin.ir       # از هر جا؛ به DNS دست نمی‌زند
```

TLS، سایت کاربر، پنل، API، پاسخ‌گویی API دستگاه پیامک و WebSocket و عمومی نبودن
فیش‌ها را بررسی می‌کند. سپس در مرورگر تست کنید: در فایل hosts **کامپیوتر خودتان**
(`/etc/hosts` یا `C:\Windows\System32\drivers\etc\hosts`) این خط را اضافه کنید، در
پنجرهٔ خصوصی تست کنید و بعد خط را بردارید:

```
NEW_IP  aicaspin.ir
```

چک‌لیست:

- [ ] ورود مشتری ← داشبورد همان سرویس‌ها و مصرف را نشان می‌دهد
- [ ] **QR** یک سرویس باز می‌شود (با پس‌زمینهٔ برند) و لینک اشتراک تغییر نکرده
- [ ] سوابق خرید، سفارش‌های قبلی را نشان می‌دهد
- [ ] ورود پرسنل به `/panel/` ← اعداد داشبورد با سرور قدیم یکی است
- [ ] **صف پرداخت** پرداخت‌های در انتظار را دارد، فیش باز می‌شود و نشانگر «آنلاین» سبز است (**WebSocket**)
- [ ] اتصال پنل ← **تست اتصال** سبز است (**PasarGuard** از IP جدید در دسترس است)؛ `docker compose exec web python manage.py panel_check`
- [ ] سرویس‌ها ← یک سرویس ← مصرف زنده بارگذاری می‌شود
- [ ] تنظیمات ← ایمیل ← **ارسال ایمیل آزمایشی** می‌رسد
- [ ] دستگاه‌های پیامک فهرست شده‌اند و لاگ پیامک پیام‌های قبلی را دارد (گوشی‌ها به دامنه می‌فرستند، پس با DNS جابه‌جا می‌شوند)
- [ ] برندینگ، پلن‌ها، کارت‌ها، صفحات و تم‌ها مثل قبل است
- [ ] `./scripts/migrate-import.sh --status` ← `MIGRATION_HOLD 1`

روی سرور جدید هنوز پرداخت واقعی انجام ندهید و سفارش واقعی تأیید نکنید: تا ورکرها
متوقف‌اند سرویسی تحویل نمی‌شود و ایمپورت نهایی این کپی را جایگزین می‌کند.

### 4. حالت تعمیر + خروجی نهایی (شروع قطعی)

ساعت خلوت را انتخاب کنید و اول صف پرداخت را تعیین تکلیف کنید.

```bash
# سرور قدیم
./scripts/migrate-export.sh --final --passphrase-file /root/.migrate-pass
```

سایت ← صفحهٔ 503، ربات‌ها و celery ← متوقف، سپس خروجی. پیامک بانکی که در زمان
قطعی برسد دریافت نمی‌شود: واریزهای آن بازه را از صورت‌حساب کارت بررسی و دستی
تأیید کنید.

### 5. ایمپورت آرشیو نهایی

```bash
# سرور جدید
rsync -avP -e ssh root@OLD_IP:/root/caspintunel/backups/migration/caspintunel-migration-*-final.tar.enc* backups/migration/
./scripts/migrate-import.sh backups/migration/caspintunel-migration-<…>-final.tar.enc --passphrase-file /root/.migrate-pass
```

باید پیام **«row counts match the manifest in every table»** و خط تطابق مدیا چاپ
شود. اگر نشد، ادامه ندهید و برگردید (بخش بازگشت).

### 6. تغییر DNS

Cloudflare ← DNS ← رکوردهای `A` برای `@`، `www` (و `mail`) را به IP جدید تغییر دهید؛
یا روی سرور جدید: `docker compose exec web python manage.py configure_dns` (اجرای
آزمایشی؛ برای اعمال `--apply`) که از `SERVER_IP` همین سرور استفاده می‌کند و رکورد
SPF را هم به‌روز می‌کند. بررسی: `dig +short aicaspin.ir` باید IP جدید را بدهد.

### 7. TLS و سپس شروع ورکرها (پایان قطعی)

گواهی کپی‌شده از همین حالا کار می‌کند و تمدید پس از تغییر DNS خودکار است؛ برای صدور
تازه: `./scripts/init-letsencrypt.sh --prod`.

```bash
# سرور جدید — فقط بعد از تغییر DNS و در حالی که سرور قدیم در حالت تعمیر/توقف است
./scripts/migrate-import.sh --start-workers
```

### 8. بررسی نهایی

- دوباره `./scripts/migrate-check.sh NEW_IP aicaspin.ir` و سپس بدون خط hosts
- به ربات فروش `/start` بفرستید؛ مینی‌اپ را باز کنید
- `docker compose logs --tail 20 bot_sales celery_worker` بدون خطا
- صفحهٔ مانیتورینگ: همه سبز؛ یک بکاپ بگیرید
- یک خرید واقعی کوچک از ابتدا تا انتها
- خطوط cron لازم را دوباره اضافه کنید (مثل `scripts/watch-update.sh` برای دکمهٔ به‌روزرسانی)

### 9. سرور قدیم را نگه دارید

چند روز آن را **روشن در حالت تعمیر و با ورکرهای متوقف** (یا خاموش) نگه دارید و حذف
نکنید. تا وقتی سرور جدید فعال است روی سرور قدیم `--resume` اجرا **نکنید**. بعد از
چند روز بدون مشکل: آخرین کپی از `backups/` را بردارید، سرور را حذف کنید و TTL را
به حالت عادی برگردانید.

## بازگشت (Rollback)

**قبل از شروع ورکرها روی سرور جدید** (مراحل 4 تا 6) — هیچ داده‌ای جای دیگری نوشته
نشده و بازگشت فوری است:

```bash
# سرور قدیم
./scripts/migrate-export.sh --resume     # سایت باز می‌شود و ربات‌ها و celery دوباره اجرا می‌شوند
```

و اگر DNS را تغییر داده‌اید به IP قدیم برگردانید.

**بعد از فعال شدن سرور جدید** — سفارش‌ها و پرداخت‌های جدید فقط روی سرور جدید
هستند. یا مشکل را همان‌جا رفع کنید، یا با همین روش در جهت عکس برگردید:
`migrate-export.sh --final` روی سرور جدید ← ایمپورت روی سرور قدیم ← برگرداندن DNS ←
`--start-workers` روی سرور قدیم. در این وضعیت هرگز فقط `--resume` را روی سرور قدیم
نزنید: دادهٔ آن قدیمی است و دو ربات هم‌زمان اجرا می‌شوند.

**ایمپورت ناموفق روی سرور جدید** چیزی را روی سرور قدیم تغییر نمی‌دهد. وضعیت قبلیِ
سرور جدید در `backups/migration/before-import-<زمان>/` می‌ماند (`env`، `db.sql.gz`،
`mail-config.tar`)؛ کافی است ایمپورت را دوباره اجرا کنید.

## دستورهای روز انتقال

```bash
# سرور قدیم
./scripts/migrate-export.sh --final --passphrase-file /root/.migrate-pass
# سرور جدید
rsync -avP -e ssh root@OLD_IP:/root/caspintunel/backups/migration/caspintunel-migration-*-final.tar.enc* backups/migration/
./scripts/migrate-import.sh backups/migration/caspintunel-migration-*-final.tar.enc --passphrase-file /root/.migrate-pass
./scripts/migrate-check.sh NEW_IP aicaspin.ir
#   ← رکوردهای A در Cloudflare را به NEW_IP تغییر دهید
./scripts/migrate-import.sh --start-workers
```

## تست ابزار

`./scripts/test-migration.sh` دو استک موقت می‌سازد (`migtest-src` و `migtest-dst` با
شبکه و ولوم جدا، بدون پورت باز، با کلیدها و رمزهای متفاوت)، اولی را با دادهٔ ساختگی
پر می‌کند و خروجی ← ایمپورت ← مقایسه، محافظ‌ها (رمز اشتباه، آرشیو خراب، ایمپورت روی
همان ماشین)، خروجی نهایی با حالت تعمیر و توقف، ایمپورت دوم با مقایسهٔ دقیق همهٔ
جدول‌ها، `--start-workers` و `--resume` را اجرا می‌کند. به استک اصلی دست نمی‌زند.
