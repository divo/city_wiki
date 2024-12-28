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
