from django import template
import pprint

register = template.Library()

@register.filter
def get_item(dictionary, key):
    """Get an item from a dictionary using bracket notation in templates"""
    return dictionary.get(key, None)

@register.filter
def items(dictionary):
    """Convert dictionary to items for iteration"""
    return dictionary.items() 

@register.filter
def pprint(value):
    """Pretty print a value for debugging"""
    return pprint.pformat(value, indent=2) 

@register.filter
def split(value, arg):
    """Split a string and return the list"""
    return value.split(arg) 