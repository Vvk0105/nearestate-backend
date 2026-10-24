from django.db import migrations, models


def backfill_paid(apps, schema_editor):
    """Existing Stripe-approved bookings: take the amount from the chosen tier."""
    ExhibitorApplication = apps.get_model("exhibitions", "ExhibitorApplication")
    paid = ExhibitorApplication.objects.filter(
        status="APPROVED", selected_tier__isnull=False
    ).exclude(stripe_session_id__isnull=True, stripe_payment_intent__isnull=True)
    for app in paid.select_related("selected_tier"):
        app.amount_paid = app.selected_tier.fee
        app.paid_at = app.applied_at
        app.save(update_fields=["amount_paid", "paid_at"])


class Migration(migrations.Migration):

    dependencies = [
        ("exhibitions", "0019_add_website_to_profile_and_booking_ref_to_application"),
    ]

    operations = [
        migrations.AddField(
            model_name="exhibitorapplication",
            name="amount_paid",
            field=models.PositiveIntegerField(
                default=0,
                help_text="Amount actually paid via Stripe, in whole currency units (0 for free/admin-added)",
            ),
        ),
        migrations.AddField(
            model_name="exhibitorapplication",
            name="paid_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RunPython(backfill_paid, migrations.RunPython.noop),
    ]
