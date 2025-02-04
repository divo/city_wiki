import wikipedia
import re
from typing import Optional, Dict, Union

def strip_brackets(text: str) -> str:
    """Remove text within brackets (both square and round) from the text."""
    # First remove square brackets
    text = re.sub(r'\[[^\]]*\]', '', text)
    # Then remove round brackets
    text = re.sub(r'\([^\)]*\)', '', text)
    # Clean up any double spaces created
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def search_wikipedia(query: str, lat: Optional[float] = None, lon: Optional[float] = None) -> Dict[str, Union[str, None]]:
    """
    Search Wikipedia for a query using geosearch if coordinates are provided, falling back to regular search.
    
    Args:
        query (str): The search query
        lat (float, optional): Latitude of the POI
        lon (float, optional): Longitude of the POI
        
    Returns:
        Dict with keys:
            'title': Title of the found article (or None if not found)
            'summary': Summary of the article (or None if not found)
            'url': URL of the article (or None if not found)
    """
    try:
        # Try geosearch first if we have coordinates
        if lat is not None and lon is not None:
            search_results = wikipedia.geosearch(lat, lon, title=query, results=5, radius=20)
        else:
            search_results = wikipedia.search(query, results=1)
        
        if not search_results:
            return {
                'title': None,
                'summary': None,
                'url': None
            }
        
        # Try each result until we find a good match
        for result in search_results:
            try:
                # Get the page for the result
                page = wikipedia.page(result, auto_suggest=False)
                
                # Basic relevance check - if using geosearch, make sure the title contains
                # some part of our query (case insensitive)
                if lat is not None and lon is not None:
                    query_parts = query.lower().split()
                    title_lower = page.title.lower()
                    if not any(part in title_lower for part in query_parts):
                        continue
                
                # Get the content and extract introduction paragraphs
                content = page.content
                intro = []
                for para in content.split('\n'):
                    if para.strip() == '':  # Skip empty lines
                        continue
                    if '==' in para:  # Stop at first section header
                        break
                    # Strip brackets from each paragraph
                    cleaned_para = strip_brackets(para)
                    if cleaned_para:  # Only add if there's content after stripping
                        intro.append(cleaned_para)
                
                summary = '\n\n'.join(intro)
                
                return {
                    'title': page.title,
                    'summary': summary,
                    'url': page.url
                }
            except wikipedia.exceptions.DisambiguationError as e:
                # If we hit a disambiguation page, try the first option
                try:
                    page = wikipedia.page(e.options[0], auto_suggest=False)
                    content = page.content
                    intro = []
                    for para in content.split('\n'):
                        if para.strip() == '':
                            continue
                        if '==' in para:
                            break
                        cleaned_para = strip_brackets(para)
                        if cleaned_para:
                            intro.append(cleaned_para)
                    
                    summary = '\n\n'.join(intro)
                    
                    return {
                        'title': page.title,
                        'summary': summary,
                        'url': page.url
                    }
                except:
                    continue
            except:
                continue
        
        # If we get here, we tried all results but none worked
        return {
            'title': None,
            'summary': None,
            'url': None
        }
            
    except Exception as e:
        print(f"Error searching Wikipedia: {str(e)}")
        
    return {
        'title': None,
        'summary': None,
        'url': None
    } 