import wikipedia
from typing import Optional, Dict, Union

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
            intro.append(para)
        
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
                intro.append(para)
            
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