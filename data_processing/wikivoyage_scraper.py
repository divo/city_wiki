import requests
import wikitextparser as wtp
from dataclasses import dataclass
from typing import List, Optional
import logging
import mwapi  # MediaWiki API wrapper
from bs4 import BeautifulSoup, Comment

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
        # When True, only collect district links that are explicitly defined in regionlist templates
        # When False, collect all wikilinks from sections titled "Districts" or "Boroughs". This can decend unrelated pages
        self.use_regionlist_districts = False
    
    # from data_processing.wikivoyage_scraper import WikivoyageScraper
    # scraper = WikivoyageScraper()
    # pois = scraper.get_city_data("Paris")
    def get_city_data(self, city_name: str) -> tuple[List[PointOfInterest], List[str], str]:
        """
        Returns a tuple of (points_of_interest, district_pages, about_text)
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
        
        poi_dict = {}  # key: name -> value: POI
        district_pages = set()  # Use a set to automatically deduplicate
        
        # Extract the first two paragraphs of text
        about_text = ""
        paragraphs = []
        for section in parsed.sections:
            if not section.title:  # This is the lead section
                # Split into paragraphs and clean them
                text = section.string
                for template in section.templates:
                    text = text.replace(str(template), '')  # Remove templates
                clean_paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
                paragraphs.extend(clean_paragraphs[:2])  # Take first two paragraphs
                break
        
        if paragraphs:
            about_text = '\n\n'.join(self._clean_text(p) for p in paragraphs)
        
        # Process sections based on the district collection strategy
        for section in parsed.sections:
            if self.use_regionlist_districts:
                category = self._determine_category(section.title)
                if category:
                    self._parse_section(section, category, poi_dict)
                district_pages.update(self._collect_district_pages(section))
            else:
                # Original approach: collect all wikilinks from Districts sections
                if section.title in ["Districts", "Boroughs", " Cities and towns "]:
                    for wikilink in section.wikilinks:
                        if wikilink.title:
                            district_pages.add(wikilink.title)
                else:
                    category = self._determine_category(section.title)
                    if category:
                        self._parse_section(section, category, poi_dict)
        
        return list(poi_dict.values()), list(district_pages), about_text  # Convert back to list before returning
    
    def _determine_category(self, title: str) -> Optional[str]:
        if not title:
            return None
            
        title_lower = title.lower().strip()
        for category, keywords in self.CATEGORIES.items():
            if any(keyword in title_lower for keyword in keywords):
                return category
        return None
    
    def _parse_section(self, section: wtp.Section, category: str, poi_dict: dict = None) -> List[PointOfInterest]:
        """Parse POIs from a section and its subsections, maintaining proper rank ordering.
        
        The function processes templates in bottom-up order:
        1. Process deepest subsections first
        2. Then process parent sections
        
        Note: In WikiTextParser, we've reached a leaf when section.sections returns
        the same content as its parent section.
        """
        if poi_dict is None:
            poi_dict = {}  # key: name -> value: POI
        
        # Process subsections that are different from current section
        for subsection in section.sections:
            if subsection.string != section.string:
                logger.info(f"Processing subsection: {subsection.title} in {section.title}")
                self._parse_section(subsection, category, poi_dict)
        
        # Process templates in current section
        for template in section.templates:
            if template.name.lower().strip() in ['listing', 'see', 'do', 'buy', 'eat', 'drink', 'sleep']:
                poi = self._parse_listing_template(template, category, len(poi_dict) + 1, section.title)
                if poi and poi.name not in poi_dict:
                    logger.info(f"Found POI in {section.title}: {poi.name}")
                    poi_dict[poi.name] = poi
        
        return list(poi_dict.values())
    
    def _get_section_templates(self, section: wtp.Section) -> List[wtp.Template]:
        """Get templates that belong directly to this section, excluding those from subsections."""
        subsection_templates = set()
        for subsection in section.sections:
            subsection_templates.update(template.string for template in subsection.templates)
        
        # Return only templates that aren't in subsections
        return [template for template in section.templates 
                if template.string not in subsection_templates
                and template.name.lower().strip() in ['listing', 'see', 'do', 'buy', 'eat', 'drink', 'sleep']]
    
    def _clean_wiki_links(self, text: str) -> str:
        """Extract the display text from wiki-style links [[link|text]] or [[text]]."""
        result = text
        while '[[' in result and ']]' in result:
            start = result.find('[[')
            end = result.find(']]') + 2
            link_text = result[start+2:end-2]
            # Take text after pipe or full link if no pipe
            display_text = link_text.split('|')[-1]
            result = result[:start] + display_text + result[end:]
        return result

    def _clean_text(self, text: str) -> str:
        """Remove HTML tags, comments, wiki links and clean up whitespace from text."""
        if not text:
            return ""
        
        # First clean wiki links
        text = self._clean_wiki_links(text)
        
        # Then use BeautifulSoup to strip all HTML
        soup = BeautifulSoup(text, 'html.parser')
        
        # Get text content and clean up whitespace
        return ' '.join(soup.get_text().split())

    def _parse_listing_template(self, template: wtp.Template, category: str, rank: int, section_title: str) -> Optional[PointOfInterest]:
        # Extract arguments from template, filtering out empty values
        args = {}
        for arg in template.arguments:
            value = arg.value.strip()
            if value and value != "None":  # Only include non-empty, non-None values
                args[arg.name.strip().lower()] = value
        
        if 'name' not in args:
            return None
        
        # Handle markdown-style links in name field using the helper method
        name = self._clean_wiki_links(args['name'])

        # Parse coordinates if present
        coords = None
        if 'lat' in args and 'long' in args:
            try:
                lat = float(args['lat'])
                lon = float(args['long'])
                coords = (lat, lon)
            except ValueError:
                pass
        
        # Build description from alt and content fields, cleaning HTML comments
        description = self._clean_text(args.get('alt', ''))
        if 'content' in args:
            content = self._clean_text(args['content'])
            description = f"{description} {content}" if description else content
        description = description.strip() or None  # Convert empty string to None

        # Helper function to clean text or return None
        def clean_or_none(value):
            if not value:
                return None
            cleaned = self._clean_text(value)
            return cleaned if cleaned else None

        return PointOfInterest(
            name=name,
            category=category,
            sub_category=section_title,
            description=description,
            coordinates=coords,
            address=clean_or_none(args.get('address')),
            phone=clean_or_none(args.get('phone')),
            website=clean_or_none(args.get('url')),
            hours=clean_or_none(args.get('hours')),
            images=[args['image']] if 'image' in args else [],
            rank=rank
        )

    def _collect_district_pages(self, section: wtp.Section, visited: Optional[set] = None, depth: int = 0, max_depth: int = 10) -> set:
        """Collect district pages from regionlist templates in a section."""
        pages = set()
        
        # First collect all region names from regionlist templates
        region_names = set()
        for template in section.templates:
            if template.name.lower().strip() == 'regionlist':
                for arg in template.arguments:
                    arg_name = arg.name.strip().lower()
                    if arg_name.startswith('region') and arg_name.endswith('name'):
                        region_name = self._clean_wiki_links(arg.value.strip())
                        if region_name:
                            region_names.add(region_name)
        
        # Then find wikilinks that match these region names
        if region_names:
            for wikilink in section.wikilinks:
                if wikilink.title:
                    link_text = self._clean_wiki_links(wikilink.text or wikilink.title)
                    if link_text in region_names:
                        pages.add(wikilink.title)
        
        return pages
