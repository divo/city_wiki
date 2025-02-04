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

def search_wikipedia(query: str) -> Dict[str, Union[str, None]]:
    """
    Search Wikipedia for a query and return the introduction paragraphs of the best matching article.
    
    Args:
        query (str): The search query
        
    Returns:
        Dict with keys:
            'title': Title of the found article (or None if not found)
            'summary': Summary of the article (or None if not found)
            'url': URL of the article (or None if not found)
    """
    try:
        # Search for the query
        search_results = wikipedia.search(query, results=1)
        
        if not search_results:
            return {
                'title': None,
                'summary': None,
                'url': None
            }
        
        # Get the page for the first result
        page = wikipedia.page(search_results[0], auto_suggest=False)
        
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
            pass
            
    except Exception as e:
        print(f"Error searching Wikipedia: {str(e)}")
        
    return {
        'title': None,
        'summary': None,
        'url': None
    }