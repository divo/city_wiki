from django.db import models
import os
from django.forms import model_to_dict
from reversion.models import Version
import reversion
from django.conf import settings

def city_image_path(instance, filename):
    """Generate file path for city images."""
    # Get the file extension
    ext = filename.split('.')[-1]
    # Create a clean filename using the city name
    clean_name = instance.name.replace(' ', '_').lower()
    # Return the complete path
    return f'cities/images/{clean_name}.{ext}'

def poi_image_path(instance, filename):
    """Generate file path for POI images."""
    # Get the file extension
    ext = filename.split('.')[-1]
    # Create a clean filename using the POI name and city
    clean_name = instance.name.replace(' ', '_').lower()
    clean_city = instance.city.name.replace(' ', '_').lower()
    # Return the complete path
    return f'cities/images/pois/{clean_city}/{clean_name}.{ext}'

@reversion.register()
class City(models.Model):
    name = models.CharField(max_length=200, unique=True)
    country = models.CharField(max_length=200, default='Unknown')
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    image_file = models.ImageField(upload_to=city_image_path, null=True, blank=True, help_text="Stored image file of this city")
    about = models.TextField(blank=True)  # Store the first 2 paragraphs from WikiVoyage
    wikivoyage_url = models.URLField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "cities"
        ordering = ['name']

    def __str__(self):
        return self.name

    def delete_image_file(self):
        """Delete the image file if it exists."""
        if self.image_file:
            if os.path.isfile(self.image_file.path):
                os.remove(self.image_file.path)
            self.image_file = None
            self.save()

    @property
    def image_url(self):
        """Return the URL for the image file if it exists."""
        if self.image_file:
            return f'{settings.BASE_URL}{self.image_file.url}'
        return None

    def to_dict(self):
        """Convert the model instance to a dictionary, handling special fields."""
        data = model_to_dict(self, exclude=['image_file'])
        data['image_url'] = self.image_url
        return data

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
    image_file = models.ImageField(upload_to=poi_image_path, null=True, blank=True, help_text="Stored image file of this POI")
    rank = models.IntegerField(default=0)
    osm_id = models.CharField(max_length=50, null=True, blank=True, help_text="OpenStreetMap ID for this POI")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['category', 'rank']
        indexes = [
            models.Index(fields=['city', 'category']),
            models.Index(fields=['district', 'category']),
        ]

    def __str__(self):
        return f"{self.name} ({self.city.name})"

    def delete_image_file(self):
        """Delete the image file if it exists."""
        if self.image_file:
            if os.path.isfile(self.image_file.path):
                os.remove(self.image_file.path)
            self.image_file = None
            self.save()

    @property
    def image_url(self):
        """Return the URL for the image file if it exists."""
        if self.image_file:
            return f'{settings.BASE_URL}{self.image_file.url}'
        return None

    def to_dict(self):
        """Convert the model instance to a dictionary, handling special fields."""
        data = model_to_dict(self, exclude=['id', 'city', 'image_file'])
        data['image_url'] = self.image_url
        if self.district:
            data['district'] = self.district.name
        data['osm_id'] = self.osm_id
        return data

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
