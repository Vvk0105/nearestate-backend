from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('exhibitions', '0008_exhibition_registration_fee'),
    ]

    operations = [
        migrations.AddField(
            model_name='exhibition',
            name='payment_details',
            field=models.TextField(
                blank=True,
                null=True,
                help_text='Free-text payment instructions shown to exhibitors (e.g. Account No, IFSC, IBAN, SWIFT)',
            ),
        ),
    ]
