"""Module for data transformation tasks."""

from celery import shared_task
from .models import City, PointOfInterest, District
from django.db import transaction
import logging
from difflib import SequenceMatcher
from django.db.models import Q
import requests

logger = logging.getLogger(__name__)

def similar(a, b, threshold=0.85):
    """Return True if strings a and b are similar enough."""
    if not a or not b:  # Handle None or empty strings
        return False
    return SequenceMatcher(None, a.lower(), b.lower()).ratio() > threshold

@shared_task
def dedup_main_city(city_id):
    """
    Find potential duplicates by comparing main city POIs against all POIs in the city.
    Returns a list of potential duplicate pairs with their similarity scores.
    """
    try:
        city = City.objects.get(id=city_id)
        logger.info(f"Starting main city deduplication for {city.name}")
        
        # Get POIs in the main city area (no district)
        main_pois = PointOfInterest.objects.filter(
            city=city,
            district__isnull=True
        ).values('id', 'name', 'category', 'latitude', 'longitude', 'address', 'rank')
        
        # Get all POIs in the city (including districts)
        all_pois = PointOfInterest.objects.filter(
            city=city
        ).values('id', 'name', 'category', 'latitude', 'longitude', 'address', 'district__name', 'rank')
        
        duplicates = []
        processed = set()  # Track processed pairs to avoid duplicates
        merged_count = 0
        
        # Compare each main city POI against all POIs
        for main_poi in main_pois:
            for other_poi in all_pois:
                # Skip self-comparisons
                if main_poi['id'] == other_poi['id']:
                    continue
                    
                pair_key = tuple(sorted([main_poi['id'], other_poi['id']]))
                if pair_key in processed:
                    continue
                
                processed.add(pair_key)
                
                # Calculate various similarity scores
                name_similarity = similar(main_poi['name'], other_poi['name'], threshold=0.85)
                same_category = main_poi['category'] == other_poi['category']
                
                # Check coordinates if both POIs have them
                close_coordinates = False
                if (main_poi['latitude'] and main_poi['longitude'] and 
                    other_poi['latitude'] and other_poi['longitude']):
                    # Simple distance check (could be improved with proper geo-distance)
                    lat_diff = abs(main_poi['latitude'] - other_poi['latitude'])
                    lon_diff = abs(main_poi['longitude'] - other_poi['longitude'])
                    close_coordinates = lat_diff < 0.001 and lon_diff < 0.001  # Roughly 100m
                
                # Check address similarity if both have addresses
                address_similarity = similar(main_poi['address'], other_poi['address'], threshold=0.85)
                
                # Determine if this pair should be flagged as potential duplicates
                is_duplicate = False
                reason = []
                
                if name_similarity:
                    is_duplicate = True
                    reason.append("Similar names")
                
                if same_category and (close_coordinates or address_similarity):
                    is_duplicate = True
                    if close_coordinates:
                        reason.append("Same category and very close locations")
                    if address_similarity:
                        reason.append("Same category and similar addresses")
                
                if is_duplicate:
                    # Add location context to the names
                    main_poi_name = main_poi['name'] + " (Main City)"
                    other_poi_name = other_poi['name']
                    if other_poi['district__name']:
                        other_poi_name += f" ({other_poi['district__name']})"
                    else:
                        other_poi_name += " (Main City)"
                    
                    # Merge the POIs
                    merge_data = {
                        'keep_id': other_poi['id'],  # Keep the non-main city POI
                        'remove_id': main_poi['id'],  # Remove the main city POI
                        'field_selections': {
                            'name': main_poi['name'],  # Take name from main city POI
                            'district': f"{other_poi['district__name']}, Main City",  # Append Main City to district
                            'rank': min(main_poi['rank'], other_poi['rank'])  # Take lower rank
                        }
                    }
                    
                    merge_status = "❌ Merge not attempted"
                    try:
                        # Make request to poi_merge endpoint
                        response = requests.post(
                            f'http://localhost:8000/city/{city.name}/poi/merge/',
                            json=merge_data,
                            headers={'Content-Type': 'application/json'}
                        )
                        
                        if response.status_code == 200:
                            merged_count += 1
                            merge_status = "✅ Successfully merged"
                        else:
                            merge_status = f"❌ Merge failed: {response.text}"
                    except Exception as e:
                        logger.error(f"Error merging POIs: {str(e)}")
                        merge_status = f"❌ Merge error: {str(e)}"
                    
                    duplicates.append({
                        'poi1_id': main_poi['id'],
                        'poi1_name': main_poi_name,
                        'poi2_id': other_poi['id'],
                        'poi2_name': other_poi_name,
                        'reason': f"{' & '.join(reason)} | {merge_status}"
                    })
        
        logger.info(f"Found {len(duplicates)} potential duplicate pairs in {city.name}, merged {merged_count}")
        
        return {
            'status': 'success',
            'message': f'Found {len(duplicates)} potential duplicate pairs for main city POIs, merged {merged_count}',
            'duplicates': duplicates
        }
        
    except Exception as e:
        logger.error(f"Error in dedup_main_city task: {str(e)}")
        raise

# Data transformation tasks will be added here