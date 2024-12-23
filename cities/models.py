from django.db import models

class PointOfInterest(models.Model):
    # TODO: Need universal ID(s). Probably going to be a mix of (lat,long) and OSM IDs
    name = models.CharField(max_length=200)
    category = models.CharField(max_length=50, choices=[
        ('see', 'See'),
        ('eat', 'Eat'),
        ('sleep', 'Sleep'),
        ('shop', 'Shop'),
        ('drink', 'Drink'),
        ('play', 'Play'),
    ])
    description = models.TextField()
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    address = models.CharField(max_length=500, null=True, blank=True)
    phone = models.CharField(max_length=50, null=True, blank=True)
    website = models.URLField(max_length=500, null=True, blank=True)
    hours = models.CharField(max_length=500, null=True, blank=True)
    rank = models.IntegerField(default=0)
    city_name = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['category', 'rank']
        indexes = [
            models.Index(fields=['city_name', 'category']),
        ]
