#!/usr/bin/env python
"""
Wrapper script to extract the entire eWM30 project from Azure DevOps
using modern API endpoints only with no filtering.

This script is a convenient shortcut to run the extraction without
having to use command line arguments.
"""

import asyncio
import os
import sys
import logging
import traceback
from datetime import datetime
from pathlib import Path

# Get the script's directory and add the src directory to the path
# This ensures the script will work regardless of current working directory
script_dir = Path(__file__).parent.absolute()
sys.path.append(str(script_dir / 'src'))

# Import after path setup
from src.config.config import AzureConfig
from src.extractors.azure_test_extractor import AzureTestExtractor

def setup_logging():
    """Set up logging configuration"""
    # Create logs directory using pathlib for better cross-platform compatibility
    log_dir = script_dir / 'logs'
    log_dir.mkdir(exist_ok=True)
    
    # Create a timestamp-based log file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f'extraction_{timestamp}.log'
    
    # Configure logging with more detailed format
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(str(log_file)),
            logging.StreamHandler()
        ]
    )
    
    # Get logger and add some system info
    logger = logging.getLogger(__name__)
    logger.info(f"Script running from: {script_dir}")
    logger.info(f"Python version: {sys.version}")
    logger.info(f"Operating system: {sys.platform}")
    
    return log_file

async def main():
    """Main function to extract the entire eWM30 project"""
    try:
        # Set up logging
        log_file = setup_logging()
        logger = logging.getLogger(__name__)
        
        logger.info("========== EXTRACTION STARTED ==========")
        logger.info("Starting extraction of entire eWM30 project")
        logger.info(f"Logs will be saved to: {log_file}")
        
        # Make sure extraction_results directory exists
        results_dir = script_dir / 'extraction_results'
        results_dir.mkdir(exist_ok=True)
        logger.info(f"Extraction results will be saved to: {results_dir}")
        
        # Load configuration
        config = AzureConfig()
        logger.info(f"Loaded configuration for project: {config.project_name}")
        logger.info(f"Organization URL: {config.organization_url}")
        
        # Initialize extractor
        extractor = AzureTestExtractor(config)
        
        # Extract the entire project
        project_name = "eWM30"  # Hardcoded for this script
        logger.info(f"Extracting entire project: {project_name}")
        
        extraction_result = await extractor.extract_entire_project(project_name=project_name)
        
        # Check extraction status
        status = extraction_result.get("status", "Unknown")
        
        if "error" in extraction_result or status.startswith("ERROR"):
            logger.error("========== EXTRACTION FAILED ==========")
            if "error" in extraction_result:
                logger.error(f"Error: {extraction_result['error']}")
            logger.error(f"Status: {status}")
            
            # Log additional errors if available
            if "errors" in extraction_result:
                for i, error in enumerate(extraction_result["errors"]):
                    logger.error(f"Additional error {i+1}: {error}")
                    
            logger.error(f"Check logs for details. Extraction directory: {extraction_result['extraction_path']}")
        else:
            # Log extraction summary
            logger.info("========== EXTRACTION COMPLETED ==========")
            logger.info(f"Status: {status}")
            logger.info(f"Extracted {extraction_result.get('total_plans', 0)} test plans")
            logger.info(f"Extracted {len(extraction_result.get('test_suites', []))} test suites")
            logger.info(f"Extracted {len(extraction_result.get('test_cases', []))} test cases")
            
            # Log warnings if any
            if "warnings" in extraction_result:
                logger.warning("Warnings during extraction:")
                for i, warning in enumerate(extraction_result["warnings"]):
                    logger.warning(f"Warning {i+1}: {warning}")
            
            logger.info(f"The extracted data is saved in: {extraction_result['extraction_path']}")
        
    except Exception as e:
        logger.error(f"========== EXTRACTION FAILED ==========")
        logger.error(f"Error during extraction: {str(e)}")
        # Print full stack trace to the log
        logger.error(traceback.format_exc())
        
if __name__ == "__main__":
    asyncio.run(main()) 