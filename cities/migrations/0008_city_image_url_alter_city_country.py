# Generated by Django 5.1.4 on 2025-01-16 09:06

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cities', '0007_pointofinterest_image_url'),
    ]

    operations = [
        migrations.AddField(
            model_name='city',
            name='image_url',
            field=models.URLField(blank=True, help_text='URL to an image of this city', max_length=500, null=True),
        ),
        migrations.AlterField(
            model_name='city',
            name='country',
            field=models.CharField(default='Unknown', max_length=200),
        ),
    ]
