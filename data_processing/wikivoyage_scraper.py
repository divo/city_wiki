import requests
import wikitextparser as wtp
from dataclasses import dataclass
from typing import List, Optional
import logging
import mwapi  # MediaWiki API wrapper

logger = logging.getLogger(__name__)

@dataclass
class PointOfInterest:
    name: str
    category: str
    sub_category: Optional[str]
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
    def get_city_data(self, city_name: str) -> tuple[List[PointOfInterest], List[str]]:
        """
        Returns a tuple of (points_of_interest, district_pages)
        """
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
        district_pages = set()  # Use a set to automatically deduplicate
        
        for section in parsed.sections:
            if section.title == "Districts":
                for wikilink in section.wikilinks:
                    district_pages.add(wikilink.title)
            else:
                category = self._determine_category(section.title)
                if category:
                    pois.extend(self._parse_section(section, category))
        
        return pois, list(district_pages)  # Convert back to list before returning
    
    def _determine_category(self, title: str) -> Optional[str]:
        if not title:
            return None
            
        title_lower = title.lower().strip()
        for category, keywords in self.CATEGORIES.items():
            if any(keyword in title_lower for keyword in keywords):
                return category
        return None
    
    def _parse_section(self, section: wtp.Section, category: str) -> List[PointOfInterest]:
        """Parse POIs from a section and its subsections, maintaining proper rank ordering.
        
        The function processes templates in bottom-up order:
        1. Process deepest subsections first
        2. Then process parent sections
        
        Note: In WikiTextParser, we've reached a leaf when section.sections returns
        the same content as its parent section.
        """
        pois = []
        seen_pois = set()  # Track POIs by (name, coords) to avoid duplicates
        rank = 0
        
        # Process subsections that are different from current section
        for subsection in section.sections:
            if subsection.string != section.string:
                logger.info(f"Processing subsection: {subsection.title} in {section.title}")
                subsection_pois = self._parse_section(subsection, category)
                for poi in subsection_pois:
                    poi_key = (poi.name, poi.coordinates if poi.coordinates else None)
                    if poi_key not in seen_pois:
                        seen_pois.add(poi_key)
                        rank += 1
                        poi.rank = rank
                        pois.append(poi)
        
        # Process templates in current section
        for template in section.templates:
            if template.name.lower().strip() in ['listing', 'see', 'do', 'buy', 'eat', 'drink', 'sleep']:
                poi = self._parse_listing_template(template, category, rank + 1, section.title)
                if poi:
                    poi_key = (poi.name, poi.coordinates if poi.coordinates else None)
                    if poi_key not in seen_pois:
                        seen_pois.add(poi_key)
                        rank += 1
                        poi.rank = rank
                        logger.info(f"Found POI in {section.title}: {poi.name}")
                        pois.append(poi)
        
        return pois
    
    def _get_section_templates(self, section: wtp.Section) -> List[wtp.Template]:
        """Get templates that belong directly to this section, excluding those from subsections."""
        subsection_templates = set()
        for subsection in section.sections:
            subsection_templates.update(template.string for template in subsection.templates)
        
        # Return only templates that aren't in subsections
        return [template for template in section.templates 
                if template.string not in subsection_templates
                and template.name.lower().strip() in ['listing', 'see', 'do', 'buy', 'eat', 'drink', 'sleep']]
    
    def _parse_listing_template(self, template: wtp.Template, category: str, rank: int, section_title: str) -> Optional[PointOfInterest]:
        # Extract arguments from template
        args = {arg.name.strip().lower(): arg.value.strip() 
               for arg in template.arguments 
               if arg.value.strip()}
        
        if 'name' not in args:
            return None
        
        # Handle markdown-style links in name field
        # TODO: Might want to store the link so I can parse it later
        name = args['name']
        if '[[' in name and ']]' in name:
            # Extract text between [[ and ]]
            name = name.split('[[')[-1].split(']]')[0]
            # If there's a pipe character, take the text after it
            if '|' in name:
                name = name.split('|')[1]

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
            name=name,  # Use the cleaned name
            category=category,
            sub_category=section_title,
            description=description.strip(),
            coordinates=coords,
            address=args.get('address'),
            phone=args.get('phone'),
            website=args.get('url'),
            hours=args.get('hours'),
            images=[args['image']] if 'image' in args else [],
            rank=rank
        )
