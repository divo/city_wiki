# Generated by Django 5.1.4 on 2025-01-16 13:23

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cities', '0008_city_image_url_alter_city_country'),
    ]

    operations = [
        migrations.AddField(
            model_name='city',
            name='about',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='city',
            name='wikivoyage_url',
            field=models.URLField(blank=True, max_length=500),
        ),
    ]
