from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('exhibitions', '0011_exhibition_currency_symbol'),
    ]

    operations = [
        migrations.AddField(
            model_name='exhibition',
            name='venue_link',
            field=models.URLField(
                blank=True,
                null=True,
                max_length=500,
                help_text='Optional link to the venue website or event page',
            ),
        ),
        migrations.AddField(
            model_name='exhibition',
            name='location_link',
            field=models.URLField(
                blank=True,
                null=True,
                max_length=500,
                help_text='Optional Google Maps or location link for the venue',
            ),
        ),
    ]
