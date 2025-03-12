import os
import asyncio
import argparse
import logging
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
    try:
        # Parse command line arguments
        parser = argparse.ArgumentParser(description='Azure Test Plans to Xray Migration')
        parser.add_argument('--csv', help='Path to CSV file containing Azure Test Plan URLs')
        parser.add_argument('--modular', action='store_true', help='Use modular output (separate files for each test plan)')
        args = parser.parse_args()
        
        logger.info("Starting Azure Test Plans to Xray Migration")
        
        # Load configuration
        config = AzureConfig()
        logger.info(f"Loaded configuration for project: {config.project_name}")
        
        # Initialize extractor
        extractor = AzureTestExtractor(config)
        
        # Extract test plans (either all or from CSV)
        if args.csv:
            logger.info(f"Extracting specific test plans from CSV: {args.csv}")
            logger.info(f"Modular output: {'Enabled' if args.modular else 'Disabled'}")
            
            extraction_result = await extractor.extract_from_csv(
                csv_path=args.csv,
                modular_output=args.modular
            )
        else:
            logger.info("Extracting all test plans")
            extraction_result = await extractor.extract_all()
        
        # Log extraction summary
        logger.info("Extraction completed successfully")
        for entity_type, entities in extraction_result.items():
            if entity_type not in ["extraction_path", "csv_mapping"]:
                count = len(entities) if isinstance(entities, list) else 1
                logger.info(f"  Extracted {count} {entity_type}")
        
        # Log output location
        output_dir = extraction_result["extraction_path"]
        logger.info("Azure Test Plans data extraction has been completed successfully")
        logger.info(f"The extracted data is saved in: {output_dir}")
        logger.info("The extracted data is ready for mapping to Xray format")
        
    except Exception as e:
        logger.error(f"Error during extraction: {str(e)}", exc_info=True)
        
if __name__ == "__main__":
    asyncio.run(main()) 