from django.db import migrations

# Runs once: afterwards the topics belong to the admin panel (rename, deactivate,
# delete) — a later deploy never brings a deleted topic back.
TOPICS = [
    # name_fa, name_en, description_fa, description_en, requires_active_service
    ("سوالات قبل از خرید", "Pre-purchase questions", "پلن‌ها، قیمت‌ها و نحوهٔ خرید",
     "Plans, prices and how to buy", False),
    ("مشکل پرداخت", "Payment problem", "پرداخت انجام شده ولی تأیید نشده، رسید، مبلغ",
     "Paid but not confirmed, receipts, amounts", True),
    ("مشکل اتصال", "Connection problem", "وصل نمی‌شود، کندی، قطعی", "Cannot connect, slow, disconnects", True),
    ("تمدید و ارتقا", "Renewal & upgrade", "تمدید سرویس، حجم اضافه، تغییر پلن",
     "Renew a service, add volume, change plan", True),
    ("سایر", "Other", "موارد دیگر", "Anything else", True),
]


def seed(apps, schema_editor):
    TicketTopic = apps.get_model("tickets", "TicketTopic")
    if TicketTopic.objects.exists():
        return
    for i, (fa, en, dfa, den, needs) in enumerate(TOPICS):
        TicketTopic.objects.create(name_fa=fa, name_en=en, description_fa=dfa, description_en=den,
                                   requires_active_service=needs, sort_order=(i + 1) * 10)


class Migration(migrations.Migration):
    dependencies = [("tickets", "0001_initial")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
