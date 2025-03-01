import asyncio
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
    logger.info("Starting Azure Test Plans to Xray Migration")
    
    # Load configuration
    config = AzureConfig()
    logger.info(f"Loaded configuration for project: {config.project_name}")
    
    # Initialize the extractor
    extractor = AzureTestExtractor(config)
    
    # Extract all data
    logger.info("Starting data extraction from Azure Test Plans")
    extraction_result = await extractor.extract_all()
    
    # Print summary of extracted data
    logger.info("Extraction completed successfully")
    for entity_type, entities in extraction_result.items():
        logger.info(f"  Extracted {len(entities)} {entity_type}")
    
    logger.info("Azure Test Plans data extraction has been completed successfully")
    logger.info("The extracted data is ready for mapping to Xray format")

if __name__ == "__main__":
    asyncio.run(main()) 