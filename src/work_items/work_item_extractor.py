"""
Work Item Extractor module.

This module handles the extraction of work items from Azure DevOps
that represent test cases.
"""

import logging
import os
import sys
import asyncio
from typing import List, Dict, Any, Optional, Set
from pathlib import Path

# Add the project root to the Python path
file_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if file_path not in sys.path:
    sys.path.append(file_path)

from src.utils.azure_client import AzureDevOpsClient
from src.config.config import AzureConfig


class WorkItemExtractor:
    """
    Extracts work items from Azure DevOps that represent test cases.
    """
    
    def __init__(self, azure_client: AzureDevOpsClient):
        """
        Initialize the WorkItemExtractor.
        
        Args:
            azure_client: The Azure DevOps client
        """
        self.client = azure_client
        self.logger = logging.getLogger(__name__)
        
    def get_test_case_fields(self) -> List[str]:
        """
        Get the list of fields to retrieve for test cases.
        
        Returns:
            List of field names
        """
        return [
            # Core fields
            "System.Id",
            "System.Title",
            "System.Description",
            "System.State",
            "System.WorkItemType",
            "System.Tags",
            "System.AssignedTo",
            "System.CreatedBy",
            "System.CreatedDate",
            "System.ChangedDate",
            "System.ChangedBy",
            
            # Test case specific fields
            "Microsoft.VSTS.TCM.Steps",           # Contains steps, actions and expected results
            "Microsoft.VSTS.TCM.Parameters",      # Test parameters
            "Microsoft.VSTS.TCM.LocalDataSource", # Parameter values
            "Microsoft.VSTS.TCM.Prerequisites",   # Preconditions
            "Microsoft.VSTS.TCM.AutomationStatus", # Automation status
            "Microsoft.VSTS.Common.Priority"      # Priority
        ]
    
    def extract_work_item_ids(self, test_cases: List[Dict[str, Any]]) -> List[int]:
        """
        Extract work item IDs from test cases.
        
        Args:
            test_cases: List of test cases
            
        Returns:
            List of work item IDs
        """
        # Use a set to deduplicate IDs
        work_item_ids = set()
        
        for test_case in test_cases:
            if "workItemId" in test_case and test_case["workItemId"]:
                try:
                    # Convert to int and add to set
                    work_item_id = int(test_case["workItemId"])
                    work_item_ids.add(work_item_id)
                except (ValueError, TypeError):
                    self.logger.warning(f"Invalid work item ID: {test_case['workItemId']}")
        
        # Convert set to sorted list
        return sorted(list(work_item_ids))
    
    async def extract_work_items_batch(self, project: str, work_item_ids: List[int]) -> List[Dict[str, Any]]:
        """
        Extract work items in batches of 200 (API limit).
        
        Args:
            project: Project name
            work_item_ids: List of work item IDs
            
        Returns:
            List of work items
        """
        if not work_item_ids:
            self.logger.warning("No work item IDs provided for extraction")
            return []
        
        # Define batch size (API limit is 200)
        batch_size = 200
        results = []
        total_batches = (len(work_item_ids) + batch_size - 1) // batch_size
        
        self.logger.info(f"Extracting {len(work_item_ids)} work items in {total_batches} batches")
        
        fields = self.get_test_case_fields()
        
        # Process in batches
        for i in range(0, len(work_item_ids), batch_size):
            batch = work_item_ids[i:i+batch_size]
            batch_num = i // batch_size + 1
            
            self.logger.info(f"Processing batch {batch_num}/{total_batches} with {len(batch)} work items")
            
            try:
                batch_results = await self.client.get_work_items_batch(
                    project_name=project,
                    work_item_ids=batch,
                    fields=fields
                )
                
                if batch_results:
                    results.extend(batch_results)
                    self.logger.info(f"Retrieved {len(batch_results)} work items in batch {batch_num}")
                else:
                    self.logger.warning(f"No work items retrieved in batch {batch_num}")
                    
            except Exception as e:
                self.logger.error(f"Error processing batch {batch_num}: {str(e)}", exc_info=True)
        
        self.logger.info(f"Retrieved a total of {len(results)} work items")
        return results
    
    async def extract_test_case_work_items(self, project: str, test_cases: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Extract all work items for test cases.
        
        Args:
            project: Project name
            test_cases: List of test cases
            
        Returns:
            Dictionary with work items and metadata
        """
        self.logger.info(f"Starting extraction of work items for test cases")
        
        # Extract work item IDs from test cases
        work_item_ids = self.extract_work_item_ids(test_cases)
        
        if not work_item_ids:
            self.logger.warning("No work item IDs found in test cases")
            return {
                "work_items": [],
                "work_item_count": 0,
                "extraction_timestamp": None,
                "status": "WARNING: No work items to extract"
            }
        
        self.logger.info(f"Found {len(work_item_ids)} unique work item IDs to extract")
        
        # Extract work items in batches
        work_items = await self.extract_work_items_batch(project, work_item_ids)
        
        # Create result
        result = {
            "work_items": work_items,
            "work_item_count": len(work_items),
            "extraction_timestamp": self.client.config.extraction_timestamp,
            "status": "Success" if work_items else "WARNING: No work items extracted"
        }
        
        # Log summary
        self.logger.info(f"Completed extraction of {len(work_items)} work items")
        
        return result 