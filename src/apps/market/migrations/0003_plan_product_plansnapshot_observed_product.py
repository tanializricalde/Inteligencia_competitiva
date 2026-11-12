from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("market", "0002_initial")]

    operations = [
        migrations.AddField(
            model_name="plan",
            name="product",
            field=models.CharField(blank=True, max_length=160),
        ),
        migrations.AddField(
            model_name="plansnapshot",
            name="observed_product",
            field=models.CharField(blank=True, max_length=160),
        ),
    ]
