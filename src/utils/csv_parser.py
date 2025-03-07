import csv
import urllib.parse
from typing import List, Dict, Tuple, Set, Any
import logging

class AzureTestPlanCSVParser:
    """Parse a CSV file containing Azure Test Plan URLs"""
    
    def __init__(self, csv_path: str):
        self.csv_path = csv_path
        self.logger = logging.getLogger(__name__)
        
    def parse(self) -> Dict[str, Any]:
        """
        Parse the CSV file and extract relevant test plan information
        
        Returns:
            Dictionary containing test plan information and mapping
        """
        test_plans_data = []
        
        try:
            with open(self.csv_path, 'r', encoding='utf-8') as csv_file:
                csv_reader = csv.reader(csv_file)
                # Skip header rows
                next(csv_reader, None)
                next(csv_reader, None)
                
                for row in csv_reader:
                    if len(row) >= 4:  # Ensure row has enough columns
                        test_suite_name = row[0]
                        owner = row[1]
                        email = row[2]
                        urls_cell = row[3]
                        
                        # Split cell by newlines to handle multiple URLs
                        urls = urls_cell.strip().split('\n')
                        
                        for url in urls:
                            # Only process Azure DevOps URLs
                            if 'dev.azure.com' in url:
                                # Extract plan ID and suite ID
                                plan_id, suite_id = self._extract_ids_from_url(url)
                                
                                if plan_id and suite_id:
                                    test_plans_data.append({
                                        'test_suite_name': test_suite_name,
                                        'owner': owner,
                                        'email': email,
                                        'url': url,
                                        'plan_id': plan_id,
                                        'suite_id': suite_id
                                    })
        except Exception as e:
            self.logger.error(f"Error parsing CSV file {self.csv_path}: {str(e)}")
        
        self.logger.info(f"Extracted {len(test_plans_data)} test plan entries from CSV")
        
        # Create plan to suite mapping
        plan_suite_mapping = self.get_plan_suite_mapping()
        
        # Return both the raw data and the mapping
        return {
            "test_plans_data": test_plans_data,
            "plan_suite_mapping": plan_suite_mapping
        }
    
    def _extract_ids_from_url(self, url: str) -> Tuple[str, str]:
        """Extract plan ID and suite ID from Azure DevOps URL"""
        try:
            # Parse the URL
            parsed_url = urllib.parse.urlparse(url)
            # Parse the query parameters
            query_params = urllib.parse.parse_qs(parsed_url.query)
            
            # Extract plan ID and suite ID
            plan_id = query_params.get('planId', [None])[0]
            suite_id = query_params.get('suiteId', [None])[0]
            
            return plan_id, suite_id
        except Exception as e:
            self.logger.warning(f"Error extracting IDs from URL {url}: {str(e)}")
            return None, None
    
    def get_unique_plan_ids(self) -> Set[str]:
        """Get unique plan IDs from the CSV"""
        test_plans_data = self.parse()["test_plans_data"]
        return {item['plan_id'] for item in test_plans_data if item['plan_id']}
    
    def get_plan_suite_mapping(self) -> Dict[str, List[str]]:
        """Get mapping of plan IDs to their suite IDs from the CSV"""
        # We need to call parse() directly here to avoid infinite recursion
        test_plans_data = []
        try:
            with open(self.csv_path, 'r', encoding='utf-8') as csv_file:
                csv_reader = csv.reader(csv_file)
                # Skip header rows
                next(csv_reader, None)
                next(csv_reader, None)
                
                for row in csv_reader:
                    if len(row) >= 4:  # Ensure row has enough columns
                        test_suite_name = row[0]
                        owner = row[1]
                        email = row[2]
                        urls_cell = row[3]
                        
                        # Split cell by newlines to handle multiple URLs
                        urls = urls_cell.strip().split('\n')
                        
                        for url in urls:
                            # Only process Azure DevOps URLs
                            if 'dev.azure.com' in url:
                                # Extract plan ID and suite ID
                                plan_id, suite_id = self._extract_ids_from_url(url)
                                
                                if plan_id and suite_id:
                                    test_plans_data.append({
                                        'test_suite_name': test_suite_name,
                                        'owner': owner,
                                        'email': email,
                                        'url': url,
                                        'plan_id': plan_id,
                                        'suite_id': suite_id
                                    })
        except Exception as e:
            self.logger.error(f"Error parsing CSV file {self.csv_path}: {str(e)}")
        
        plan_suite_mapping = {}
        
        for item in test_plans_data:
            plan_id = item['plan_id']
            suite_id = item['suite_id']
            
            if plan_id and suite_id:
                if plan_id not in plan_suite_mapping:
                    plan_suite_mapping[plan_id] = []
                
                if suite_id not in plan_suite_mapping[plan_id]:
                    plan_suite_mapping[plan_id].append(suite_id)
        
        return plan_suite_mapping 