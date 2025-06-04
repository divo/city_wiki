import os
import django
import logging
from typing import Dict, List, Optional, Any

# Set up Django environment
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "city_wiki.settings")
django.setup()

# Now import Django-related modules
from django.db import models
from prefect import flow, task
from cities.services.city_import import (
    fetch_city_pois,
    create_or_update_city,
    process_pois,
    create_or_get_district,
    import_city_data as import_city_data_service
)

logger = logging.getLogger(__name__)


@task(name="fetch_wikivoyage_data")
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


@task(name="process_city")
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


@flow(name="import_district")
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



@flow(name="import_city")
def import_city(name: str, max_depth: int = 2) -> Dict[str, Any]:
    """
    Import a city and its districts from Wikivoyage.

    Args:
        name: Name of the city to import
        max_depth: Maximum depth to recurse for districts

    Returns:
        Dictionary with status information
    """
    logger.info(f"Starting import flow for city: {name} (max_depth: {max_depth})")
    result = import_wikivoyage_data(name, max_depth)

    return result


if __name__ == "__main__":
    import_city.deploy(
        name="import-city-wikivoyage-deployment",
        work_pool_name="city-import-pool",
        image="city-import-image",
        push=False
    )
