"""
Work Item Processor module.

This module handles the processing and transformation of work items
retrieved from Azure DevOps, focusing on test case specific data.
"""

import logging
import os
import sys
import json
import xml.etree.ElementTree as ET
import re
from typing import List, Dict, Any, Optional
from pathlib import Path

# Add the project root to the Python path
file_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if file_path not in sys.path:
    sys.path.append(file_path)


class WorkItemProcessor:
    """
    Processes work items from Azure DevOps, focusing on test case specific data.
    """
    
    def __init__(self):
        """Initialize the WorkItemProcessor."""
        self.logger = logging.getLogger(__name__)
    
    def process_work_items(self, work_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Process a list of work items, extracting and transforming test case specific data.
        
        Args:
            work_items: List of work items retrieved from Azure DevOps
            
        Returns:
            List of processed work items with structured test case data
        """
        processed_items = []
        
        for work_item in work_items:
            try:
                processed_item = self.process_work_item(work_item)
                processed_items.append(processed_item)
            except Exception as e:
                self.logger.error(f"Error processing work item {work_item.get('id', 'unknown')}: {str(e)}", exc_info=True)
        
        self.logger.info(f"Processed {len(processed_items)} work items")
        return processed_items
    
    def process_work_item(self, work_item: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process a single work item, extracting and transforming test case specific data.
        
        Args:
            work_item: Work item retrieved from Azure DevOps
            
        Returns:
            Processed work item with structured test case data
        """
        # Create a copy of the work item to avoid modifying the original
        processed_item = work_item.copy()
        
        # Extract fields
        fields = processed_item.get("fields", {})
        
        # Process test steps
        if "Microsoft.VSTS.TCM.Steps" in fields:
            steps_xml = fields["Microsoft.VSTS.TCM.Steps"]
            if steps_xml:
                try:
                    processed_steps = self.parse_steps_xml(steps_xml)
                    processed_item["test_steps"] = processed_steps
                except Exception as e:
                    self.logger.error(f"Error parsing steps for work item {work_item.get('id', 'unknown')}: {str(e)}", exc_info=True)
                    processed_item["test_steps"] = []
            else:
                processed_item["test_steps"] = []
        else:
            processed_item["test_steps"] = []
        
        # Process parameters
        if "Microsoft.VSTS.TCM.Parameters" in fields:
            params_xml = fields["Microsoft.VSTS.TCM.Parameters"]
            if params_xml:
                try:
                    processed_params = self.parse_parameters_xml(params_xml)
                    processed_item["test_parameters"] = processed_params
                except Exception as e:
                    self.logger.error(f"Error parsing parameters for work item {work_item.get('id', 'unknown')}: {str(e)}", exc_info=True)
                    processed_item["test_parameters"] = []
            else:
                processed_item["test_parameters"] = []
        else:
            processed_item["test_parameters"] = []
        
        # Process parameter values (local data source)
        if "Microsoft.VSTS.TCM.LocalDataSource" in fields:
            data_source = fields["Microsoft.VSTS.TCM.LocalDataSource"]
            if data_source:
                try:
                    parameter_values = self.parse_data_source(data_source)
                    processed_item["parameter_values"] = parameter_values
                except Exception as e:
                    self.logger.error(f"Error parsing parameter values for work item {work_item.get('id', 'unknown')}: {str(e)}", exc_info=True)
                    processed_item["parameter_values"] = []
            else:
                processed_item["parameter_values"] = []
        else:
            processed_item["parameter_values"] = []
        
        return processed_item
    
    def parse_steps_xml(self, steps_xml: str) -> List[Dict[str, Any]]:
        """
        Parse the XML containing test steps.
        
        Args:
            steps_xml: XML string containing test steps
            
        Returns:
            List of structured test steps
        """
        if not steps_xml:
            return []
        
        try:
            # Parse XML
            # Handle CDATA sections and potential XML issues
            # Azure DevOps test steps are in a specific format with steps, actions, and expected results
            steps = []
            
            # Clean up XML if needed
            clean_xml = steps_xml.strip()
            
            # Some XML might be wrapped in CDATA, detect and handle it
            if "<![CDATA[" in clean_xml and "]]>" in clean_xml:
                self.logger.debug("Detected CDATA in steps XML, extracting content")
                start_idx = clean_xml.find("<![CDATA[") + 9
                end_idx = clean_xml.rfind("]]>")
                if start_idx > 0 and end_idx > start_idx:
                    clean_xml = clean_xml[start_idx:end_idx]
            
            # Ensure it has proper XML structure
            if not clean_xml.startswith("<?xml") and not clean_xml.startswith("<steps"):
                clean_xml = f"<?xml version='1.0' encoding='UTF-8'?><steps>{clean_xml}</steps>"
            elif not clean_xml.startswith("<?xml") and clean_xml.startswith("<steps"):
                clean_xml = f"<?xml version='1.0' encoding='UTF-8'?>{clean_xml}"
                
            self.logger.debug(f"Parsing XML with size: {len(clean_xml)} bytes")
            
            # Parse the XML
            try:
                root = ET.fromstring(clean_xml)
            except ET.ParseError as xml_error:
                self.logger.warning(f"XML parsing error: {str(xml_error)}, trying with recovery")
                # Try to recover by finding all step blocks manually
                step_blocks = []
                start_tags = [m.start() for m in re.finditer("<step", clean_xml)]
                end_tags = [m.start() for m in re.finditer("</step>", clean_xml)]
                
                if len(start_tags) == len(end_tags) and len(start_tags) > 0:
                    for i in range(len(start_tags)):
                        step_block = clean_xml[start_tags[i]:end_tags[i]+7]  # +7 for </step>
                        step_blocks.append(f"<root>{step_block}</root>")
                    
                    # Process each step block separately
                    for block in step_blocks:
                        try:
                            step_root = ET.fromstring(block)
                            step_elem = step_root.find("step")
                            if step_elem is not None:
                                step = self._extract_step_data(step_elem)
                                steps.append(step)
                        except Exception as step_error:
                            self.logger.error(f"Error processing step block: {str(step_error)}")
                    
                    return steps
                else:
                    # If we can't recover, log the error and return empty
                    self.logger.error(f"Unable to recover XML parsing. Found {len(start_tags)} start tags and {len(end_tags)} end tags.")
                    return []
            
            # Normal processing of well-formed XML
            # Find all step elements (handle both direct children and nested steps)
            step_elems = root.findall('.//step')
            
            for step_elem in step_elems:
                step = self._extract_step_data(step_elem)
                steps.append(step)
            
            self.logger.info(f"Successfully parsed {len(steps)} test steps")
            return steps
        except Exception as e:
            self.logger.error(f"Error parsing steps XML: {str(e)}", exc_info=True)
            # Return an empty list instead of raising to maintain robustness
            return []
    
    def _extract_step_data(self, step_elem: ET.Element) -> Dict[str, Any]:
        """
        Extract data from a step element.
        
        Args:
            step_elem: ElementTree Element containing step data
            
        Returns:
            Dictionary with step data
        """
        step = {
            "id": step_elem.get('id', ''),
            "type": step_elem.get('type', ''),
            "title": "",
            "action": "",
            "expected_result": "",
            "attachments": []
        }
        
        # Extract step parameterization info if available
        param_type = step_elem.get('parameterizedString', '')
        if param_type:
            step["parameterized"] = True
            step["parameter_type"] = param_type
        
        # Extract step title/description
        title_elem = step_elem.find('./title')
        if title_elem is not None:
            step["title"] = self._get_element_text(title_elem)
        
        # Extract step action
        action_elem = step_elem.find('./action')
        if action_elem is not None:
            step["action"] = self._get_element_text(action_elem)
        
        # Extract expected result
        expected_elem = step_elem.find('./expectedResult')
        if expected_elem is not None:
            step["expected_result"] = self._get_element_text(expected_elem)
        
        # Extract attachments
        attachment_elems = step_elem.findall('./attachments/attachment')
        for attachment_elem in attachment_elems:
            attachment = {
                "name": attachment_elem.get('name', ''),
                "url": attachment_elem.get('url', '')
            }
            step["attachments"].append(attachment)
        
        return step
    
    def _get_element_text(self, elem: ET.Element) -> str:
        """
        Get text from an element, handling CDATA sections and HTML content.
        
        Args:
            elem: ElementTree Element
            
        Returns:
            Text content as string
        """
        if elem is None:
            return ""
            
        # Get text directly
        text = elem.text or ""
        
        # Check for HTML content (common in Azure DevOps)
        if text.strip().startswith("<") and text.strip().endswith(">"):
            # This could be HTML content, try to extract just the text
            try:
                from html.parser import HTMLParser
                
                class MLStripper(HTMLParser):
                    def __init__(self):
                        super().__init__()
                        self.reset()
                        self.strict = False
                        self.convert_charrefs = True
                        self.text = []
                    
                    def handle_data(self, d):
                        self.text.append(d)
                    
                    def get_data(self):
                        return ''.join(self.text)
                
                stripper = MLStripper()
                stripper.feed(text)
                text = stripper.get_data()
            except Exception as e:
                self.logger.warning(f"Failed to strip HTML from text: {str(e)}")
        
        return text.strip()
    
    def parse_parameters_xml(self, parameters_xml: str) -> List[Dict[str, Any]]:
        """
        Parse the XML containing test parameters.
        
        Args:
            parameters_xml: XML string containing test parameters
            
        Returns:
            List of structured test parameters
        """
        if not parameters_xml:
            return []
        
        try:
            # Clean up XML if needed
            clean_xml = parameters_xml.strip()
            
            # Some XML might be wrapped in CDATA, detect and handle it
            if "<![CDATA[" in clean_xml and "]]>" in clean_xml:
                self.logger.debug("Detected CDATA in parameters XML, extracting content")
                start_idx = clean_xml.find("<![CDATA[") + 9
                end_idx = clean_xml.rfind("]]>")
                if start_idx > 0 and end_idx > start_idx:
                    clean_xml = clean_xml[start_idx:end_idx]
            
            # Ensure it has proper XML structure
            if not clean_xml.startswith("<?xml") and not clean_xml.startswith("<parameters"):
                clean_xml = f"<?xml version='1.0' encoding='UTF-8'?><parameters>{clean_xml}</parameters>"
            elif not clean_xml.startswith("<?xml") and clean_xml.startswith("<parameters"):
                clean_xml = f"<?xml version='1.0' encoding='UTF-8'?>{clean_xml}"
                
            self.logger.debug(f"Parsing parameters XML with size: {len(clean_xml)} bytes")
            
            # Parse the XML
            try:
                root = ET.fromstring(clean_xml)
            except ET.ParseError as xml_error:
                self.logger.warning(f"Parameters XML parsing error: {str(xml_error)}, trying with recovery")
                # Try to recover by finding all param blocks manually
                param_blocks = []
                start_tags = [m.start() for m in re.finditer("<param", clean_xml)]
                end_tags = [m.start() for m in re.finditer("/>", clean_xml)]
                
                if len(start_tags) == len(end_tags) and len(start_tags) > 0:
                    parameters = []
                    for i in range(len(start_tags)):
                        param_block = clean_xml[start_tags[i]:end_tags[i]+2]  # +2 for "/>
                        # Extract attributes using regex
                        name_match = re.search(r'name="([^"]*)"', param_block)
                        default_match = re.search(r'default="([^"]*)"', param_block)
                        
                        if name_match:
                            param = {
                                "name": name_match.group(1),
                                "default": default_match.group(1) if default_match else ""
                            }
                            parameters.append(param)
                    
                    self.logger.info(f"Recovered {len(parameters)} parameters from malformed XML")
                    return parameters
                else:
                    # If we can't recover, log the error and return empty
                    self.logger.error(f"Unable to recover parameters XML parsing.")
                    return []
            
            # Normal processing of well-formed XML
            parameters = []
            
            # Find all parameter elements
            for param_elem in root.findall('.//param'):
                param = {
                    "name": param_elem.get('name', ''),
                    "default": param_elem.get('default', '')
                }
                
                # Get any additional attributes
                for attr_name, attr_value in param_elem.attrib.items():
                    if attr_name not in ['name', 'default']:
                        param[attr_name] = attr_value
                
                parameters.append(param)
            
            self.logger.info(f"Successfully parsed {len(parameters)} test parameters")
            return parameters
        except Exception as e:
            self.logger.error(f"Error parsing parameters XML: {str(e)}", exc_info=True)
            # Return an empty list instead of raising to maintain robustness
            return []
    
    def parse_data_source(self, data_source: str) -> List[Dict[str, Any]]:
        """
        Parse the local data source containing parameter values.
        
        Args:
            data_source: String containing parameter values
            
        Returns:
            List of parameter value sets
        """
        if not data_source:
            return []
        
        try:
            # Clean up XML if needed
            clean_xml = data_source.strip()
            
            # Some XML might be wrapped in CDATA, detect and handle it
            if "<![CDATA[" in clean_xml and "]]>" in clean_xml:
                self.logger.debug("Detected CDATA in data source XML, extracting content")
                start_idx = clean_xml.find("<![CDATA[") + 9
                end_idx = clean_xml.rfind("]]>")
                if start_idx > 0 and end_idx > start_idx:
                    clean_xml = clean_xml[start_idx:end_idx]
            
            # Ensure it has proper XML structure
            if not clean_xml.startswith("<?xml") and not clean_xml.startswith("<LocalDataSource"):
                clean_xml = f"<?xml version='1.0' encoding='UTF-8'?><LocalDataSource>{clean_xml}</LocalDataSource>"
            elif not clean_xml.startswith("<?xml") and clean_xml.startswith("<LocalDataSource"):
                clean_xml = f"<?xml version='1.0' encoding='UTF-8'?>{clean_xml}"
                
            self.logger.debug(f"Parsing data source XML with size: {len(clean_xml)} bytes")
            
            # Parse the XML
            try:
                root = ET.fromstring(clean_xml)
            except ET.ParseError as xml_error:
                self.logger.warning(f"Data source XML parsing error: {str(xml_error)}")
                # For data source, it's hard to recover manually, so return empty
                return []
            
            # The data source is typically organized as a table with rows and columns
            value_sets = []
            
            # Check for different possible XML structures
            # Azure DevOps can store the data in different formats
            
            # Check for table/row/column structure (most common)
            row_elems = root.findall('.//table/row')
            if row_elems:
                self.logger.debug(f"Found table/row/column structure with {len(row_elems)} rows")
                for row_elem in row_elems:
                    value_set = {}
                    for col_elem in row_elem.findall('./column'):
                        name = col_elem.get('name', '')
                        value = col_elem.text or ''
                        if name:
                            value_set[name] = value.strip()
                    
                    # Only add non-empty value sets
                    if value_set:
                        value_sets.append(value_set)
                
                return value_sets
            
            # Check for data/row structure (alternative format)
            row_elems = root.findall('.//data/row')
            if row_elems:
                self.logger.debug(f"Found data/row structure with {len(row_elems)} rows")
                for row_elem in row_elems:
                    value_set = {}
                    for attr_name, attr_value in row_elem.attrib.items():
                        value_set[attr_name] = attr_value
                    
                    # Only add non-empty value sets
                    if value_set:
                        value_sets.append(value_set)
                
                return value_sets
            
            # Check for direct key-value pairs (simplest format)
            value_elems = root.findall('./value')
            if value_elems:
                self.logger.debug(f"Found simple value structure with {len(value_elems)} values")
                value_set = {}
                for value_elem in value_elems:
                    name = value_elem.get('name', '')
                    value = value_elem.text or ''
                    if name:
                        value_set[name] = value.strip()
                
                # Return as a single value set if not empty
                if value_set:
                    value_sets.append(value_set)
                
                return value_sets
            
            # If we reach here, we couldn't find a recognized structure
            self.logger.warning("Could not identify a recognized structure in data source XML")
            return []
        except Exception as e:
            self.logger.error(f"Error parsing data source: {str(e)}", exc_info=True)
            # Return an empty list instead of raising to maintain robustness
            return []
    
    def enhance_test_cases(self, test_cases: List[Dict[str, Any]], work_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Enhance test cases with work item data.
        
        Args:
            test_cases: List of test cases
            work_items: List of processed work items
            
        Returns:
            List of enhanced test cases
        """
        # Create a mapping of work item IDs to work items for fast lookup
        work_item_map = {}
        for work_item in work_items:
            if "id" in work_item:
                work_item_map[work_item["id"]] = work_item
        
        enhanced_test_cases = []
        
        for test_case in test_cases:
            # Create a copy of the test case
            enhanced_test_case = test_case.copy()
            
            # Add work item data if available
            if "workItemId" in test_case and test_case["workItemId"]:
                work_item_id = test_case["workItemId"]
                if work_item_id in work_item_map:
                    work_item = work_item_map[work_item_id]
                    
                    # Add selected work item properties
                    enhanced_test_case["work_item_data"] = {
                        "id": work_item.get("id"),
                        "rev": work_item.get("rev"),
                        "fields": work_item.get("fields"),
                        "test_steps": work_item.get("test_steps", []),
                        "test_parameters": work_item.get("test_parameters", []),
                        "parameter_values": work_item.get("parameter_values", [])
                    }
                else:
                    self.logger.warning(f"Work item {work_item_id} not found for test case {test_case.get('id', 'unknown')}")
            
            enhanced_test_cases.append(enhanced_test_case)
        
        self.logger.info(f"Enhanced {len(enhanced_test_cases)} test cases with work item data")
        return enhanced_test_cases
    
    def save_work_items(self, work_items: List[Dict[str, Any]], output_path: str) -> None:
        """
        Save work items to a JSON file.
        
        Args:
            work_items: List of work items
            output_path: Path to save the file
        """
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(work_items, f, indent=2, ensure_ascii=False)
            self.logger.info(f"Saved {len(work_items)} work items to {output_path}")
        except Exception as e:
            self.logger.error(f"Error saving work items to {output_path}: {str(e)}", exc_info=True)
    
    def save_enhanced_test_cases(self, test_cases: List[Dict[str, Any]], output_path: str) -> None:
        """
        Save enhanced test cases to a JSON file.
        
        Args:
            test_cases: List of enhanced test cases
            output_path: Path to save the file
        """
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(test_cases, f, indent=2, ensure_ascii=False)
            self.logger.info(f"Saved {len(test_cases)} enhanced test cases to {output_path}")
        except Exception as e:
            self.logger.error(f"Error saving enhanced test cases to {output_path}: {str(e)}", exc_info=True) 