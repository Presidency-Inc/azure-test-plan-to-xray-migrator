import os
import asyncio
import argparse
import logging
import sys
from logging.handlers import RotatingFileHandler
from datetime import datetime
from pathlib import Path
from config.config import AzureConfig
from extractors.azure_test_extractor import AzureTestExtractor
from utils.json_utils import save_json_data

def setup_logging():
    # Create logs directory if it doesn't exist
    logs_dir = os.path.join("logs")
    os.makedirs(logs_dir, exist_ok=True)
    
    # Generate timestamp for log filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(logs_dir, f"extraction_{timestamp}.log")
    
    # Set up logging configuration
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(console_formatter)
    
    # File handler with rotation (100 MB per file, 1000 backup files)
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=100 * 1024 * 1024,  # 100 MB
        backupCount=1000
    )
    file_handler.setLevel(logging.INFO)
    file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(file_formatter)
    
    # Add handlers to root logger
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
    
    return log_file

async def main():
    try:
        # Set up logging first
        log_file = setup_logging()
        
        # Parse command line arguments
        parser = argparse.ArgumentParser(description='Azure Test Plans to Xray Migration')
        parser.add_argument('--csv', help='Path to CSV file containing Azure Test Plan URLs')
        parser.add_argument('--modular', action='store_true', help='Use modular output (separate files for each test plan)')
        parser.add_argument('--extract-project', action='store_true', 
                          help='Extract the entire project without filtering')
        parser.add_argument('--project-name', type=str, default='eWM30',
                          help='Project name to extract (default: eWM30)')
        args = parser.parse_args()
        
        logger = logging.getLogger(__name__)
        logger.info("Starting Azure Test Plans to Xray Migration")
        logger.info(f"Logs will be saved to: {log_file}")
        
        # Load configuration
        config = AzureConfig()
        logger.info(f"Loaded configuration for project: {config.project_name}")
        
        # Initialize extractor
        extractor = AzureTestExtractor(config)
        
        # Determine which extraction method to use
        if args.extract_project:
            # New: Extract entire project using modern API only
            logger.info(f"Extracting entire project: {args.project_name}")
            extraction_result = await extractor.extract_entire_project(
                project_name=args.project_name
            )
            logger.info(f"Extraction completed successfully")
            logger.info(f"Extracted {extraction_result.get('total_plans', 0)} test plans")
            logger.info(f"The extracted data is saved in: {extraction_result['extraction_path']}")
        elif args.csv:
            # Legacy: Extract specific test plans from CSV
            logger.info(f"Extracting specific test plans from CSV: {args.csv}")
            logger.info(f"Modular output: {'Enabled' if args.modular else 'Disabled'}")
            
            extraction_result = await extractor.extract_from_csv(
                csv_path=args.csv,
                modular_output=args.modular
            )
        else:
            # Legacy: Extract all test plans
            logger.info("Extracting all test plans")
            extraction_result = await extractor.extract_all()
        
        # Log extraction summary
        logger.info("Extraction completed successfully")
        for entity_type, entities in extraction_result.items():
            if entity_type not in ["extraction_path", "csv_mapping", "project_name", "extraction_timestamp", "total_plans", "error"]:
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