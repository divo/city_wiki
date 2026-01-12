"""
Test cases for the city_import service module.
"""
from django.test import TestCase
from unittest.mock import patch, MagicMock
from ..services.city_import import (
    fetch_city_pois,
    create_or_update_city,
    create_or_get_district,
    process_pois,
    import_city_data
)
from ..models import City, PointOfInterest, District, Validation
from data_processing.wikivoyage_scraper import PointOfInterest as ScraperPOI


class CityImportServiceTestCase(TestCase):
    def setUp(self):
        """Set up test data."""
        self.city = City.objects.create(
            name="Test City",
            country="Test Country"
        )
        
        self.district = District.objects.create(
            name="Test District",
            city=self.city
        )

    @patch('cities.services.city_import.WikivoyageScraper')
    def test_fetch_city_pois_success(self, mock_scraper_class):
        """Test fetching POIs successfully."""
        # Setup mock
        mock_scraper = MagicMock()
        mock_scraper.get_city_data.return_value = (
            [ScraperPOI(name="Test POI", category="see", sub_category="Museum", description="Test description")],
            ["Test District"],
            "About text"
        )
        mock_scraper_class.return_value = mock_scraper
        
        # Call function
        pois, district_pages, about_text = fetch_city_pois("Test City")
        
        # Assertions
        self.assertEqual(len(pois), 1)
        self.assertEqual(pois[0].name, "Test POI")
        self.assertEqual(district_pages, ["Test District"])
        self.assertEqual(about_text, "About text")
        mock_scraper.get_city_data.assert_called_once_with("Test City")

    @patch('cities.services.city_import.WikivoyageScraper')
    def test_fetch_city_pois_api_error(self, mock_scraper_class):
        """Test handling API error when fetching POIs."""
        from mwapi.errors import APIError
        
        # Setup mock to raise APIError
        mock_scraper = MagicMock()
        mock_scraper.get_city_data.side_effect = APIError('error', 'API Error', {})
        mock_scraper_class.return_value = mock_scraper
        
        # Call function
        pois, district_pages, about_text = fetch_city_pois("Test City")
        
        # Assertions
        self.assertIsNone(pois)
        self.assertIsNone(district_pages)
        self.assertIsNone(about_text)
        
        # Check that a validation record was created
        validation = Validation.objects.get(
            context='WikiImport',
            aggregate='FetchArticleError',
            specialized_aggregate='CityFetchError'
        )
        self.assertEqual(validation.description, "error: API Error -- {}")

    def test_create_or_update_city(self):
        """Test creating and updating a city."""
        # Create new city
        new_city = create_or_update_city("New City", about_text="About New City")
        self.assertEqual(new_city.name, "New City")
        self.assertEqual(new_city.about, "About New City")
        
        # Update existing city
        updated_city = create_or_update_city("Test City", about_text="Updated about text")
        self.assertEqual(updated_city.id, self.city.id)
        self.assertEqual(updated_city.about, "Updated about text")
        
        # Create city with different root city name
        district_city = create_or_update_city("District City", "Root City")
        self.assertEqual(district_city.name, "Root City")

    def test_create_or_get_district(self):
        """Test creating and getting districts."""
        # Get existing district
        district = create_or_get_district("Test District", self.city)
        self.assertEqual(district.id, self.district.id)
        
        # Create new district
        new_district = create_or_get_district("New District", self.city)
        self.assertEqual(new_district.name, "New District")
        self.assertEqual(new_district.city, self.city)
        
        # Create sub-district
        sub_district = create_or_get_district("Sub District", self.city, self.district.id)
        self.assertEqual(sub_district.name, "Sub District")
        self.assertEqual(sub_district.parent_district, self.district)
        
        # Test district name with slash
        slash_district = create_or_get_district("City/Slashed District", self.city)
        self.assertEqual(slash_district.name, "Slashed District")

    def test_process_pois(self):
        """Test processing POIs."""
        # Create test POIs
        test_pois = [
            ScraperPOI(
                name="Test POI 1",
                category="see",
                sub_category="Museum",
                description="Description 1",
                coordinates=(1.0, 2.0),
                address="Address 1",
                phone="123-456-7890",
                website="http://example.com",
                hours="9-5",
                rank=1
            ),
            ScraperPOI(
                name="Test POI 2",
                category="eat",
                sub_category="Restaurant",
                description="Description 2",
                rank=2
            )
        ]
        
        # Process POIs
        db_pois = process_pois(self.city, test_pois)
        self.assertEqual(len(db_pois), 2)
        
        # Verify POIs in database
        pois = PointOfInterest.objects.filter(city=self.city).order_by('rank')
        self.assertEqual(pois.count(), 2)
        
        # Check first POI details
        self.assertEqual(pois[0].name, "Test POI 1")
        self.assertEqual(pois[0].category, "see")
        self.assertEqual(pois[0].sub_category, "Museum")
        self.assertEqual(pois[0].latitude, 1.0)
        self.assertEqual(pois[0].longitude, 2.0)
        
        # Check second POI details
        self.assertEqual(pois[1].name, "Test POI 2")
        self.assertEqual(pois[1].category, "eat")
        self.assertEqual(pois[1].sub_category, "Restaurant")
        self.assertIsNone(pois[1].latitude)
        
        # Test clearing existing POIs
        test_pois2 = [
            ScraperPOI(name="New POI", category="eat", sub_category=None, description="New Description")
        ]
        
        db_pois2 = process_pois(self.city, test_pois2, clear_existing=True)
        pois = PointOfInterest.objects.filter(city=self.city)
        self.assertEqual(pois.count(), 1)
        self.assertEqual(pois[0].name, "New POI")

    @patch('cities.services.city_import.fetch_city_pois')
    def test_import_city_data(self, mock_fetch_pois):
        """Test the main import_city_data function."""
        # Setup mock to return test data
        test_pois = [
            ScraperPOI(name="Test POI", category="see", sub_category="Museum", description="Description")
        ]
        mock_fetch_pois.return_value = (test_pois, ["Test District"], "About text")
        
        # Call import function
        result = import_city_data("Test City")
        
        # Verify result
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['city'], 'Test City')
        self.assertEqual(result['pois_count'], 1)
        
        # Verify POI was created
        poi = PointOfInterest.objects.get(name="Test POI")
        self.assertEqual(poi.category, "see")
        
        # Test error handling
        mock_fetch_pois.return_value = (None, None, None)
        error_result = import_city_data("Error City")
        self.assertEqual(error_result['status'], 'error')