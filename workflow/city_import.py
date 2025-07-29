import os
import django
import logging
from typing import Dict, List, Optional, Any

# Set up Django environment
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "city_wiki.settings")
django.setup()

# Now import Django-related modules
from django.db import models
from prefect import flow, task, pause_flow_run, get_run_logger
from asgiref.sync import sync_to_async
from cities.services.city_import import (
    fetch_city_pois,
    create_or_update_city,
    process_pois,
    create_or_get_district,
    import_city_data as import_city_data_service
)
from cities.enrich_tasks import (
    geocode_city_coordinates, 
    geocode_missing_addresses, 
    geocode_missing_coordinates,
    find_all_duplicates,
    auto_merge_duplicates
)
from cities.models import City

logger = logging.getLogger(__name__)

# Using the simplest pause approach, no need for a custom class


@task(name="fetch_wikivoyage_data", retries=3)
def fetch_wikivoyage_data(city_name: str, depth: int = 0) -> Dict[str, Any]:
    """
    Fetch city data from Wikivoyage.

    Args:
        city_name: Name of the city to fetch
        depth: Current depth in the recursion

    Returns:
        Dictionary with POIs, district pages, and about text
    """
    pois, district_pages, about_text = fetch_city_pois(city_name, depth)

    if pois is None:
        logger.error(f"Error fetching POIs for {city_name}")
        return {
            'status': 'error',
            'city': city_name,
            'error': 'Error fetching POIs'
        }

    return {
        'status': 'success',
        'city': city_name,
        'pois': pois,
        'district_pages': district_pages,
        'about_text': about_text
    }


@task(name="process_city", retries=2)
def process_city(
    data: Dict[str, Any],
    city_name: str,
    root_city_name: Optional[str] = None,
    district_name: Optional[str] = None,
    parent_district_id: Optional[int] = None,
    clear_existing: bool = False
) -> Dict[str, Any]:
    """
    Process city data and save to database.

    Args:
        data: Data from fetch_wikivoyage_data
        city_name: Name of the city
        root_city_name: Name of the root city
        district_name: Name of the district (None for root city)
        parent_district_id: ID of the parent district (None for root districts)
        clear_existing: Whether to clear existing POIs

    Returns:
        Dictionary with status information
    """
    if data.get('status') == 'error':
        return data

    if not root_city_name:
        root_city_name = city_name

    # Create/update the city
    city = create_or_update_city(
        city_name=city_name,
        root_city_name=root_city_name,
        about_text=data.get('about_text')
    )

    # Process POIs
    db_pois = process_pois(
        city=city,
        pois=data.get('pois', []),
        clear_existing=clear_existing,
        district_name=district_name,
        parent_district_id=parent_district_id
    )

    return {
        'status': 'success',
        'city': city_name,
        'root_city': root_city_name,
        'district': district_name,
        'pois_count': len(db_pois),
        'district_pages': data.get('district_pages', [])
    }


@task(name="import_district", retries=2)
def import_district(
    district_name: str,
    root_city_name: str,
    current_depth: int = 1,
    max_depth: int = 2,
    parent_district_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Import a district from Wikivoyage.

    Args:
        district_name: Name of the district to import
        root_city_name: Name of the root city
        current_depth: Current depth in the recursion
        max_depth: Maximum depth to recurse
        parent_district_id: ID of the parent district

    Returns:
        Dictionary with status information
    """
    logger.info(f"Importing district {district_name} (part of {root_city_name}, depth: {current_depth}/{max_depth})")

    # Fetch data for this district
    data = fetch_wikivoyage_data(district_name, current_depth)

    # Process the district data
    result = process_city(
        data=data,
        city_name=district_name,
        root_city_name=root_city_name,
        district_name=district_name,
        parent_district_id=parent_district_id,
        clear_existing=False
    )

    # If we haven't reached max_depth, process sub-districts
    if current_depth < max_depth and result['status'] == 'success':
        # Get the district ID
        try:
            from cities.models import District
            district = District.objects.get(name=district_name.split('/')[-1], city__name=root_city_name)
            district_id = district.id

            # Process each sub-district
            for sub_district in result.get('district_pages', []):
                import_district(
                    district_name=sub_district,
                    root_city_name=root_city_name,
                    current_depth=current_depth + 1,
                    max_depth=max_depth,
                    parent_district_id=district_id
                )
        except District.DoesNotExist:
            logger.warning(f"District {district_name} not found for city {root_city_name}")

    return result

def import_wikivoyage_data(name: str, max_depth: int = 2) -> Dict[str, Any]:
    # Fetch data for the main city
    data = fetch_wikivoyage_data(name, 0)

    # Process the city data
    result = process_city(
        data=data,
        city_name=name,
        clear_existing=True  # Clear existing POIs for the root city
    )

    # Process districts if successful
    if result['status'] == 'success' and max_depth > 0:
        district_pages = result.get('district_pages', [])
        logger.info(f"Found {len(district_pages)} districts for {name}")

        # Import each district
        for district in district_pages:
            import_district(
                district_name=district,
                root_city_name=name,
                current_depth=1,
                max_depth=max_depth
            )

    return result



async def _import_city_data(name: str, max_depth: int = 2) -> Dict[str, Any]:
    """
    Import city data using the synchronous import function.

    Args:
        name: Name of the city to import
        max_depth: Maximum depth to recurse for districts

    Returns:
        Dictionary with import results
    """
    logger = get_run_logger()
    logger.info(f"Importing city data for {name} (max_depth: {max_depth})")

    # Use sync_to_async to properly bridge Django's sync code with our async flow
    import_async = sync_to_async(import_wikivoyage_data, thread_sensitive=True)
    result = await import_async(name, max_depth)

    # Ensure result is a dictionary
    if not isinstance(result, dict):
        result = dict(result)

    return result


async def _geocode_city(name: str, result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Geocode the city coordinates.

    Args:
        name: Name of the city
        result: Result dictionary from import

    Returns:
        Updated result dictionary with geocoding information
    """
    logger = get_run_logger()
    logger.info(f"Geocoding coordinates for city: {name}")

    try:
        # First, get the city ID - wrap in sync_to_async to safely use Django ORM in async context
        get_city = sync_to_async(City.objects.get, thread_sensitive=True)
        city = await get_city(name=name)

        # Then geocode the city coordinates - wrap in sync_to_async to safely call in async context
        geocode_async = sync_to_async(geocode_city_coordinates, thread_sensitive=True)
        geocode_result = await geocode_async(city.id)

        # Add geocoding result to our main result
        result['geocoding'] = geocode_result

        logger.info(f"Geocoded coordinates for {name}: {geocode_result.get('status', 'unknown')}")
    except City.DoesNotExist:
        logger.error(f"City {name} not found in database for geocoding")
        result['geocoding'] = {'status': 'error', 'message': f"City {name} not found in database"}
    except Exception as e:
        logger.error(f"Error geocoding city coordinates: {str(e)}")
        result['geocoding'] = {'status': 'error', 'message': str(e)}

    return result


async def _geocode_missing_addresses(name: str, result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Geocode missing addresses for POIs with coordinates.

    Args:
        name: Name of the city
        result: Result dictionary from import and geocoding

    Returns:
        Updated result dictionary with address geocoding information
    """
    logger = get_run_logger()
    logger.info(f"Geocoding missing addresses for POIs in {name}")

    try:
        # Get the city ID
        get_city = sync_to_async(City.objects.get, thread_sensitive=True)
        city = await get_city(name=name)

        # Geocode missing addresses
        geocode_addresses_async = sync_to_async(geocode_missing_addresses, thread_sensitive=True)
        addresses_result = await geocode_addresses_async(city.id)

        # Add address geocoding result to our main result
        result['address_geocoding'] = addresses_result

        logger.info(f"Address geocoding for {name}: {addresses_result.get('status', 'unknown')}, "
                   f"Updated {addresses_result.get('updated_count', 0)} POIs")
    except City.DoesNotExist:
        logger.error(f"City {name} not found in database for address geocoding")
        result['address_geocoding'] = {'status': 'error', 'message': f"City {name} not found in database"}
    except Exception as e:
        logger.error(f"Error geocoding addresses: {str(e)}")
        result['address_geocoding'] = {'status': 'error', 'message': str(e)}

    return result


async def _geocode_missing_coordinates(name: str, result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Geocode missing coordinates for POIs with addresses.

    Args:
        name: Name of the city
        result: Result dictionary from import and geocoding

    Returns:
        Updated result dictionary with coordinate geocoding information
    """
    logger = get_run_logger()
    logger.info(f"Geocoding missing coordinates for POIs in {name}")

    try:
        # Get the city ID
        get_city = sync_to_async(City.objects.get, thread_sensitive=True)
        city = await get_city(name=name)

        # Geocode missing coordinates
        geocode_coords_async = sync_to_async(geocode_missing_coordinates, thread_sensitive=True)
        coordinates_result = await geocode_coords_async(city.id)

        # Add coordinate geocoding result to our main result
        result['coordinate_geocoding'] = coordinates_result

        logger.info(f"Coordinate geocoding for {name}: {coordinates_result.get('status', 'unknown')}, "
                   f"Updated {coordinates_result.get('updated_count', 0)} POIs")
    except City.DoesNotExist:
        logger.error(f"City {name} not found in database for coordinate geocoding")
        result['coordinate_geocoding'] = {'status': 'error', 'message': f"City {name} not found in database"}
    except Exception as e:
        logger.error(f"Error geocoding coordinates: {str(e)}")
        result['coordinate_geocoding'] = {'status': 'error', 'message': str(e)}

    return result


async def _find_duplicates(name: str, result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Find potential duplicate POIs in the city.

    Args:
        name: Name of the city
        result: Result dictionary from import and geocoding

    Returns:
        Updated result dictionary with duplicate detection information
    """
    logger = get_run_logger()
    logger.info(f"Detecting duplicate POIs in {name}")

    try:
        # Get the city ID
        get_city = sync_to_async(City.objects.get, thread_sensitive=True)
        city = await get_city(name=name)

        # Find duplicates
        find_duplicates_async = sync_to_async(find_all_duplicates, thread_sensitive=True)
        duplicates_result = await find_duplicates_async(city.id)

        # Add duplicates result to our main result
        result['duplicates'] = duplicates_result

        logger.info(f"Duplicate detection for {name}: {duplicates_result.get('status', 'unknown')}, "
                   f"Found {len(duplicates_result.get('duplicates', []))} potential duplicate pairs")
    except City.DoesNotExist:
        logger.error(f"City {name} not found in database for duplicate detection")
        result['duplicates'] = {'status': 'error', 'message': f"City {name} not found in database"}
    except Exception as e:
        logger.error(f"Error finding duplicates: {str(e)}")
        result['duplicates'] = {'status': 'error', 'message': str(e)}

    return result


async def _auto_merge_duplicates(name: str, result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Automatically merge duplicate POIs using best-value logic.
    Uses the duplicates data from the previous step to avoid redundant work.

    Args:
        name: Name of the city
        result: Result dictionary from import and geocoding (should contain 'duplicates' key)

    Returns:
        Updated result dictionary with auto-merge information
    """
    logger = get_run_logger()
    logger.info(f"Auto-merging duplicate POIs in {name}")

    try:
        # Get the city ID
        get_city = sync_to_async(City.objects.get, thread_sensitive=True)
        city = await get_city(name=name)

        # Get duplicates data from previous step
        duplicates_data = result.get('duplicates')
        
        if not duplicates_data or duplicates_data.get('status') != 'success':
            logger.warning(f"No valid duplicates data found for {name}, skipping auto-merge")
            result['auto_merge'] = {'status': 'skipped', 'message': 'No valid duplicates data available'}
            return result

        # Auto-merge duplicates using the existing data
        auto_merge_async = sync_to_async(auto_merge_duplicates, thread_sensitive=True)
        merge_result = await auto_merge_async(city.id, duplicates_data)

        # Add merge result to our main result
        result['auto_merge'] = merge_result

        logger.info(f"Auto-merge for {name}: {merge_result.get('status', 'unknown')}, "
                   f"Merged {merge_result.get('merged_count', 0)}/{merge_result.get('total_pairs', 0)} pairs")
    except City.DoesNotExist:
        logger.error(f"City {name} not found in database for auto-merge")
        result['auto_merge'] = {'status': 'error', 'message': f"City {name} not found in database"}
    except Exception as e:
        logger.error(f"Error auto-merging duplicates: {str(e)}")
        result['auto_merge'] = {'status': 'error', 'message': str(e)}

    return result


def _format_initial_confirmation_message(name: str, result: Dict[str, Any]) -> str:
    """
    Format an initial confirmation message for the user after data import.

    Args:
        name: Name of the city
        result: Result dictionary with import data

    Returns:
        Formatted message string
    """
    message = (f"City import complete for {name}. "
              f"Imported {result.get('pois_count', 0)} POIs for the main city and "
              f"processed {len(result.get('district_pages', []))} districts. "
              f"Would you like to proceed with geocoding coordinates and addresses?")

    return message


def _format_geocoding_confirmation_message(name: str, result: Dict[str, Any]) -> str:
    """
    Format a confirmation message after geocoding operations.

    Args:
        name: Name of the city
        result: Result dictionary with geocoding results

    Returns:
        Formatted message string
    """
    # City geocoding info
    city_msg = ""
    if result.get('geocoding', {}).get('status') == 'success':
        coords = result.get('geocoding', {}).get('coordinates', {})
        lat = coords.get('latitude')
        lng = coords.get('longitude')
        city_msg = f"City coordinates set to ({lat}, {lng})."

    # Address geocoding info
    address_msg = ""
    if result.get('address_geocoding', {}).get('status') == 'success':
        updated = result.get('address_geocoding', {}).get('updated_count', 0)
        processed = result.get('address_geocoding', {}).get('processed_count', 0)
        address_msg = f"Updated addresses for {updated} out of {processed} POIs."

    # Coordinate geocoding info
    coord_msg = ""
    if result.get('coordinate_geocoding', {}).get('status') == 'success':
        updated = result.get('coordinate_geocoding', {}).get('updated_count', 0)
        processed = result.get('coordinate_geocoding', {}).get('processed_count', 0)
        coord_msg = f"Updated coordinates for {updated} out of {processed} POIs."

    # Duplicate detection info
    dup_msg = ""
    duplicate_list = ""
    if result.get('duplicates', {}).get('status') == 'success':
        duplicates = result.get('duplicates', {}).get('duplicates', [])
        dups = len(duplicates)
        dup_msg = f"Found {dups} potential duplicate pairs that may need review."
        
        # Add detailed list of duplicates if any were found
        if dups > 0:
            duplicate_list = "\n\nDetailed duplicate pairs:\n"
            for i, dup in enumerate(duplicates, 1):
                duplicate_list += (f"{i}. {dup.get('poi1_name', 'Unknown')} ↔ {dup.get('poi2_name', 'Unknown')} "
                                  f"(Reason: {dup.get('reason', 'Unknown')}, "
                                  f"IDs: {dup.get('poi1_id', 'Unknown')}/{dup.get('poi2_id', 'Unknown')})\n")

    # Auto-merge info
    merge_msg = ""
    if result.get('auto_merge', {}).get('status') == 'success':
        merged = result.get('auto_merge', {}).get('merged_count', 0)
        total = result.get('auto_merge', {}).get('total_pairs', 0)
        errors = len(result.get('auto_merge', {}).get('errors', []))
        merge_msg = f"Auto-merged {merged} out of {total} duplicate pairs ({errors} errors)."

    message = (f"Geocoding and deduplication complete for {name}.\n\n"
              f"{city_msg}\n"
              f"{address_msg}\n"
              f"{coord_msg}\n"
              f"{dup_msg}{duplicate_list}\n"
              f"{merge_msg}\n"
              f"Would you like to continue with the import process?")

    return message


async def _get_user_confirmation(message: str, result: Dict[str, Any], step: str = "import") -> Dict[str, Any]:
    """
    Pause the flow and get user confirmation.
    
    Args:
        message: Message to display to the user
        result: Result dictionary to update with confirmation
        step: The current step requiring confirmation
        
    Returns:
        Updated result dictionary with confirmation information
    """
    logger = get_run_logger()
    logger.info(message)
    
    try:
        # Use the simplest form with a single bool input
        confirmation = await pause_flow_run(
            wait_for_input=bool
        )
        
        # Add confirmation to the result with the specific step
        result[f'{step}_confirmed'] = confirmation
        logger.info(f"User confirmation for {step}: {confirmation}")
        
        # If confirmed, return success message
        if confirmation:
            logger.info(f"User confirmed the {step}")
        else:
            logger.info(f"User did NOT confirm the {step}")
            
    except Exception as e:
        logger.error(f"Error during {step} confirmation: {str(e)}")
        result[f'{step}_confirmed'] = False
        result[f'{step}_confirmation_error'] = str(e)
    
    return result


@flow(name="import_city", version="1.0")
async def import_city(name: str, max_depth: int = 2) -> Dict[str, Any]:
    """
    Import a city and its districts from Wikivoyage.
    
    Args:
        name: Name of the city to import
        max_depth: Maximum depth to recurse for districts
        
    Returns:
        Dictionary with status information
    """
    logger = get_run_logger()
    logger.info(f"Starting import flow for city: {name} (max_depth: {max_depth})")

    # Step 1: Import city data
    result = await _import_city_data(name, max_depth)

    # Step 2: Format initial confirmation message
    message = _format_initial_confirmation_message(name, result)

    # Step 3: Get user confirmation before proceeding with geocoding
    result = await _get_user_confirmation(message, result, step="import")
    
    # Only proceed with geocoding if user confirmed
    if result.get('import_confirmed', False):
        logger.info(f"User confirmed import for {name}, proceeding with geocoding")
        
        # Step 4: Geocode city coordinates
        result = await _geocode_city(name, result)
        
        # Step 5: Geocode missing addresses for POIs
        result = await _geocode_missing_addresses(name, result)
        
        # Step 6: Geocode missing coordinates for POIs
        result = await _geocode_missing_coordinates(name, result)
        
        # Step 7: Find duplicate POIs
        result = await _find_duplicates(name, result)
        
        # Step 8: Auto-merge duplicate POIs
        result = await _auto_merge_duplicates(name, result)
        
        # Step 9: Format geocoding confirmation message
        message = _format_geocoding_confirmation_message(name, result)
        
        # Step 10: Get final user confirmation
        result = await _get_user_confirmation(message, result, step="geocoding")
    else:
        logger.info(f"User did not confirm import for {name}, skipping geocoding steps")

    return result


if __name__ == "__main__":
    import asyncio

    # For local testing
    # asyncio.run(import_city("Paris"))

    # For deployment
    import_city.serve(
        name="import-city-wikivoyage",
        tags=["city", "wikivoyage"],
    )
