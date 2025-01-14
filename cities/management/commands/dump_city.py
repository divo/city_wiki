from django.core.management.base import BaseCommand
from cities.models import City, District, PointOfInterest
import json
from django.core.serializers.json import DjangoJSONEncoder
from django.forms.models import model_to_dict

# Example: python manage.py dump_city "Paris" --output paris_data.json
class Command(BaseCommand):
    help = 'Dumps all data for a specific city in JSON format'

    def add_arguments(self, parser):
        parser.add_argument('city_name', type=str, help='Name of the city to dump')
        parser.add_argument('--output', type=str, help='Output file path (optional)')

    def handle(self, *args, **options):
        city_name = options['city_name']
        output_file = options.get('output')

        try:
            city = City.objects.get(name=city_name)
        except City.DoesNotExist:
            self.stderr.write(self.style.ERROR(f'City "{city_name}" not found'))
            return

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

        # Add POIs
        for poi in city.points_of_interest.all():
            poi_data = model_to_dict(poi, exclude=['id', 'city'])
            if poi.district:
                poi_data['district'] = poi.district.name
            data['points_of_interest'].append(poi_data)

        # Convert to JSON
        json_data = json.dumps(data, cls=DjangoJSONEncoder, indent=2)

        if output_file:
            with open(output_file, 'w') as f:
                f.write(json_data)
            self.stdout.write(self.style.SUCCESS(f'Data written to {output_file}'))
        else:
            self.stdout.write(json_data) 