from django.db import models

class City(models.Model):
    name = models.CharField(max_length=200, unique=True)
    country = models.CharField(max_length=200)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['name']
        verbose_name_plural = 'cities'
    
    def __str__(self):
        return f"{self.name}, {self.country}"

class PointOfInterest(models.Model):
    CATEGORIES = [
        ('see', 'See'),
        ('eat', 'Eat'),
        ('sleep', 'Sleep'),
        ('shop', 'Shop'),
        ('drink', 'Drink'),
        ('play', 'Play'),
    ]
    
    # TODO: Need universal ID(s). Probably going to be a mix of (lat,long) and OSM IDs
    city = models.ForeignKey(City, on_delete=models.CASCADE, related_name='points_of_interest', null=True)
    name = models.CharField(max_length=200)
    category = models.CharField(max_length=50, choices=CATEGORIES)
    description = models.TextField()
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    address = models.CharField(max_length=500, null=True, blank=True)
    phone = models.CharField(max_length=50, null=True, blank=True)
    website = models.URLField(max_length=500, null=True, blank=True)
    hours = models.CharField(max_length=500, null=True, blank=True)
    rank = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['category', 'rank']
        indexes = [
            models.Index(fields=['city', 'category']),
        ]
