"""Module for data transformation tasks."""

from celery import shared_task
from .models import City, PointOfInterest, District
from django.db import transaction
import logging
from difflib import SequenceMatcher
from django.db.models import Q
import requests
import os
import time
import geopy.distance
import pandas as pd
from shapely.geometry import Point
import geopandas as gpd

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

    if name_similarity and (close_coordinates or address_similarity):
        is_duplicate = True
        reasons.append("Similar names and coordinates or addresses")

#    if same_category and (close_coordinates or address_similarity):
#        is_duplicate = True
#        if close_coordinates:
#            reasons.append("Same category and very close locations")
#        if address_similarity:
#            reasons.append("Same category and similar addresses")

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

@shared_task
def geocode_missing_coordinates(city_id):
    """
    Find POIs with missing coordinates but have addresses, then use Mapbox to get their coordinates.
    Processes one POI at a time to make the task resumable.
    """
    try:
        city = City.objects.get(id=city_id)
        logger.info(f"Starting coordinate geocoding for {city.name}")

        # Get POIs with addresses but no coordinates
        pois = PointOfInterest.objects.filter(
            city=city,
            latitude__isnull=True,
            address__isnull=False
        ).exclude(address='')

        total_pois = pois.count()
        processed_count = 0
        updated_count = 0

        mapbox_token = os.environ.get('MAPBOX_TOKEN')
        if not mapbox_token:
            raise ValueError("MAPBOX_TOKEN environment variable not set")

        # Check if city has valid coordinates for proximity biasing
        has_valid_coords = (
            city.longitude is not None and
            city.latitude is not None and
            -180 <= float(city.longitude) <= 180 and
            -90 <= float(city.latitude) <= 90
        )

        for poi in pois:
            try:
                # Construct search query with POI name and address
                search_text = f"{poi.name}, {poi.address}, {city.name}"

                # Base params
                params = {
                    'access_token': mapbox_token,
                    'limit': 1,
                    'types': 'address,poi',  # Look for both addresses and points of interest
                }

                # Add proximity only if city has valid coordinates
                if has_valid_coords:
                    params['proximity'] = f"{city.longitude},{city.latitude}"

                # Call Mapbox Forward Geocoding API
                response = requests.get(
                    'https://api.mapbox.com/geocoding/v5/mapbox.places/' + search_text + '.json',
                    params=params
                )

                if response.status_code == 200:
                    data = response.json()
                    if data['features']:
                        # Get the first (most relevant) result
                        feature = data['features'][0]
                        coordinates = feature['geometry']['coordinates']

                        # Update the POI with the new coordinates
                        poi.longitude = coordinates[0]
                        poi.latitude = coordinates[1]
                        poi.save()
                        updated_count += 1
                        logger.info(f"Updated coordinates for POI {poi.name}: ({poi.latitude}, {poi.longitude})")
                    else:
                        logger.warning(f"No coordinates found for POI {poi.name} with address {poi.address}")
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
            'message': f'Processed {processed_count} POIs, updated {updated_count} coordinates',
            'processed_count': processed_count,
            'updated_count': updated_count
        }

    except Exception as e:
        logger.error(f"Error in geocode_missing_coordinates task: {str(e)}")
        raise

@shared_task
def geocode_city_coordinates(city_id):
    """
    Fetch coordinates for a city using Mapbox's geocoding API.
    This should be run before attempting to geocode POIs to ensure proper proximity biasing.
    """
    try:
        city = City.objects.get(id=city_id)
        logger.info(f"Starting city coordinate lookup for {city.name}")

        mapbox_token = os.environ.get('MAPBOX_TOKEN')
        if not mapbox_token:
            raise ValueError("MAPBOX_TOKEN environment variable not set")

        # Construct search query with city name and country
        search_text = f"{city.name}, {city.country}" if city.country else city.name

        # Call Mapbox Forward Geocoding API
        response = requests.get(
            'https://api.mapbox.com/geocoding/v5/mapbox.places/' + search_text + '.json',
            params={
                'access_token': mapbox_token,
                'limit': 1,
                'types': 'place',  # Limit to cities/places
            }
        )

        if response.status_code == 200:
            data = response.json()
            if data['features']:
                # Get the first (most relevant) result
                feature = data['features'][0]
                coordinates = feature['geometry']['coordinates']

                # Update the city with the new coordinates
                city.longitude = coordinates[0]
                city.latitude = coordinates[1]

                # If country wasn't set, get it from the context
                if not city.country:
                    for context in feature.get('context', []):
                        if context.get('id', '').startswith('country.'):
                            city.country = context['text']
                            break

                city.save()
                logger.info(f"Updated coordinates for {city.name}: ({city.latitude}, {city.longitude})")

                return {
                    'status': 'success',
                    'message': f'Updated coordinates for {city.name}',
                    'coordinates': {
                        'latitude': city.latitude,
                        'longitude': city.longitude
                    },
                    'country': city.country
                }
            else:
                logger.warning(f"No coordinates found for city {city.name}")
                return {
                    'status': 'warning',
                    'message': f'No coordinates found for {city.name}'
                }
        else:
            logger.error(f"Mapbox API error for city {city.name}: {response.text}")
            return {
                'status': 'error',
                'message': f'API error: {response.text}'
            }

    except Exception as e:
        logger.error(f"Error in geocode_city_coordinates task: {str(e)}")
        raise

@shared_task
def fetch_osm_ids(city_id):
    """
    Find POIs without OSM IDs and try to match them using Overpass API.
    Searches for POIs within 5 meters of our coordinates.
    Processes one POI at a time to make the task resumable.
    """
    try:
        city = City.objects.get(id=city_id)
        logger.info(f"Starting OSM ID lookup for {city.name}")

        # Get POIs without OSM IDs but with coordinates
        pois = PointOfInterest.objects.filter(
            city=city,
            osm_id__isnull=True,
            latitude__isnull=False,
            longitude__isnull=False
        )

        total_pois = pois.count()
        processed_count = 0
        updated_count = 0

        # Overpass API endpoint
        overpass_url = "https://overpass-api.de/api/interpreter"

        for poi in pois:
            try:
                # Construct Overpass QL query to find nodes within 5 meters
                # nwr means nodes, ways, and relations
                overpass_query = f"""
                [out:json];
                nwr(around:5,{poi.latitude},{poi.longitude})->.all;
                .all out body;
                """

                response = requests.post(overpass_url, data={'data': overpass_query})

                if response.status_code == 200:
                    data = response.json()
                    if data['elements']:
                        # Get the closest element (first one)
                        element = data['elements'][0]
                        osm_id = str(element['id'])
                        element_type = element['type']  # node, way, or relation

                        # Update the POI with the OSM ID, prefixing with type for clarity
                        poi.osm_id = f"{element_type}/{osm_id}"
                        poi.save()
                        updated_count += 1
                        logger.info(f"Updated OSM ID for POI {poi.name} ({poi.latitude}, {poi.longitude}): {poi.osm_id}")
                    else:
                        logger.warning(f"No POI found within 5m of coordinates ({poi.latitude}, {poi.longitude}) for {poi.name}")
                else:
                    logger.error(f"Overpass API error for POI {poi.name}: {response.text}")

                # Sleep briefly to respect rate limits
                time.sleep(1)

            except Exception as e:
                logger.error(f"Error processing POI {poi.name}: {str(e)}")

            processed_count += 1

            # Log progress every 10 POIs
            if processed_count % 10 == 0:
                logger.info(f"Processed {processed_count}/{total_pois} POIs")

        return {
            'status': 'success',
            'message': f'Processed {processed_count} POIs, updated {updated_count} with OSM IDs',
            'processed_count': processed_count,
            'updated_count': updated_count
        }

    except Exception as e:
        logger.error(f"Error in fetch_osm_ids task: {str(e)}")
        raise

def load_osm_data_from_pbf(pbf_file):
    """
    Load OSM data from PBF file including POIs and buildings, with preprocessing.
    
    Args:
        pbf_file: Path to the local OSM PBF file
        
    Returns:
        tuple: (osm_pois_4326, osm_pois_3857) - OSM data in WGS84 and Web Mercator projections
    """
    from pyrosm import OSM
    import pandas as pd
    
    # Initialize Pyrosm and load the data
    logger.info("Loading OSM data with Pyrosm...")
    osm = OSM(pbf_file)

    # Load multiple types of OSM data
    osm_pois = osm.get_pois()
    logger.info(f"Loaded {len(osm_pois)} POIs from OSM")

    # Also load buildings which might contain POIs
    try:
        osm_buildings = osm.get_buildings()
        logger.info(f"Loaded {len(osm_buildings)} buildings from OSM")
        # Combine POIs and buildings
        osm_pois = pd.concat([osm_pois, osm_buildings], ignore_index=True)
        logger.info(f"Combined total: {len(osm_pois)} OSM features")
    except Exception as e:
        logger.warning(f"Could not load buildings: {e}")

    # Remove duplicates based on ID if any and reset indices
    osm_pois = osm_pois.drop_duplicates(subset=['id'], keep='first').reset_index(drop=True)

    # Ensure OSM POIs are in WGS 84
    osm_pois = osm_pois.to_crs("EPSG:4326")

    # Pre-project OSM data to Web Mercator for efficient distance calculations
    logger.info("Projecting OSM data to Web Mercator for distance calculations...")
    osm_projected = osm_pois.to_crs("EPSG:3857")
    
    return osm_pois, osm_projected


def find_best_name_match_from_nearby(poi_name, nearby_osm_pois, threshold=60):
    """
    Given multiple nearby OSM POIs, find the one with the best name match using thefuzz fuzzy matching.

    Args:
        poi_name: Name of the target POI
        nearby_osm_pois: DataFrame of nearby OSM POIs
        threshold: Minimum similarity score (0-100, thefuzz uses 0-100 scale)

    Returns the best matching row or None if no good match found.
    """
    from thefuzz import fuzz
    import pandas as pd

    if poi_name is None or poi_name.strip() == "":
        return None

    poi_name_clean = poi_name.strip()

    # Name fields to check in order of preference
    name_fields = ['name', 'name:en', 'brand', 'addr:housename']

    best_score = 0
    best_match = None

    # For each OSM POI, calculate the best score across all its name fields
    for idx in nearby_osm_pois.index:
        osm_poi = nearby_osm_pois.loc[idx]
        poi_best_score = 0

        # Check each name field for this POI
        for field in name_fields:
            if field in osm_poi and pd.notna(osm_poi[field]):
                osm_name = str(osm_poi[field]).strip()
                if osm_name:  # Only process non-empty names
                    # Use token_sort_ratio for better handling of word order differences
                    score = fuzz.token_sort_ratio(poi_name_clean, osm_name)
                    poi_best_score = max(poi_best_score, score)

        # Update global best if this POI's score is better
        if poi_best_score > best_score and poi_best_score >= threshold:
            best_score = poi_best_score
            best_match = osm_poi

    return best_match if best_score >= threshold else None


def find_closest_osm_poi_optimized(target_point_projected, osm_pois, osm_projected, radius_meters=20, poi_name=None):
    """
    Find the closest OSM POI using pre-computed target projection.

    Args:
        target_point_projected: Pre-projected target point geometry (EPSG:3857)
        osm_pois: GeoDataFrame of OSM POIs in EPSG:4326 (for tag extraction)
        osm_projected: GeoDataFrame of OSM POIs in EPSG:3857 (for distance calculation)
        radius_meters: Search radius in meters
        poi_name: Name of the target POI for name matching

    Returns:
        tuple: (osm_id_string, distance_meters, tags_dict) or (None, None, None) if no match
    """
    import pandas as pd

    try:
        # Calculate distances in meters using pre-projected data
        distances = osm_projected.geometry.distance(target_point_projected)

        # Filter by radius
        within_radius_mask = distances <= radius_meters

        if not within_radius_mask.any():
            return None, None, None

        # Get nearby POIs from original (unprojected) data for tag extraction
        nearby = osm_pois[within_radius_mask].copy()
        nearby['distance_meters'] = distances[within_radius_mask]

        # Filter to only include nodes and ways (exclude relations)
        if 'osm_type' in nearby.columns:
            nearby = nearby[nearby['osm_type'].isin(['node', 'way'])]
        elif 'type' in nearby.columns:
            nearby = nearby[nearby['type'].isin(['node', 'way'])]

        # Check if we still have results after filtering
        if len(nearby) == 0:
            return None, None, None

        # Sort by distance
        nearby = nearby.sort_values('distance_meters')

        # If multiple results and we have a POI name, try name matching to find the best one
        if len(nearby) > 1 and poi_name:
            best_match = find_best_name_match_from_nearby(poi_name, nearby)
            if best_match is not None:
                closest = best_match
            else:
                closest = nearby.iloc[0]  # Fall back to closest by distance
        else:
            closest = nearby.iloc[0]

        # Get OSM ID and type
        osm_id = str(closest['id'])
        # Check if 'osm_type' exists in the data, otherwise use 'type' or default to 'node'
        if 'osm_type' in closest:
            osm_type = closest['osm_type']
        elif 'type' in closest:
            osm_type = closest['type']
        else:
            osm_type = 'node'

        osm_id_string = f"{osm_type}/{osm_id}"

        # Extract tags for logging (exclude technical columns)
        exclude_cols = {'geometry', 'id', 'distance_meters', 'type', 'osm_type', 'version', 'timestamp', 'visible'}
        tags = {col: closest[col] for col in closest.index
                if pd.notna(closest[col]) and col not in exclude_cols}

        return osm_id_string, closest['distance_meters'], tags

    except Exception as e:
        logger.error(f"Error in find_closest_osm_poi_optimized: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return None, None, None


def find_closest_osm_poi(poi_lat, poi_lon, osm_pois, osm_projected, radius_meters=5, poi_name=None):
    """
    Find the closest OSM POI within the given radius using proper geographic distance calculation.

    Args:
        poi_lat: Latitude of target POI
        poi_lon: Longitude of target POI
        osm_pois: GeoDataFrame of OSM POIs in EPSG:4326 (for tag extraction)
        osm_projected: GeoDataFrame of OSM POIs in EPSG:3857 (for distance calculation)
        radius_meters: Search radius in meters (default: 5)

    Returns:
        tuple: (osm_id_string, distance_meters, tags_dict) or (None, None, None) if no match
    """
    from shapely.geometry import Point
    import geopandas as gpd
    import pandas as pd

    try:
        # Create target point in WGS84 and project to Web Mercator
        target_point = Point(poi_lon, poi_lat)
        target_gdf = gpd.GeoDataFrame({"geometry": [target_point]}, crs="EPSG:4326")
        target_projected = target_gdf.to_crs("EPSG:3857")

        # Calculate distances in meters using pre-projected data
        distances = osm_projected.geometry.distance(target_projected.iloc[0].geometry)

        # Filter by radius
        within_radius_mask = distances <= radius_meters

        if not within_radius_mask.any():
            return None, None, None

        # Get nearby POIs from original (unprojected) data for tag extraction
        nearby = osm_pois[within_radius_mask].copy()
        nearby['distance_meters'] = distances[within_radius_mask]

        # Sort by distance
        nearby = nearby.sort_values('distance_meters')

        # If multiple results and we have a POI name, try name matching to find the best one
        if len(nearby) > 1 and poi_name:
            best_match = find_best_name_match_from_nearby(poi_name, nearby)
            if best_match is not None:
                closest = best_match
            else:
                closest = nearby.iloc[0]  # Fall back to closest by distance
        else:
            closest = nearby.iloc[0]

        # Get OSM ID and type
        osm_id = str(closest['id'])
        # Check if 'osm_type' exists in the data, otherwise use 'type' or default to 'node'
        if 'osm_type' in closest:
            osm_type = closest['osm_type']
        elif 'type' in closest:
            osm_type = closest['type']
        else:
            osm_type = 'node'

        osm_id_string = f"{osm_type}/{osm_id}"

        # Extract tags for logging (exclude technical columns)
        exclude_cols = {'geometry', 'id', 'distance_meters', 'type', 'osm_type', 'version', 'timestamp', 'visible'}
        tags = {col: closest[col] for col in closest.index
                if pd.notna(closest[col]) and col not in exclude_cols}

        return osm_id_string, closest['distance_meters'], tags

    except Exception as e:
        logger.error(f"Error in find_closest_osm_poi: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return None, None, None


@shared_task
def find_osm_ids_local(city_id, pois=None, pbf_file=None):
    """
    Find POIs without OSM IDs by searching a local OSM PBF file using Pyrosm.
    Searches for nodes within 5 meters of each POI's coordinates.

    Args:
        city_id: ID of the city to process
        pbf_file: Path to the local OSM PBF file
    """
    try:
        if not pbf_file:
            raise ValueError("No PBF file path provided")

        import os
        if not os.path.isfile(pbf_file):
            raise ValueError(f"PBF file not found at path: {pbf_file}")

        from pyrosm import OSM

        city = City.objects.get(id=city_id)
        logger.info(f"Starting local OSM ID lookup for {city.name} using PBF file: {pbf_file}")

        if pois is None:
            raise ValueError("POIs parameter is required")

        total_pois = pois.count()
        if total_pois == 0:
            logger.info(f"No POIs in {city.name} need OSM IDs")
            return {
                'status': 'success',
                'message': 'No POIs need OSM IDs',
                'processed_count': 0,
                'updated_count': 0
            }

        logger.info(f"Found {total_pois} POIs to process in {city.name}")

        # Load OSM data
        osm_pois, osm_projected = load_osm_data_from_pbf(pbf_file)

        # Process each POI
        processed_count = 0
        updated_count = 0

        logger.info(f"Found {len(pois)} POIs to process in {city.name}")

        # Pre-compute all target projections to avoid repeated coordinate transformations
        logger.info("Pre-computing POI coordinate projections...")
        poi_coords = [(poi.latitude, poi.longitude, poi.name, poi.id) for poi in pois]

        from shapely.geometry import Point
        import geopandas as gpd

        # Create all target points at once
        target_points = [Point(lon, lat) for lat, lon, name, poi_id in poi_coords]
        target_gdf = gpd.GeoDataFrame(
            {"geometry": target_points, "poi_name": [name for lat, lon, name, poi_id in poi_coords], "poi_id": [poi_id for lat, lon, name, poi_id in poi_coords]},
            crs="EPSG:4326"
        )
        target_projected = target_gdf.to_crs("EPSG:3857")

        for i, poi in enumerate(pois):
            try:
                # Use pre-computed projection for this POI
                target_point_projected = target_projected.iloc[i]

                # Single search with 20m radius (prioritizes closer matches and better name matches)
                osm_id_string, distance_meters, tags = find_closest_osm_poi_optimized(
                    target_point_projected.geometry, osm_pois, osm_projected, poi_name=poi.name
                )

                if osm_id_string:
                    # Update the POI
                    poi.osm_id = osm_id_string
                    poi.save()
                    updated_count += 1

            except Exception as e:
                logger.error(f"Error processing POI {poi.name}: {str(e)}")

            processed_count += 1
            if processed_count % 100 == 0:
                logger.info(f"Progress: {processed_count}/{total_pois} POIs processed, {updated_count} matches found")

        logger.info(f"\nTask complete for {city.name}:")
        logger.info(f"- Total POIs processed: {processed_count}")
        logger.info(f"- POIs updated with OSM IDs: {updated_count}")
        logger.info(f"- POIs without matches: {processed_count - updated_count}")

        return {
            'status': 'success',
            'message': f'Processed {processed_count} POIs, updated {updated_count} with OSM IDs',
            'processed_count': processed_count,
            'updated_count': updated_count
        }

    except Exception as e:
        logger.error(f"Error in find_osm_ids_local task: {str(e)}")
        raise

@shared_task
def find_duplicate_keys(city_id):
    """
    Find POIs with duplicate keys, where key is {name}-{latitude}-{longitude}.
    Only considers POIs that have both latitude and longitude.
    """
    try:
        city = City.objects.get(id=city_id)
        logger.info(f"Starting duplicate key detection for {city.name}")

        # Get POIs with coordinates
        pois = PointOfInterest.objects.filter(
            city=city,
            latitude__isnull=False,
            longitude__isnull=False
        ).values('id', 'name', 'latitude', 'longitude', 'category', 'district__name')

        # Group POIs by their key
        poi_groups = {}
        for poi in pois:
            # Format coordinates to fixed precision to avoid floating point issues
            lat = "{:.6f}".format(float(poi['latitude']))
            lon = "{:.6f}".format(float(poi['longitude']))
            name = str(poi['name'] or '')

            key = f"{name}-{lat}-{lon}"
            if key not in poi_groups:
                poi_groups[key] = []
            poi_groups[key].append(poi)

        # Find groups with duplicates
        duplicates = []
        for key, group in poi_groups.items():
            if len(group) > 1:
                # Format POI info for display
                poi_list = []
                for poi in group:
                    poi_name = str(poi['name'] or '')
                    district = str(poi['district__name'] or 'Main City')

                    poi_list.append({
                        'id': int(poi['id']),
                        'name': f"{poi_name} ({district})",
                        'category': str(poi['category'] or ''),
                        'latitude': "{:.6f}".format(float(poi['latitude'])),
                        'longitude': "{:.6f}".format(float(poi['longitude']))
                    })

                duplicates.append({
                    'key': key,
                    'count': len(group),
                    'pois': poi_list
                })

        logger.info(f"Found {len(duplicates)} duplicate key groups in {city.name}")

        return {
            'status': 'success',
            'message': f'Found {len(duplicates)} groups of POIs with duplicate keys',
            'duplicates': duplicates
        }

    except Exception as e:
        logger.error(f"Error in find_duplicate_keys task: {str(e)}")
        raise

@shared_task
def auto_merge_duplicates(city_id, duplicates_data=None):
    """
    Automatically merge general duplicate POIs using best-value logic.
    Uses provided duplicates data or calls find_all_duplicates if not provided.
    """
    try:
        city = City.objects.get(id=city_id)
        logger.info(f"Starting automatic merge of duplicates for {city.name}")

        # Use provided duplicates data or find them if not provided
        if duplicates_data and duplicates_data.get('status') == 'success':
            duplicates = duplicates_data.get('duplicates', [])
            logger.info(f"Using provided duplicate pairs data")
        else:
            logger.info(f"No duplicate pairs provided, finding them now")
            duplicates_result = find_all_duplicates(city_id)

            if duplicates_result.get('status') != 'success':
                logger.error(f"Failed to find duplicates: {duplicates_result}")
                return duplicates_result

            duplicates = duplicates_result.get('duplicates', [])

        total_pairs = len(duplicates)
        merged_count = 0
        errors = []

        logger.info(f"Found {total_pairs} duplicate pairs to process")

        for i, duplicate_pair in enumerate(duplicates, 1):
            try:
                poi1_id = duplicate_pair['poi1_id']
                poi2_id = duplicate_pair['poi2_id']

                logger.info(f"Processing pair {i}/{total_pairs}: {duplicate_pair['poi1_name']} ↔ {duplicate_pair['poi2_name']}")

                # Get full POI data
                poi1 = PointOfInterest.objects.get(id=poi1_id)
                poi2 = PointOfInterest.objects.get(id=poi2_id)

                # Determine which POI to keep and which to remove using best-value logic
                keep_poi, remove_poi, field_selections = _determine_best_merge(poi1, poi2)

                # Prepare merge data
                merge_data = {
                    'keep_id': keep_poi.id,
                    'remove_id': remove_poi.id,
                    'field_selections': field_selections
                }

                # Make request to poi_merge endpoint
                response = requests.post(
                    f'http://localhost:8000/city/{city.name}/poi/merge/',
                    json=merge_data,
                    headers={'Content-Type': 'application/json'}
                )

                if response.status_code == 200:
                    merged_count += 1
                    logger.info(f"✅ Successfully merged {remove_poi.name} into {keep_poi.name}")
                else:
                    error_msg = f"❌ Merge failed for POIs {poi1_id}/{poi2_id}: {response.text}"
                    logger.error(error_msg)
                    errors.append(error_msg)

            except PointOfInterest.DoesNotExist as e:
                error_msg = f"❌ POI not found for pair {poi1_id}/{poi2_id}: {str(e)}"
                logger.error(error_msg)
                errors.append(error_msg)
            except Exception as e:
                error_msg = f"❌ Error processing pair {poi1_id}/{poi2_id}: {str(e)}"
                logger.error(error_msg)
                errors.append(error_msg)

        logger.info(f"Auto-merge complete for {city.name}: merged {merged_count}/{total_pairs} pairs")

        return {
            'status': 'success',
            'message': f'Processed {total_pairs} duplicate pairs, successfully merged {merged_count}',
            'total_pairs': total_pairs,
            'merged_count': merged_count,
            'errors': errors
        }

    except Exception as e:
        logger.error(f"Error in auto_merge_duplicates task: {str(e)}")
        raise


def _determine_best_merge(poi1, poi2):
    """
    Determine which POI to keep and which to remove, plus field selections for the merge.
    Logic: Choose best values (non-null over null, longer text over shorter, higher rank).

    Returns:
        tuple: (keep_poi, remove_poi, field_selections)
    """

    # Start with poi1 as default keeper
    keep_poi = poi1
    remove_poi = poi2
    field_selections = {}

    # Helper function to choose better value
    def choose_better_value(val1, val2, field_name):
        # Non-null wins over null
        if val1 and not val2:
            return val1
        if val2 and not val1:
            return val2

        # If both are null or both are non-null
        if not val1 and not val2:
            return val1  # Both null, doesn't matter

        # Both have values - apply field-specific logic
        if field_name == 'rank':
            # Lower rank (number) is better
            return min(val1, val2) if val1 is not None and val2 is not None else (val1 or val2)
        elif field_name in ['description', 'address', 'hours']:
            # Longer text is usually better
            str1 = str(val1 or '')
            str2 = str(val2 or '')
            return val1 if len(str1) >= len(str2) else val2
        else:
            # For other fields, prefer poi1's value (arbitrary but consistent)
            return val1

    # Determine best values for each field
    fields_to_compare = [
        'name', 'category', 'sub_category', 'description',
        'latitude', 'longitude', 'address', 'phone',
        'website', 'hours', 'rank'
    ]

    for field in fields_to_compare:
        val1 = getattr(poi1, field, None)
        val2 = getattr(poi2, field, None)

        best_val = choose_better_value(val1, val2, field)

        # If the best value comes from the remove_poi, we need to update field_selections
        if best_val == val2:
            field_selections[field] = best_val

    # Handle district separately (it's a ForeignKey)
    district1 = poi1.district
    district2 = poi2.district

    # Prefer non-null district, or keep poi1's district
    if district2 and not district1:
        field_selections['district'] = district2.name
    elif district1 and district2 and district1 != district2:
        # Both have districts - this is a judgment call, keep poi1's
        pass

    # Handle coordinates as a pair
    if poi1.latitude and poi1.longitude and (not poi2.latitude or not poi2.longitude):
        # poi1 has complete coordinates, poi2 doesn't
        pass
    elif poi2.latitude and poi2.longitude and (not poi1.latitude or not poi1.longitude):
        # poi2 has complete coordinates, poi1 doesn't
        field_selections['coordinates'] = f"{poi2.latitude},{poi2.longitude}"

    logger.info(f"Merge decision: keeping POI {keep_poi.id} ({keep_poi.name}), removing POI {remove_poi.id} ({remove_poi.name})")
    logger.info(f"Field selections: {field_selections}")

    return keep_poi, remove_poi, field_selections


# Data transformation tasks will be added here
