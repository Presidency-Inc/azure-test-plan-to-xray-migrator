import unittest
import os
import json
import tempfile
import csv
from src.utils.csv_parser import AzureTestPlanCSVParser

class TestAzureTestPlanCSVParser(unittest.TestCase):
    
    def setUp(self):
        # Create a temporary CSV file for testing
        self.temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.csv')
        self.csv_content = [
            ["Test Suite"],
            ["Test Suite Name", "Owner", "Email", "URL", "Count", "Automated"],
            ["Suite 1", "John Doe", "john@example.com", "https://dev.azure.com/org/project/_testPlans/define?planId=123&suiteId=456", "10", "No"],
            ["Suite 2", "Jane Smith", "jane@example.com", "https://dev.azure.com/org/project/_testPlans/define?planId=789&suiteId=101", "20", "Yes"],
            ["Suite 3", "Bob Johnson", "bob@example.com", "https://dev.azure.com/org/project/_testPlans/define?planId=123&suiteId=789\nhttps://dev.azure.com/org/project/_testPlans/define?planId=456&suiteId=123", "30", "Mixed"]
        ]
        
        with open(self.temp_file.name, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerows(self.csv_content)
            
        self.parser = AzureTestPlanCSVParser(self.temp_file.name)
    
    def tearDown(self):
        # Remove the temporary file
        os.unlink(self.temp_file.name)
    
    def test_parse(self):
        # Test parsing the CSV file
        result = self.parser.parse()
        
        # Check that the result contains the correct structure
        self.assertIn('csv_data', result)
        self.assertIn('plan_suite_mapping', result)
        self.assertIn('metadata', result)
        
        # Check that we have the correct number of data rows
        self.assertEqual(len(result['csv_data']), 3)
        
        # Check that we have extracted the correct URLs
        first_row = result['csv_data'][0]
        self.assertEqual(first_row['test_suite_name'], 'Suite 1')
        self.assertEqual(first_row['owner'], 'John Doe')
        self.assertEqual(first_row['email'], 'john@example.com')
        self.assertEqual(len(first_row['urls']), 1)
        self.assertEqual(first_row['urls'][0]['plan_id'], 123)
        self.assertEqual(first_row['urls'][0]['suite_id'], 456)
        
        # Check the row with multiple URLs
        third_row = result['csv_data'][2]
        self.assertEqual(len(third_row['urls']), 2)
        self.assertEqual(third_row['urls'][0]['plan_id'], 123)
        self.assertEqual(third_row['urls'][0]['suite_id'], 789)
        self.assertEqual(third_row['urls'][1]['plan_id'], 456)
        self.assertEqual(third_row['urls'][1]['suite_id'], 123)
    
    def test_get_unique_plan_ids(self):
        # Parse first
        self.parser.parse()
        
        # Test getting unique plan IDs
        unique_plans = self.parser.get_unique_plan_ids()
        self.assertEqual(len(unique_plans), 3)
        self.assertTrue(123 in unique_plans)
        self.assertTrue(456 in unique_plans)
        self.assertTrue(789 in unique_plans)
    
    def test_get_plan_suite_mapping(self):
        # Parse first
        self.parser.parse()
        
        # Test getting plan to suite mapping
        mapping = self.parser.get_plan_suite_mapping()
        
        # Plan 123 should map to suites 456 and 789
        self.assertEqual(len(mapping[123]), 2)
        self.assertTrue(456 in mapping[123])
        self.assertTrue(789 in mapping[123])
        
        # Plan 456 should map to suite 123
        self.assertEqual(len(mapping[456]), 1)
        self.assertTrue(123 in mapping[456])
        
        # Plan 789 should map to suite 101
        self.assertEqual(len(mapping[789]), 1)
        self.assertTrue(101 in mapping[789])
    
    def test_extract_ids_from_url(self):
        # Test the private method _extract_ids_from_url
        url = "https://dev.azure.com/org/project/_testPlans/define?planId=123&suiteId=456"
        plan_id, suite_id = self.parser._extract_ids_from_url(url)
        self.assertEqual(plan_id, 123)
        self.assertEqual(suite_id, 456)
        
        # Test with different order of parameters
        url = "https://dev.azure.com/org/project/_testPlans/define?suiteId=789&planId=101"
        plan_id, suite_id = self.parser._extract_ids_from_url(url)
        self.assertEqual(plan_id, 101)
        self.assertEqual(suite_id, 789)
        
        # Test with additional parameters
        url = "https://dev.azure.com/org/project/_testPlans/define?planId=123&suiteId=456&someOtherParam=value"
        plan_id, suite_id = self.parser._extract_ids_from_url(url)
        self.assertEqual(plan_id, 123)
        self.assertEqual(suite_id, 456)
        
        # Test with invalid URL
        url = "https://dev.azure.com/org/project/_testPlans/define?someParam=value"
        with self.assertRaises(ValueError):
            self.parser._extract_ids_from_url(url)

if __name__ == '__main__':
    unittest.main() 