from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.contrib import messages
from django.db.models import Count
from django.forms.models import model_to_dict
from django.core.serializers.json import DjangoJSONEncoder
import json

from ..models import City, PointOfInterest
from ..fetch_tasks import import_city_data
from celery.result import AsyncResult

import logging
logger = logging.getLogger(__name__)


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
        reversion.set_comment(f"Reverted to version from {
                              revision.date_created}")
        if request.user.is_authenticated:
            reversion.set_user(request.user)

    messages.success(request, f"Successfully reverted {
                     poi.name} to version from {revision.date_created}")
    return redirect('poi_history', city_name=city_name, poi_id=poi_id)


@csrf_exempt
@require_http_methods(["POST"])
def poi_edit(request, city_name, poi_id):
    """Handle editing of a POI."""
    try:
        poi = get_object_or_404(
            PointOfInterest, id=poi_id, city__name=city_name)

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
        remove_poi = get_object_or_404(
            PointOfInterest, id=remove_id, city=city)

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
                            district = District.objects.get(
                                name=value, city=city)
                            keep_poi.district = district
                        except District.DoesNotExist:
                            # If district doesn't exist, create it
                            district = District.objects.create(
                                name=value, city=city)
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







@csrf_exempt
@require_http_methods(["POST"])
def fetch_poi_image(request, city_name, poi_id):
    """Fetch image URLs for a POI without saving any."""
    try:
        city = get_object_or_404(City, name=city_name)
        poi = get_object_or_404(PointOfInterest, id=poi_id, city=city)

        # Get images from both sources
        wikimedia_result = _fetch_wikimedia_images(poi.name)
        pixabay_result = _fetch_pixabay_images(poi.name)

        # Combine results
        result = _combine_image_results(wikimedia_result, pixabay_result)
        return JsonResponse(result, status=404 if result['status'] == 'error' else 200)

    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def save_poi_image(request, city_name, poi_id):
    """Save a specific image URL for a POI."""
    try:
        city = get_object_or_404(City, name=city_name)
        poi = get_object_or_404(PointOfInterest, id=poi_id, city=city)

        data = json.loads(request.body)
        image_url = data.get('image_url')

        if not image_url:
            return JsonResponse({
                'status': 'error',
                'message': 'Image URL is required'
            }, status=400)

        # Save the image URL
        poi.image_url = image_url
        poi.save()

        return JsonResponse({
            'status': 'success',
            'message': 'Image URL saved'
        })

    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def delete_poi_image(request, city_name, poi_id):
    """Delete the image URL from a POI."""
    try:
        city = get_object_or_404(City, name=city_name)
        poi = get_object_or_404(PointOfInterest, id=poi_id, city=city)

        # Clear the image URL
        poi.image_url = None
        poi.save()

        return JsonResponse({
            'status': 'success',
            'message': 'Image URL removed'
        })

    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)



