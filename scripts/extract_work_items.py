#!/usr/bin/env python3
"""
Script to extract work items directly using the WorkItemExtractor.

This script demonstrates how to use the WorkItemExtractor module independently 
to extract work items from Azure DevOps.

Usage:
    python extract_work_items.py --project <project_name> --work-item-ids <comma_separated_ids>
"""

import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
import json

# Add the src directory to the path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
sys.path.append(project_root)

# Now we can import modules from src
from src.config.config import AzureConfig
from src.utils.azure_client import AzureDevOpsClient
from src.work_items.work_item_extractor import WorkItemExtractor
from src.work_items.work_item_processor import WorkItemProcessor

def setup_logging():
    """Set up logging configuration."""
    # Create logs directory if it doesn't exist
    logs_dir = os.path.join(project_root, "logs")
    os.makedirs(logs_dir, exist_ok=True)
    
    # Generate timestamp for log filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(logs_dir, f"work_items_extraction_{timestamp}.log")
    
    # Set up logging configuration
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(console_formatter)
    
    # File handler with rotation
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=100 * 1024 * 1024,  # 100 MB
        backupCount=10
    )
    file_handler.setLevel(logging.INFO)
    file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(file_formatter)
    
    # Add handlers to root logger
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
    
    return log_file

async def main():
    """Main function to extract work items."""
    try:
        # Set up logging first
        log_file = setup_logging()
        logger = logging.getLogger(__name__)
        
        # Parse command line arguments
        parser = argparse.ArgumentParser(description='Extract Work Items from Azure DevOps')
        parser.add_argument('--project', type=str, default=None,
                            help='Project name (defaults to the one in config)')
        parser.add_argument('--work-item-ids', type=str, required=False,
                            help='Comma-separated list of work item IDs to extract')
        parser.add_argument('--output-dir', type=str, default=None,
                            help='Output directory for the extracted work items')
        parser.add_argument('--fields', type=str, default=None,
                            help='Comma-separated list of fields to retrieve (defaults to test case fields)')
        args = parser.parse_args()
        
        logger.info("Starting Work Items Extraction")
        logger.info(f"Logs will be saved to: {log_file}")
        
        # Load configuration
        config = AzureConfig()
        project = args.project or config.project_name
        logger.info(f"Using project: {project}")
        
        # Initialize Azure client
        logger.info("Initializing Azure DevOps client")
        client = AzureDevOpsClient(config)
        
        # Initialize work item extractor and processor
        work_item_extractor = WorkItemExtractor(client)
        work_item_processor = WorkItemProcessor()
        
        # Prepare output directory
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = args.output_dir or os.path.join(project_root, "output", "work_items", timestamp)
        os.makedirs(output_dir, exist_ok=True)
        logger.info(f"Output directory: {output_dir}")
        
        # Parse work item IDs if provided
        work_item_ids = []
        if args.work_item_ids:
            id_strings = args.work_item_ids.split(',')
            work_item_ids = [int(id_str.strip()) for id_str in id_strings if id_str.strip().isdigit()]
            logger.info(f"Extracting {len(work_item_ids)} specific work items: {work_item_ids}")
        else:
            logger.info("No work item IDs provided. Please specify with --work-item-ids")
            return
        
        # Parse fields if provided
        fields = None
        if args.fields:
            fields = [field.strip() for field in args.fields.split(',') if field.strip()]
            logger.info(f"Using custom fields: {fields}")
        else:
            fields = work_item_extractor.get_test_case_fields()
            logger.info(f"Using default test case fields")
        
        # Extract work items
        logger.info(f"Extracting {len(work_item_ids)} work items")
        
        # Use more explicit logging for debugging
        logger.info(f"Connecting to Azure DevOps at: {config.organization_url}")
        logger.info(f"Using PAT authentication with username: {config.username}")
        logger.info(f"Work item IDs being requested: {work_item_ids}")
        
        # Call the extract_work_items_batch method directly
        work_items = await work_item_extractor.extract_work_items_batch(project, work_item_ids)
        
        # Add verbose logging about the response
        if not work_items:
            logger.error("No work items retrieved from Azure DevOps API")
            logger.error("This could be due to: invalid IDs, permission issues, or API formatting errors")
        else:
            logger.info(f"Successfully retrieved {len(work_items)} work items from Azure DevOps")
            for idx, item in enumerate(work_items):
                item_id = item.get('id')
                item_title = item.get('fields', {}).get('System.Title', 'Unknown')
                logger.info(f"Work item {idx+1}: ID={item_id}, Title={item_title}")
        
        extraction_result = {
            "work_items": work_items,
            "work_item_count": len(work_items),
            "extraction_timestamp": datetime.now().isoformat(),
            "status": "Success" if work_items else "ERROR: No work items extracted"
        }
        
        # Process the work items
        work_items = extraction_result.get("work_items", [])
        logger.info(f"Processing {len(work_items)} work items")
        processed_work_items = work_item_processor.process_work_items(work_items)
        
        # Save raw work items
        raw_output_path = os.path.join(output_dir, "raw_work_items.json")
        with open(raw_output_path, 'w', encoding='utf-8') as f:
            json.dump(work_items, f, indent=2, ensure_ascii=False)
        logger.info(f"Saved raw work items to {raw_output_path}")
        
        # Save processed work items
        processed_output_path = os.path.join(output_dir, "processed_work_items.json")
        work_item_processor.save_work_items(processed_work_items, processed_output_path)
        
        # Create summary information
        summary = {
            "project_name": project,
            "extraction_timestamp": timestamp,
            "total_work_items": len(work_items),
            "processed_work_items": len(processed_work_items),
            "status": extraction_result.get("status", "Unknown")
        }
        
        # Add any errors if present
        if "errors" in extraction_result:
            summary["errors"] = extraction_result["errors"]
        
        # Save summary
        summary_path = os.path.join(output_dir, "extraction_summary.json")
        with open(summary_path, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        logger.info(f"Saved summary to {summary_path}")
        
        logger.info("Work item extraction completed successfully")
        logger.info(f"Extracted {len(processed_work_items)} work items")
        logger.info(f"Results saved to {output_dir}")
        
    except Exception as e:
        logger.error(f"Error during work item extraction: {str(e)}", exc_info=True)

if __name__ == "__main__":
    asyncio.run(main()) 