from django.db import models
import reversion

@reversion.register()
class City(models.Model):
    name = models.CharField(max_length=200, unique=True)
    country = models.CharField(max_length=200, default='Unknown')
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    image_url = models.URLField(max_length=500, null=True, blank=True, help_text="URL to an image of this city")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "cities"
        ordering = ['name']

    def __str__(self):
        return self.name

@reversion.register()
class District(models.Model):
    name = models.CharField(max_length=200)
    city = models.ForeignKey(City, on_delete=models.CASCADE, related_name='districts')
    parent_district = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='subdistricts')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        unique_together = [['name', 'city']]  # A district name should be unique within a city

    def __str__(self):
        return f"{self.name} (District of {self.city.name})"

@reversion.register()
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
    city = models.ForeignKey(City, on_delete=models.CASCADE, related_name='points_of_interest')
    district = models.ForeignKey(District, on_delete=models.SET_NULL, null=True, blank=True, related_name='points_of_interest')
    name = models.CharField(max_length=200)
    category = models.CharField(max_length=50, choices=CATEGORIES)
    sub_category = models.CharField(max_length=200, null=True, blank=True)
    description = models.TextField()
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    address = models.CharField(max_length=500, null=True, blank=True)
    phone = models.CharField(max_length=50, null=True, blank=True)
    website = models.URLField(max_length=500, null=True, blank=True)
    hours = models.CharField(max_length=500, null=True, blank=True)
    rank = models.IntegerField(default=0)
    image_url = models.URLField(max_length=500, null=True, blank=True, help_text="URL to an image of this POI")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['category', 'rank']
        indexes = [
            models.Index(fields=['city', 'category']),
            models.Index(fields=['district', 'category']),
        ]

class Validation(models.Model):
    """
    Track specific errors that occur when building entries in the dataset.
    """
    parent = models.ForeignKey(City, on_delete=models.SET_NULL, null=True, blank=True, related_name='validations')
    context = models.CharField(max_length=50, help_text="Context of the validation (e.g., 'import', 'update')")
    aggregate = models.CharField(max_length=50, help_text="High-level error category")
    specialized_aggregate = models.CharField(max_length=50, help_text="Specific error subcategory")
    description = models.CharField(max_length=500, help_text="Detailed description of the validation error")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['parent']),
            models.Index(fields=['context', 'aggregate']),
        ]

    def __str__(self):
        return f"{self.aggregate}: {self.parent.name if self.parent else 'No City'} ({self.context})"

class PoiList(models.Model):
    title = models.CharField(max_length=200)
    city = models.ForeignKey(City, on_delete=models.CASCADE, related_name='poi_lists')
    pois = models.ManyToManyField(PointOfInterest, related_name='lists')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.title} ({self.city.name})"

    class Meta:
        ordering = ['-created_at']
