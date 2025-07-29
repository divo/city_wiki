#!/usr/bin/env python
"""
Script to run the city import Prefect workflow.

This script can be used to manually trigger a city import workflow
without using Prefect's deployment infrastructure.

Usage:
    python run_import.py --city "Paris" --depth 2
"""

import os
import argparse
import django
import logging
from datetime import datetime

# Set up Django environment
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "city_wiki.settings")
django.setup()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import the flow after Django is configured
from city_import import import_city


def main():
    """Run the city import workflow based on command line arguments."""
    parser = argparse.ArgumentParser(description='Run city import workflow')
    parser.add_argument('--city', required=True, help='Name of city to import')
    parser.add_argument('--depth', type=int, default=2, help='Maximum depth for district recursion')
    
    args = parser.parse_args()
    
    # Log start of workflow
    start_time = datetime.now()
    logger.info(f"Starting import workflow for {args.city} at {start_time}")
    
    try:
        # Run the flow synchronously
        result = import_city(name=args.city, max_depth=args.depth)
        
        # Log completion
        end_time = datetime.now()
        duration = end_time - start_time
        
        if result.get('status') == 'success':
            logger.info(f"Workflow completed successfully in {duration}")
            stats = result.get('statistics', {})
            if stats:
                logger.info(f"Imported {stats.get('total_pois', 0)} POIs for {args.city}")
                
                # Print any validation warnings
                warnings = stats.get('validation', {}).get('warnings', [])
                if warnings:
                    logger.warning(f"Found {len(warnings)} validation warnings:")
                    for warning in warnings:
                        logger.warning(f"  - {warning}")
        else:
            logger.error(f"Workflow failed: {result.get('error', 'Unknown error')}")
            
    except Exception as e:
        logger.exception(f"Error running workflow: {str(e)}")
        return 1
        
    return 0


if __name__ == "__main__":
    exit_code = main()
    exit(exit_code)