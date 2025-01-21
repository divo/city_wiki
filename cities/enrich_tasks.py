"""Module for data transformation tasks."""

from celery import shared_task
from .models import City, PointOfInterest, District
from django.db import transaction
import logging
from difflib import SequenceMatcher
from django.db.models import Q
import requests
import os

logger = logging.getLogger(__name__)

def similar(a, b, threshold=0.85):
    """Return True if strings a and b are similar enough."""
    if not a or not b:  # Handle None or empty strings
        return False
    return SequenceMatcher(None, a.lower(), b.lower()).ratio() > threshold

def detect_duplicate_pois(poi1, poi2):
    """
    Check if two POIs are potential duplicates based on various criteria.
    Returns (is_duplicate, reasons) tuple.
    """
    reasons = []
    
    # Calculate various similarity scores
    name_similarity = similar(poi1['name'], poi2['name'], threshold=0.85)
    same_category = poi1['category'] == poi2['category']
    
    # Check coordinates if both POIs have them
    close_coordinates = False
    if (poi1['latitude'] and poi1['longitude'] and 
        poi2['latitude'] and poi2['longitude']):
        # Simple distance check (could be improved with proper geo-distance)
        lat_diff = abs(poi1['latitude'] - poi2['latitude'])
        lon_diff = abs(poi1['longitude'] - poi2['longitude'])
        close_coordinates = lat_diff < 0.001 and lon_diff < 0.001  # Roughly 100m
    
    # Check address similarity if both have addresses
    address_similarity = similar(poi1['address'], poi2['address'], threshold=0.85)
    
    # Determine if this pair should be flagged as potential duplicates
    is_duplicate = False
    
    if name_similarity:
        is_duplicate = True
        reasons.append("Similar names")
    
    if same_category and (close_coordinates or address_similarity):
        is_duplicate = True
        if close_coordinates:
            reasons.append("Same category and very close locations")
        if address_similarity:
            reasons.append("Same category and similar addresses")
    
    return is_duplicate, reasons

@shared_task
def find_all_duplicates(city_id):
    """
    Find potential duplicates by comparing all POIs against each other in the city.
    Returns a list of potential duplicate pairs with their similarity scores.
    """
    try:
        city = City.objects.get(id=city_id)
        logger.info(f"Starting full duplicate detection for {city.name}")
        
        # Get all POIs in the city
        all_pois = PointOfInterest.objects.filter(
            city=city
        ).values('id', 'name', 'category', 'latitude', 'longitude', 'address', 'district__name', 'rank')
        
        duplicates = []
        processed = set()  # Track processed pairs to avoid duplicates
        merged_count = 0
        
        # Compare each POI against all others
        for i, poi1 in enumerate(all_pois):
            for poi2 in list(all_pois)[i+1:]:  # Start from i+1 to avoid self-comparisons and duplicates
                pair_key = tuple(sorted([poi1['id'], poi2['id']]))
                if pair_key in processed:
                    continue
                
                processed.add(pair_key)
                
                is_duplicate, reasons = detect_duplicate_pois(poi1, poi2)
                
                if is_duplicate:
                    # Add location context to the names
                    poi1_name = poi1['name']
                    poi2_name = poi2['name']
                    if poi1['district__name']:
                        poi1_name += f" ({poi1['district__name']})"
                    else:
                        poi1_name += " (Main City)"
                    if poi2['district__name']:
                        poi2_name += f" ({poi2['district__name']})"
                    else:
                        poi2_name += " (Main City)"
                    
                    duplicates.append({
                        'poi1_id': poi1['id'],
                        'poi1_name': poi1_name,
                        'poi2_id': poi2['id'],
                        'poi2_name': poi2_name,
                        'reason': ' & '.join(reasons)
                    })
        
        logger.info(f"Found {len(duplicates)} potential duplicate pairs in {city.name}")
        
        return {
            'status': 'success',
            'message': f'Found {len(duplicates)} potential duplicate pairs',
            'duplicates': duplicates
        }
        
    except Exception as e:
        logger.error(f"Error in find_all_duplicates task: {str(e)}")
        raise

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
                
                is_duplicate, reasons = detect_duplicate_pois(main_poi, other_poi)
                
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
                        'reason': f"{' & '.join(reasons)} | {merge_status}"
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

@shared_task
def geocode_missing_addresses(city_id):
    """
    Find POIs with missing addresses but have coordinates, then use Mapbox to get their addresses.
    Processes one POI at a time to make the task resumable.
    """
    try:
        city = City.objects.get(id=city_id)
        logger.info(f"Starting address geocoding for {city.name}")
        
        # Get POIs with coordinates but no address
        pois = PointOfInterest.objects.filter(
            city=city,
            latitude__isnull=False,
            longitude__isnull=False
        ).filter(Q(address='') | Q(address__isnull=True))
        
        total_pois = pois.count()
        processed_count = 0
        updated_count = 0
        
        mapbox_token = os.environ.get('MAPBOX_TOKEN')
        if not mapbox_token:
            raise ValueError("MAPBOX_TOKEN environment variable not set")
        
        for poi in pois:
            try:
                # Call Mapbox Reverse Geocoding API
                response = requests.get(
                    f'https://api.mapbox.com/geocoding/v5/mapbox.places/{poi.longitude},{poi.latitude}.json',
                    params={
                        'access_token': mapbox_token,
                        'types': 'address',
                        'limit': 1
                    }
                )
                
                if response.status_code == 200:
                    data = response.json()
                    if data['features']:
                        # Get the first (most relevant) result
                        feature = data['features'][0]
                        
                        # Update the POI with the new address
                        poi.address = feature['place_name']
                        poi.save()
                        updated_count += 1
                        logger.info(f"Updated address for POI {poi.name}: {poi.address}")
                    else:
                        logger.warning(f"No address found for POI {poi.name} at coordinates {poi.latitude}, {poi.longitude}")
                else:
                    logger.error(f"Mapbox API error for POI {poi.name}: {response.text}")
                
            except Exception as e:
                logger.error(f"Error processing POI {poi.name}: {str(e)}")
            
            processed_count += 1
            
            # Log progress every 10 POIs
            if processed_count % 10 == 0:
                logger.info(f"Processed {processed_count}/{total_pois} POIs")
        
        return {
            'status': 'success',
            'message': f'Processed {processed_count} POIs, updated {updated_count} addresses',
            'processed_count': processed_count,
            'updated_count': updated_count
        }
        
    except Exception as e:
        logger.error(f"Error in geocode_missing_addresses task: {str(e)}")
        raise

# Data transformation tasks will be added here