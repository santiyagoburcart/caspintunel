"""Card numbers entered before the serializer normalized them may still hold
Persian/Arabic digits (shown to customers on checkout and in the bot). Store
ASCII digits only — the same rule `BankCardSerializer.validate_card_number`
applies to new writes. The number itself does not change."""
from django.db import migrations

_TBL = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def forwards(apps, schema_editor):
    BankCard = apps.get_model("payments_sms", "BankCard")
    for card in BankCard.objects.all():
        digits = "".join(ch for ch in (card.card_number or "").translate(_TBL) if ch.isdigit())
        if digits and digits != card.card_number:
            card.card_number = digits
            card.save(update_fields=["card_number"])


class Migration(migrations.Migration):
    dependencies = [("payments_sms", "0003_smssource_created_at")]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
