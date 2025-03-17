import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Add the src directory to the path
src_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(src_dir)
sys.path.append(project_root)

# Now we can import modules from src
from src.config.config import AzureConfig
from src.extractors.azure_test_extractor import AzureTestExtractor
from src.utils.json_utils import save_json_data

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
                project=args.project_name
            )
            
            # Check extraction status
            status = extraction_result.get("status", "Unknown")
            
            if "error" in extraction_result or status.startswith("ERROR"):
                logger.error("Extraction failed")
                if "error" in extraction_result:
                    logger.error(f"Error: {extraction_result['error']}")
                logger.error(f"Status: {status}")
                
                # Log additional errors if available
                if "errors" in extraction_result:
                    for i, error in enumerate(extraction_result["errors"]):
                        logger.error(f"Additional error {i+1}: {error}")
                        
                logger.error(f"Check logs for details. Extraction directory: {extraction_result['extraction_path']}")
                return
            
            logger.info(f"Extraction completed successfully")
            logger.info(f"Extracted {extraction_result.get('total_plans', 0)} test plans")
            
            # Add work item extraction status reporting
            if "work_items" in extraction_result:
                work_item_count = len(extraction_result["work_items"])
                work_item_status = extraction_result.get("work_item_extraction_status", "Unknown")
                logger.info(f"Extracted {work_item_count} work items")
                logger.info(f"Work item extraction status: {work_item_status}")
                
                # Report any work item warnings
                if "work_item_warnings" in extraction_result:
                    for i, warning in enumerate(extraction_result["work_item_warnings"]):
                        logger.warning(f"Work item warning {i+1}: {warning}")
            
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
            if entity_type not in ["extraction_path", "csv_mapping", "project_name", "extraction_timestamp", "total_plans", "error", "errors", "warnings", "status"]:
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