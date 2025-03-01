import asyncio
import logging
import argparse
from datetime import datetime
from pathlib import Path
from config.config import AzureConfig
from extractors.azure_test_extractor import AzureTestExtractor
from utils.json_utils import save_json_data

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def main():
    # Set up argument parser
    parser = argparse.ArgumentParser(description='Azure Test Plans to Xray Migration')
    parser.add_argument('--csv', help='Path to CSV file containing Azure Test Plan URLs', default=None)
    parser.add_argument('--modular', action='store_true', help='Generate modular output files (one per test plan)')
    args = parser.parse_args()
    
    logger.info("Starting Azure Test Plans to Xray Migration")
    
    # Load configuration
    config = AzureConfig()
    logger.info(f"Loaded configuration for project: {config.project_name}")
    
    # Initialize the extractor
    extractor = AzureTestExtractor(config)
    
    # Extract data based on whether a CSV file was provided
    extraction_result = None
    if args.csv:
        logger.info(f"Extracting specific test plans from CSV: {args.csv}")
        logger.info(f"Modular output: {'Enabled' if args.modular else 'Disabled'}")
        extraction_result = await extractor.extract_from_csv(args.csv, modular_output=args.modular)
    else:
        logger.info("Extracting all test plans")
        extraction_result = await extractor.extract_all()
    
    # Print summary of extracted data
    logger.info("Extraction completed successfully")
    for entity_type, entities in extraction_result.items():
        if entity_type not in ["csv_mapping", "extraction_path"]:  # Skip csv_mapping and extraction_path in the count summary
            count = len(entities) if isinstance(entities, list) else 1
            logger.info(f"  Extracted {count} {entity_type}")
    
    logger.info(f"Azure Test Plans data extraction has been completed successfully")
    logger.info(f"The extracted data is saved in: {extraction_result.get('extraction_path', 'Unknown')}")
    logger.info("The extracted data is ready for mapping to Xray format")

if __name__ == "__main__":
    asyncio.run(main()) 