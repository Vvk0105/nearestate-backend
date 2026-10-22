from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0004_user_profile_completed"),
    ]

    operations = [
        migrations.AddField(
            model_name="emailotp",
            name="attempts",
            field=models.PositiveSmallIntegerField(default=0),
        ),
    ]
