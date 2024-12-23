import requests
import wikitextparser as wtp
from dataclasses import dataclass
from typing import List, Optional
import logging
import mwapi  # MediaWiki API wrapper

@dataclass
class PointOfInterest:
    name: str
    category: str
    description: str
    coordinates: Optional[tuple[float, float]] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    hours: Optional[str] = None
    images: List[str] = None
    rank: int = 0

class WikivoyageScraper:
    CATEGORIES = {
        'see': ['see', 'sight', 'attraction', 'museum'],
        'eat': ['eat', 'restaurant', 'food'],
        'sleep': ['sleep', 'hotel', 'lodging'],
        'shop': ['buy', 'shopping'],
        'drink': ['drink', 'bar', 'nightlife'],
        'play': ['do', 'entertainment', 'activity']
    }
    
    def __init__(self):
        self.session = mwapi.Session('https://en.wikivoyage.org', user_agent='CityWiki/1.0')
    
    # from data_processing.wikivoyage_scraper import WikivoyageScraper
    # scraper = WikivoyageScraper()
    # pois = scraper.get_city_data("Paris")
    def get_city_data(self, city_name: str) -> List[PointOfInterest]:
        # Get the raw wikitext using the MediaWiki API
        response = self.session.get(
            action='parse',
            page=city_name,
            prop=['wikitext'],
            format='json'
        )
        
        if 'error' in response:
            raise Exception(f"Failed to fetch {city_name}: {response['error']}")
            
        wikitext = response['parse']['wikitext']['*']
        parsed = wtp.parse(wikitext)
        
        pois = []
        for section in parsed.sections:
            print(section.title)
            category = self._determine_category(section.title)
            if category:
                pois.extend(self._parse_section(section, category))
        
        return pois
    
    def _determine_category(self, title: str) -> Optional[str]:
        if not title:
            return None
            
        title_lower = title.lower().strip()
        for category, keywords in self.CATEGORIES.items():
            if any(keyword in title_lower for keyword in keywords):
                return category
        return None
    
    def _parse_section(self, section: wtp.Section, category: str) -> List[PointOfInterest]:
        pois = []
        rank = 0
        
        # Parse listing templates
        for template in section.templates:
            if template.name.lower().strip() in ['listing', 'see', 'do', 'buy', 'eat', 'drink', 'sleep']:
                rank += 1
                poi = self._parse_listing_template(template, category, rank)
                if poi:
                    pois.append(poi)
        
        return pois
    
    def _parse_listing_template(self, template: wtp.Template, category: str, rank: int) -> Optional[PointOfInterest]:
        # Extract arguments from template
        args = {arg.name.strip().lower(): arg.value.strip() 
               for arg in template.arguments 
               if arg.value.strip()}
        
        if 'name' not in args:
            return None
            
        # Parse coordinates if present
        coords = None
        if 'lat' in args and 'long' in args:
            try:
                lat = float(args['lat'])
                lon = float(args['long'])
                coords = (lat, lon)
            except ValueError:
                pass
        
        # Build description from alt and content fields
        description = args.get('alt', '')
        if 'content' in args:
            description = f"{description} {args['content']}" if description else args['content']
        
        return PointOfInterest(
            name=args['name'],
            category=category,
            description=description.strip(),
            coordinates=coords,
            address=args.get('address'),
            phone=args.get('phone'),
            website=args.get('url'),
            hours=args.get('hours'),
            images=[args['image']] if 'image' in args else [],
            rank=rank
        )

if __name__ == "__main__":
    # Test the scraper
    scraper = WikivoyageScraper()
    pois = scraper.get_city_data("Paris")
    
    # Print first 3 POIs from each category
    for category in scraper.CATEGORIES.keys():
        print(f"\n=== {category.upper()} ===")
        category_pois = [poi for poi in pois if poi.category == category]
        for poi in category_pois[:3]:
            print(f"\nName: {poi.name}")
            print(f"Description: {poi.description[:100]}...")
            if poi.coordinates:
                print(f"Coordinates: {poi.coordinates}")