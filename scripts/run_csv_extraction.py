#!/usr/bin/env python
"""
Script to run extraction with a CSV file
"""
import os
import sys
import logging
import argparse
import asyncio
from dotenv import load_dotenv

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.config.config import AzureConfig
from src.extractors.azure_test_extractor import AzureTestExtractor
from src.utils.csv_parser import AzureTestPlanCSVParser

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('extraction.log')
    ]
)
logger = logging.getLogger(__name__)

async def main():
    """
    Main function to run the extraction with a CSV file
    """
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Extract Azure Test Plans data based on a CSV file')
    parser.add_argument('csv_file', help='Path to the CSV file containing Azure Test Plan URLs')
    parser.add_argument('--modular', action='store_true', help='Generate modular output files (one per test plan)')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    args = parser.parse_args()

    # Set logging level
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    # Load environment variables
    load_dotenv()

    # Validate that the CSV file exists
    if not os.path.isfile(args.csv_file):
        logger.error(f"CSV file not found: {args.csv_file}")
        sys.exit(1)

    # Create an instance of the extractor
    logger.info(f"Starting extraction from CSV file: {args.csv_file}")
    logger.info(f"Modular output: {'Enabled' if args.modular else 'Disabled'}")
    
    # Load configuration
    config = AzureConfig()
    logger.info(f"Using project: {config.project_name}")
    
    # Initialize extractor
    extractor = AzureTestExtractor(config)

    try:
        # Extract data from the CSV
        results = await extractor.extract_from_csv(args.csv_file, modular_output=args.modular)
        
        # Log extraction summary
        logger.info("Extraction completed successfully!")
        for entity_type, entities in results.items():
            if entity_type not in ["csv_mapping", "extraction_path"]:
                count = len(entities) if isinstance(entities, list) else 1
                logger.info(f"  Extracted {count} {entity_type}")
        
        # Log the path to the extracted data
        logger.info(f"Extraction directory: {results.get('extraction_path', 'Unknown')}")
        
        if args.modular:
            logger.info(f"Modular output created in: {os.path.join(results.get('extraction_path', ''), 'modular')}")
        
    except Exception as e:
        logger.error(f"Error during extraction: {str(e)}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main()) 