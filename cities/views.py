from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from data_processing.wikivoyage_scraper import WikivoyageScraper
from .models import PointOfInterest, City, District, PoiList
from django.db import transaction, models
from .tasks import import_city_data
from celery.result import AsyncResult
from django.contrib import messages
import logging
from django.db.models import Count
import json
from django.forms.models import model_to_dict
from django.core.serializers.json import DjangoJSONEncoder
from . import generation
import reversion
from reversion.models import Version

logger = logging.getLogger(__name__)

def city_list(request):
    cities = City.objects.all()
    return render(request, 'cities/city_list.html', {'cities': cities})

def generate_text_view(request):
    """Render the text generation interface."""
    context = generation.generate_text_view(request)
    return render(request, 'cities/generate.html', context)

@csrf_exempt
@require_http_methods(["POST"])
def generate_text(request, city_name):
    """Generate structured JSON analysis using OpenAI's API based on city data."""
    return generation.generate_text(request, city_name)

@csrf_exempt
@require_http_methods(["POST"])
def generate_list(request, city_name):
    """Generate structured JSON lists of POIs using OpenAI's API."""
    return generation.generate_list(request, city_name)

# TODO: Make this admin only
@csrf_exempt
@require_http_methods(["POST"])
def import_city_data_view(request, city_name):
    try:
        # Start the Celery task
        task = import_city_data.delay(city_name)
        
        return JsonResponse({
            'status': 'success',
            'message': f'Started import for {city_name}',
            'task_id': task.id
        })
        
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)

@require_http_methods(["GET"])
def check_import_status(request, task_id):
    """Check the status of an import task"""
    task_result = AsyncResult(task_id)
    
    if task_result.ready():
        if task_result.successful():
            result = task_result.get()
            return JsonResponse({
                'status': 'completed',
                'result': result
            })
        else:
            return JsonResponse({
                'status': 'failed',
                'error': str(task_result.result)
            }, status=500)
    
    return JsonResponse({
        'status': 'processing'
    })

def city_detail(request, city_name):
    city = get_object_or_404(City, name=city_name)
    
    # Get max_rank filter from query params
    try:
        max_rank = int(request.GET.get('max_rank', 0))
    except ValueError:
        max_rank = 0
    
    # Get district filter
    district_id = request.GET.get('district', '')
    
    # Get sort parameters
    sort_by = request.GET.get('sort', 'name')
    sort_dir = request.GET.get('dir', 'asc')
    
    # Get all districts for the filter dropdown
    districts = city.districts.all().order_by('name')
    
    # Get all POIs for this city, organized by category
    pois_by_category = {}
    category_rank_counts = {}
    for category, _ in PointOfInterest.CATEGORIES:
        # Base query with sorting
        pois = city.points_of_interest.filter(
            category=category
        ).select_related('district')
        
        # Apply rank filter if specified
        if max_rank > 0:
            pois = pois.filter(rank__lte=max_rank)
            
        # Apply district filter if specified
        if district_id:
            if district_id == 'main':
                pois = pois.filter(district__isnull=True)
            else:
                pois = pois.filter(district_id=district_id)
        
        # Apply sorting
        order_by = [f"{'-' if sort_dir == 'desc' else ''}{sort_by}"]
        if sort_by != 'name':  # Add name as secondary sort
            order_by.append('name')
        pois = pois.order_by(*order_by)
        
        pois_by_category[category] = pois
        
        # Count POIs by rank (show all ranks even when filtered)
        rank_counts = list(city.points_of_interest.filter(
            category=category
        ).values('rank').annotate(count=Count('rank')).order_by('rank'))
        category_rank_counts[category] = rank_counts
    
    return render(request, 'cities/city_detail.html', {
        'city': city,
        'pois_by_category': pois_by_category,
        'category_rank_counts': category_rank_counts,
        'max_rank': max_rank,
        'sort_by': sort_by,
        'sort_dir': sort_dir,
        'districts': districts,
        'selected_district': district_id,
    })

@csrf_exempt  # TODO: Replace with proper admin authentication
@require_http_methods(["DELETE"])
def delete_city(request, city_name):
    try:
        city = get_object_or_404(City, name=city_name)
        city.delete()  # This will cascade delete all POIs due to the ForeignKey relationship
        
        return JsonResponse({
            'status': 'success',
            'message': f'Deleted {city_name} and all its points of interest'
        })
        
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)

def import_city(request):
    if request.method == "POST":
        city_name = request.POST.get('city_name')
        try:
            max_depth = int(request.POST.get('max_depth', 2))  # Default to 2 if not provided
            task = import_city_data.delay(city_name, max_depth=max_depth)
            messages.success(request, f'Started import for {city_name} (Task ID: {task.id})')
        except ValueError:
            messages.error(request, 'Invalid max depth value')
        except Exception as e:
            messages.error(request, f'Error importing {city_name}: {str(e)}')
    
    return redirect('city_list')

def city_map(request, city_name):
    city = get_object_or_404(City, name=city_name)
    
    # Get max_rank filter from query params
    try:
        max_rank = int(request.GET.get('max_rank', 0))
    except ValueError:
        max_rank = 0
    
    # Get district filter
    district_id = request.GET.get('district', '')
    
    # Get selected categories (default to all if none selected)
    selected_categories = request.GET.getlist('categories') or [cat[0] for cat in PointOfInterest.CATEGORIES]
    
    # Get all districts for the filter dropdown
    districts = city.districts.all().order_by('name')
    
    # Filter POIs by rank and categories
    pois = city.points_of_interest.filter(category__in=selected_categories)
    if max_rank > 0:
        pois = pois.filter(rank__lte=max_rank)
        
    # Apply district filter if specified
    if district_id:
        if district_id == 'main':
            pois = pois.filter(district__isnull=True)
        else:
            pois = pois.filter(district_id=district_id)
    
    # Find first POI with coordinates to center the map
    center_poi = pois.exclude(latitude=None, longitude=None).first()
    center = {
        'longitude': center_poi.longitude if center_poi else 2.3522,  # Paris default
        'latitude': center_poi.latitude if center_poi else 48.8566
    }
    
    # Get rank counts for the filter UI
    rank_counts = list(city.points_of_interest.filter(category__in=selected_categories)
                      .values('rank')
                      .annotate(count=Count('rank'))
                      .order_by('rank'))
    
    # Get category counts
    category_counts = list(city.points_of_interest.values('category')
                         .annotate(count=Count('category'))
                         .order_by('category'))
    
    # Convert POIs to JSON for the template
    pois_json = json.dumps([{
        'name': poi.name,
        'category': poi.category,
        'sub_category': poi.sub_category,
        'description': poi.description,
        'latitude': poi.latitude,
        'longitude': poi.longitude,
        'address': poi.address,
        'website': poi.website
    } for poi in pois])
    
    return render(request, 'cities/city_map.html', {
        'city': city,
        'pois_json': pois_json,
        'center': center,
        'max_rank': max_rank,
        'rank_counts': rank_counts,
        'categories': PointOfInterest.CATEGORIES,
        'selected_categories': selected_categories,
        'category_counts': {item['category']: item['count'] for item in category_counts},
        'districts': districts,
        'selected_district': district_id,
    })

@require_http_methods(["GET"])
def dump_city(request, city_name):
    """Return a JSON dump of all data for a specific city."""
    try:
        city = get_object_or_404(City, name=city_name)
        
        # Prepare the data structure
        data = {
            'city': model_to_dict(city, exclude=['id']),
            'districts': [],
            'points_of_interest': []
        }

        # Add districts
        for district in city.districts.all():
            district_data = model_to_dict(district, exclude=['id', 'city'])
            if district.parent_district:
                district_data['parent_district'] = district.parent_district.name
            data['districts'].append(district_data)

        # Add POIs - only those with coordinates
        for poi in city.points_of_interest.filter(latitude__isnull=False, longitude__isnull=False):
            poi_data = model_to_dict(poi, exclude=['id', 'city'])
            if poi.district:
                poi_data['district'] = poi.district.name
            data['points_of_interest'].append(poi_data)

        return JsonResponse(data, encoder=DjangoJSONEncoder, json_dumps_params={'indent': 2})
        
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)

@require_http_methods(["GET"])
def city_list_json(request):
    """Return a JSON list of all cities in the database."""
    try:
        cities = City.objects.all()
        city_data = []
        
        for city in cities:
            poi_count = city.points_of_interest.filter(latitude__isnull=False, longitude__isnull=False).count()
            city_data.append({
                'name': city.name,
                'country': city.country,
                'latitude': city.latitude,
                'longitude': city.longitude,
                'district_count': city.districts.count(),
                'poi_count': poi_count,
                'created_at': city.created_at,
                'updated_at': city.updated_at,
            })
            
        return JsonResponse({
            'cities': city_data
        }, encoder=DjangoJSONEncoder, json_dumps_params={'indent': 2})
        
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)

def poi_history(request, city_name, poi_id):
    """Display version history for a POI."""
    poi = get_object_or_404(PointOfInterest, id=poi_id, city__name=city_name)
    
    # Get all versions for this POI
    versions = Version.objects.get_for_object(poi)
    
    # Process versions to show changes
    processed_versions = []
    
    for version in versions:
        try:
            # Try to parse the comment as JSON to get the changes
            comment_data = json.loads(version.revision.comment or '{}')
            changes = comment_data.get('changes', {})
            
            # If no changes found in comment, fall back to comparing with previous version
            if not changes:
                current_data = version.field_dict
                # For initial version, show all fields as new
                changes = {field: {'old': None, 'new': value} 
                          for field, value in current_data.items()}
            
            version.changes = changes
            processed_versions.append(version)
            
        except json.JSONDecodeError:
            # If comment is not JSON, show raw field dict
            version.changes = {field: {'old': None, 'new': value} 
                             for field, value in version.field_dict.items()}
            processed_versions.append(version)
    
    return render(request, 'cities/poi_history.html', {
        'poi': poi,
        'versions': processed_versions,
    })

@require_http_methods(["POST"])
def poi_revert(request, city_name, poi_id, revision_id):
    """Revert a POI to a specific version."""
    poi = get_object_or_404(PointOfInterest, id=poi_id, city__name=city_name)
    revision = get_object_or_404(reversion.models.Revision, id=revision_id)
    
    with reversion.create_revision():
        revision.revert()
        reversion.set_comment(f"Reverted to version from {revision.date_created}")
        if request.user.is_authenticated:
            reversion.set_user(request.user)
    
    messages.success(request, f"Successfully reverted {poi.name} to version from {revision.date_created}")
    return redirect('poi_history', city_name=city_name, poi_id=poi_id)

@csrf_exempt
@require_http_methods(["POST"])
def poi_edit(request, city_name, poi_id):
    """Handle editing of a POI."""
    try:
        poi = get_object_or_404(PointOfInterest, id=poi_id, city__name=city_name)
        
        # Store old values for change tracking
        old_values = {
            'name': poi.name,
            'category': poi.category,
            'sub_category': poi.sub_category,
            'description': poi.description,
            'latitude': poi.latitude,
            'longitude': poi.longitude,
            'address': poi.address,
            'phone': poi.phone,
            'website': poi.website,
            'hours': poi.hours,
            'rank': poi.rank
        }
        
        # Get new values from POST data
        new_values = {
            'name': request.POST.get('name'),
            'category': request.POST.get('category'),
            'sub_category': request.POST.get('sub_category'),
            'description': request.POST.get('description'),
            'latitude': request.POST.get('latitude') or None,
            'longitude': request.POST.get('longitude') or None,
            'address': request.POST.get('address'),
            'phone': request.POST.get('phone'),
            'website': request.POST.get('website'),
            'hours': request.POST.get('hours'),
            'rank': request.POST.get('rank')
        }
        
        # Create a new revision
        with reversion.create_revision():
            # Update fields
            for field, value in new_values.items():
                setattr(poi, field, value)
            
            poi.save()
            
            # Store meta-data including the changes
            changes = {field: {'old': old_values[field], 'new': new_values[field]} 
                      for field, value in new_values.items() 
                      if old_values[field] != new_values[field]}
            
            reversion.set_comment(json.dumps({
                'message': "Updated via edit form",
                'changes': changes
            }))
        
        return JsonResponse({
            'status': 'success',
            'message': 'POI updated successfully'
        })
        
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)

@require_http_methods(["GET"])
def poi_detail(request, city_name, poi_id):
    """Return JSON data for a specific POI."""
    city = get_object_or_404(City, name=city_name)
    poi = get_object_or_404(PointOfInterest, id=poi_id, city=city)
    
    data = {
        'id': poi.id,
        'name': poi.name,
        'category': poi.category,
        'sub_category': poi.sub_category,
        'description': poi.description,
        'latitude': poi.latitude,
        'longitude': poi.longitude,
        'address': poi.address,
        'phone': poi.phone,
        'website': poi.website,
        'hours': poi.hours,
        'rank': poi.rank,
        'district': poi.district.name if poi.district else None
    }
    
    return JsonResponse(data)

@csrf_exempt
@require_http_methods(["POST"])
def poi_merge(request, city_name):
    """Handle merging of two POIs."""
    try:
        # Parse the request data
        data = json.loads(request.body)
        keep_id = data.get('keep_id')
        remove_id = data.get('remove_id')
        field_selections = data.get('field_selections', {})
        
        # Get the POIs
        city = get_object_or_404(City, name=city_name)
        keep_poi = get_object_or_404(PointOfInterest, id=keep_id, city=city)
        remove_poi = get_object_or_404(PointOfInterest, id=remove_id, city=city)
        
        # Store old values for change tracking
        old_values = {
            'name': keep_poi.name,
            'category': keep_poi.category,
            'sub_category': keep_poi.sub_category,
            'description': keep_poi.description,
            'latitude': keep_poi.latitude,
            'longitude': keep_poi.longitude,
            'address': keep_poi.address,
            'phone': keep_poi.phone,
            'website': keep_poi.website,
            'hours': keep_poi.hours,
            'rank': keep_poi.rank,
            'district': keep_poi.district.name if keep_poi.district else None
        }
        
        # Create a new revision for the merge
        with reversion.create_revision():
            # Update fields based on selections
            for field, value in field_selections.items():
                if field == 'coordinates':
                    if value:
                        lat, lon = value.split(',')
                        keep_poi.latitude = float(lat.strip())
                        keep_poi.longitude = float(lon.strip())
                elif field == 'district':
                    if value == 'Main City':
                        keep_poi.district = None
                    else:
                        # Try to find the district by name
                        try:
                            district = District.objects.get(name=value, city=city)
                            keep_poi.district = district
                        except District.DoesNotExist:
                            # If district doesn't exist, create it
                            district = District.objects.create(name=value, city=city)
                            keep_poi.district = district
                else:
                    setattr(keep_poi, field, value)
            
            keep_poi.save()
            
            # Store meta-data including the changes
            changes = {field: {'old': old_values[field], 'new': value} 
                      for field, value in field_selections.items() 
                      if old_values.get(field) != value}
            
            reversion.set_comment(json.dumps({
                'message': f"Merged with POI {remove_id}",
                'changes': changes
            }))
            
            # Delete the removed POI
            remove_poi.delete()
        
        return JsonResponse({
            'status': 'success',
            'message': 'POIs merged successfully'
        })
        
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)

def poi_lists(request, city_name):
    """Display all POI lists for a city."""
    city = get_object_or_404(City, name=city_name)
    poi_lists = city.poi_lists.all()
    
    return render(request, 'cities/poi_lists.html', {
        'city': city,
        'poi_lists': poi_lists,
    })

@csrf_exempt
@require_http_methods(["POST"])
def create_poi_list(request, city_name):
    """Create a new POI list."""
    try:
        data = json.loads(request.body)
        title = data.get('title')
        poi_ids = data.get('poi_ids', [])
        
        if not title:
            return JsonResponse({
                'status': 'error',
                'message': 'Title is required'
            }, status=400)
            
        if not poi_ids:
            return JsonResponse({
                'status': 'error',
                'message': 'At least one POI must be selected'
            }, status=400)
        
        city = get_object_or_404(City, name=city_name)
        
        # Create the list
        poi_list = PoiList.objects.create(
            title=title,
            city=city
        )
        
        # Add POIs to the list
        pois = PointOfInterest.objects.filter(id__in=poi_ids, city=city)
        poi_list.pois.add(*pois)
        
        return JsonResponse({
            'status': 'success',
            'message': 'List created successfully'
        })
        
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)

@csrf_exempt
@require_http_methods(["POST"])
def delete_poi_list(request, city_name, list_id):
    """Delete a POI list."""
    try:
        city = get_object_or_404(City, name=city_name)
        poi_list = get_object_or_404(PoiList, id=list_id, city=city)
        poi_list.delete()
        
        return JsonResponse({
            'status': 'success',
            'message': 'List deleted successfully'
        })
        
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)
