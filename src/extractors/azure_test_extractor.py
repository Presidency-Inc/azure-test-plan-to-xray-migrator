from typing import List, Dict, Any, Optional
import asyncio
import os
import json
import logging
from datetime import datetime
import sys

# Add the project root to the Python path
file_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if file_path not in sys.path:
    sys.path.append(file_path)

from src.utils.azure_client import AzureDevOpsClient
from src.utils.csv_parser import AzureTestPlanCSVParser
from src.config.config import AzureConfig
from src.work_items.work_item_extractor import WorkItemExtractor
from src.work_items.work_item_processor import WorkItemProcessor
from pathlib import Path

class AzureTestExtractor:
    def __init__(self, config: AzureConfig):
        self.config = config
        self.client = AzureDevOpsClient(config)
        self.output_dir = os.path.join("output", "data", "extraction")
        os.makedirs(self.output_dir, exist_ok=True)
        self.logger = logging.getLogger(__name__)
        
    async def extract_all(self) -> Dict[str, Any]:
        """Extract all test plans data with all related entities"""
        self.logger.info("Starting extraction of all Azure Test Plans data")
        
        # Create a timestamp-based directory for this extraction
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        extraction_dir = os.path.join(self.output_dir, timestamp)
        os.makedirs(extraction_dir, exist_ok=True)
        
        # Extract all test plans with their hierarchical data
        test_plans = await self.extract_test_plans()
        
        # Extract additional entities
        test_configurations = await self.extract_test_configurations()
        test_variables = await self.extract_test_variables()
        test_points = []
        test_results = []
        
        # For each test plan, extract all test points and results
        for plan in test_plans:
            plan_points = await self.extract_test_points_for_plan(plan["id"])
            test_points.extend(plan_points)
            
            # Extract test results for each test point
            for point in plan_points:
                point_results = await self.extract_test_results_for_point(point["id"])
                test_results.extend(point_results)
        
        # Create the complete extraction result
        extraction_result = {
            "test_plans": test_plans,
            "test_configurations": test_configurations,
            "test_variables": test_variables,
            "test_points": test_points,
            "test_results": test_results,
            "extraction_path": extraction_dir
        }
        
        # Save the extraction data
        self._save_extraction_data(extraction_result, extraction_dir)
        
        self.logger.info(f"Extraction completed successfully. Data saved in: {extraction_dir}")
        return extraction_result
    
    async def extract_from_csv(self, csv_path: str, modular_output: bool = False) -> Dict[str, Any]:
        """
        Extract specific test plans mentioned in a CSV file
        
        Args:
            csv_path: Path to CSV file containing Azure Test Plan URLs
            modular_output: If True, save each test plan extraction in separate files
            
        Returns:
            Dictionary containing extracted data
        """
        self.logger.info(f"Starting extraction of specific Azure Test Plans from CSV: {csv_path}")
        
        # Parse the CSV file
        parser = AzureTestPlanCSVParser(csv_path)
        csv_data = parser.parse()
        plan_suite_mapping = csv_data['plan_suite_mapping']
        
        # Create a timestamp-based directory for this extraction
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        extraction_dir = os.path.join(self.output_dir, timestamp)
        os.makedirs(extraction_dir, exist_ok=True)
        
        # Directory for modular output (if enabled)
        modular_dir = os.path.join(extraction_dir, "modular") if modular_output else None
        if modular_output:
            os.makedirs(modular_dir, exist_ok=True)
        
        # Extract common data (shared across all plans)
        test_configurations = await self.extract_test_configurations()
        test_variables = await self.extract_test_variables()
        
        # Prepare for monolithic output
        all_test_plans = []
        all_test_points = []
        all_test_results = []
        
        # Extract test plans and associated data
        for plan_id, suite_ids in plan_suite_mapping.items():
            self.logger.info(f"Extracting plan ID: {plan_id} with {len(suite_ids)} suites")
            plan = await self._extract_specific_test_plan(int(plan_id), [int(suite_id) for suite_id in suite_ids])
            
            if not plan:
                self.logger.warning(f"Plan ID {plan_id} could not be extracted, skipping")
                continue
                
            # Extract test points and results for this plan
            plan_points = await self.extract_test_points_for_plan(plan["id"])
            plan_results = []
            
            for point in plan_points:
                point_results = await self.extract_test_results_for_point(point["id"])
                plan_results.extend(point_results)
            
            # Save modular extraction if enabled
            if modular_output:
                plan_data = {
                    "test_plans": [plan],
                    "test_points": plan_points,
                    "test_results": plan_results,
                    "test_configurations": test_configurations,
                    "test_variables": test_variables
                }
                
                plan_dir = os.path.join(modular_dir, f"plan_{plan_id}")
                os.makedirs(plan_dir, exist_ok=True)
                self._save_extraction_data(plan_data, plan_dir)
                self.logger.info(f"Saved modular extraction for plan {plan_id} to {plan_dir}")
            
            # Add to monolithic collection
            all_test_plans.append(plan)
            all_test_points.extend(plan_points)
            all_test_results.extend(plan_results)
        
        # Create the complete extraction result for monolithic output
        extraction_result = {
            "test_plans": all_test_plans,
            "test_configurations": test_configurations,
            "test_variables": test_variables,
            "test_points": all_test_points,
            "test_results": all_test_results,
            "csv_mapping": csv_data,
            "extraction_path": extraction_dir
        }
        
        # Save the monolithic extraction data
        self._save_extraction_data(extraction_result, extraction_dir)
        
        self.logger.info(f"Extraction of specific test plans completed successfully.")
        self.logger.info(f"Monolithic data saved in: {extraction_dir}")
        if modular_output:
            self.logger.info(f"Modular data saved in: {modular_dir}")
            
        return extraction_result
        
    async def _extract_specific_test_plan(self, plan_id: int, suite_ids: List[int]) -> Dict:
        """Extract a specific test plan with only specified suites"""
        self.logger.info(f"Extracting test plan ID: {plan_id} with specific suites: {suite_ids}")
        try:
            # Get the plan details - don't use await as method is not async anymore
            plan = self.client.get_test_plan_by_id(
                project=self.config.project_name, 
                plan_id=plan_id
            )
            
            if not plan:
                self.logger.warning(f"Test plan {plan_id} not found")
                raise ValueError(f"Test plan {plan_id} not found")
            
            # Get the complete suite hierarchy to properly handle nested suites
            suite_hierarchy = self.client.get_test_suite_hierarchy(
                project=self.config.project_name,
                plan_id=plan_id
            )
            
            # Log all suites in the hierarchy
            self.logger.info(f"Found {len(suite_hierarchy)} suites in plan {plan_id}")
            for suite_id, suite in suite_hierarchy.items():
                parent_id = suite.parent_suite.id if hasattr(suite, 'parent_suite') and suite.parent_suite else None
                self.logger.info(f"Suite {suite_id} (Name: {suite.name}) - Parent: {parent_id}")
            
            test_plan = {
                "id": plan.id if hasattr(plan, 'id') else None,
                "name": plan.name if hasattr(plan, 'name') else None,
                "area_path": plan.area_path if hasattr(plan, 'area_path') else None,
                "iteration_path": plan.iteration_path if hasattr(plan, 'iteration_path') else None,
                "description": plan.description if hasattr(plan, 'description') else None,
                "start_date": plan.start_date if hasattr(plan, 'start_date') else None,
                "end_date": plan.end_date if hasattr(plan, 'end_date') else None,
                "state": plan.state if hasattr(plan, 'state') else None,
                "owner": self._extract_identity_ref(plan.owner) if hasattr(plan, 'owner') and plan.owner else None,
                "test_suites": []
            }
            
            # Find the root suite first (it will not have a parent_suite or have plan_id as parent)
            root_suite_id = None
            for suite_id, suite in suite_hierarchy.items():
                parent_id = suite.parent_suite.id if hasattr(suite, 'parent_suite') and suite.parent_suite else None
                if parent_id is None or parent_id == plan_id:
                    root_suite_id = suite_id
                    break
                
            if root_suite_id:
                self.logger.info(f"Found root suite ID: {root_suite_id}")
                
                # MODIFIED: Check if root suite itself is in the specified suites
                root_is_requested = root_suite_id in suite_ids
                
                # First extract the root suite with all its hierarchy
                root_suite = await self._extract_suite_with_hierarchy(
                    plan_id, 
                    root_suite_id, 
                    suite_hierarchy, 
                    include_all_suites=root_is_requested,  # If root is requested, include all its children
                    specific_suites=suite_ids
                )
                
                if root_suite:
                    test_plan["test_suites"].append(root_suite)
            else:
                # No root suite found, try to extract the specified suites directly
                self.logger.warning(f"No root suite found for plan {plan_id}, extracting specified suites directly")
                for suite_id in suite_ids:
                    try:
                        # Use the hierarchy extraction method instead of direct suite extraction
                        # This will ensure we get the complete hierarchy for each specified suite
                        suite = await self._extract_suite_with_hierarchy(
                            plan_id,
                            suite_id,
                            suite_hierarchy,
                            include_all_suites=True,  # Include all children of this specific suite
                            specific_suites=suite_ids
                        )
                        if suite:
                            test_plan["test_suites"].append(suite)
                    except Exception as e:
                        self.logger.error(f"Error extracting test suite {suite_id} from plan {plan_id}: {str(e)}")
                
            return test_plan
        except Exception as e:
            self.logger.error(f"Error extracting test plan {plan_id}: {str(e)}")
            raise

    async def _extract_suite_with_hierarchy(self, plan_id: int, suite_id: int, suite_hierarchy: Dict, include_all_suites: bool = True, specific_suites: List[int] = None) -> Optional[Dict]:
        """
        Extract a test suite with all its nested suites
        
        Args:
            plan_id: The plan ID
            suite_id: The suite ID to extract
            suite_hierarchy: Dictionary of all suites in the plan
            include_all_suites: If True, include all nested suites; if False, only include specific suites
            specific_suites: List of suite IDs to include (used when include_all_suites is False)
            
        Returns:
            Dictionary containing suite data with nested suites
        """
        self.logger.info(f"Extracting suite {suite_id} with hierarchy, include_all={include_all_suites}, specific_suites={specific_suites}")
        
        # Get the suite details
        try:
            # Use the suite from the hierarchy if available
            if suite_id in suite_hierarchy:
                suite = suite_hierarchy[suite_id]
            else:
                # Fetch the suite directly if not in hierarchy
                suite = self.client.get_test_suite_by_id(
                    project=self.config.project_name,
                    plan_id=plan_id,
                    suite_id=suite_id
                )
                
            if not suite:
                self.logger.warning(f"Suite {suite_id} not found")
                return None
            
            # Create suite dictionary
            test_suite = {
                "id": suite.id if hasattr(suite, 'id') else None,
                "name": suite.name if hasattr(suite, 'name') else None,
                "parent_suite_id": suite.parent_suite.id if hasattr(suite, 'parent_suite') and suite.parent_suite else None,
                "state": suite.state if hasattr(suite, 'state') else None,
                "suite_type": suite.suite_type if hasattr(suite, 'suite_type') else None,
                "test_cases": [],
                "child_suites": []
            }
            
            # Extract test cases if this suite is in the specific_suites list or we're including all suites
            # IMPORTANT: We're checking if this suite is specifically requested or we're including all
            should_extract_test_cases = include_all_suites or (specific_suites and suite_id in specific_suites)
            
            if should_extract_test_cases:
                self.logger.info(f"Extracting test cases for suite {suite_id}")
                test_suite["test_cases"] = await self._extract_test_cases_for_suite(plan_id, suite_id)
            else:
                self.logger.info(f"Skipping test case extraction for suite {suite_id}")
            
            # Find child suites
            child_suite_ids = []
            for child_id, child_suite in suite_hierarchy.items():
                parent_id = child_suite.parent_suite.id if hasattr(child_suite, 'parent_suite') and child_suite.parent_suite else None
                if parent_id == suite_id:
                    child_suite_ids.append(child_id)
                
            # Extract child suites recursively
            for child_id in child_suite_ids:
                # MODIFIED LOGIC: 
                # 1. Include if we're including all suites
                # 2. Include if this child is specifically requested
                # 3. ADDED: Include if this suite's parent (current suite) is specifically requested
                # This ensures we get complete hierarchies for any suite in specific_suites
                should_extract_child = (
                    include_all_suites or 
                    (specific_suites and child_id in specific_suites) or
                    (specific_suites and suite_id in specific_suites)  # Extract all children of a requested suite
                )
                
                if should_extract_child:
                    child_suite = await self._extract_suite_with_hierarchy(
                        plan_id, 
                        child_id, 
                        suite_hierarchy, 
                        include_all_suites, 
                        specific_suites
                    )
                    if child_suite:
                        test_suite["child_suites"].append(child_suite)
                    
            return test_suite
        except Exception as e:
            self.logger.error(f"Error extracting suite {suite_id} with hierarchy: {str(e)}")
            return None

    async def _extract_test_cases_for_suite(self, plan_id: int, suite_id: int) -> List[Dict]:
        """Extract test cases for a specific suite"""
        self.logger.info(f"Extracting test cases for plan ID: {plan_id}, suite ID: {suite_id}")
        test_cases = []
        
        try:
            # Get test cases
            suite_test_cases = self.client.get_test_cases(
                project=self.config.project_name,
                plan_id=plan_id,
                suite_id=suite_id
            )
            
            # Log the number of test cases found
            test_case_count = len(suite_test_cases) if suite_test_cases else 0
            self.logger.info(f"Found {test_case_count} test cases for suite {suite_id}")
            
            if not suite_test_cases:
                return []
            
            # Process each test case
            for case in suite_test_cases:
                # Log the test case details for debugging
                self.logger.info(f"Processing test case ID: {case.id if hasattr(case, 'id') else 'Unknown'}")
                self.logger.info(f"Test case attributes: {dir(case)}")
                
                # Extract work item details safely
                work_item_id = None
                work_item_url = None
                if hasattr(case, 'work_item') and case.work_item:
                    work_item_id = case.work_item.id if hasattr(case.work_item, 'id') else None
                    work_item_url = case.work_item.url if hasattr(case.work_item, 'url') else None
                
                # Create test case dictionary with all available attributes
                test_case = {
                    "id": case.id if hasattr(case, 'id') else None,
                    "name": case.name if hasattr(case, 'name') else None,
                    "work_item_id": work_item_id,
                    "work_item_url": work_item_url,
                    "order": case.order if hasattr(case, 'order') else None,
                    "priority": case.priority if hasattr(case, 'priority') else None,
                    "description": case.description if hasattr(case, 'description') else None,
                }
                
                # Extract additional fields if available
                if hasattr(case, 'steps_html'):
                    test_case["steps_html"] = case.steps_html
                elif hasattr(case, 'steps'):
                    test_case["steps"] = case.steps
                    
                # Extract acceptance criteria if available
                if hasattr(case, 'acceptance_criteria'):
                    test_case["acceptance_criteria"] = case.acceptance_criteria
                
                # Extract test steps if case has an ID
                case_id = case.id if hasattr(case, 'id') else None
                if case_id:
                    steps = await self._extract_test_steps(case_id)
                    test_case["steps"] = steps
                else:
                    test_case["steps"] = []
                    
                # Add the test case to the list
                test_cases.append(test_case)
        except Exception as e:
            self.logger.error(f"Error extracting test cases for suite {suite_id} from plan {plan_id}: {str(e)}", exc_info=True)
        
        return test_cases

    async def _extract_specific_test_suite(self, plan_id: int, suite_id: int) -> Dict:
        """Extract a specific test suite by ID (without hierarchy)"""
        self.logger.info(f"Extracting test suite ID: {suite_id} from plan ID: {plan_id}")
        try:
            # Get the suite details - don't use await as method is not async anymore
            suite = self.client.get_test_suite_by_id(
                project=self.config.project_name,
                plan_id=plan_id,
                suite_id=suite_id
            )
            
            if not suite:
                self.logger.warning(f"Test suite {suite_id} not found")
                raise ValueError(f"Test suite {suite_id} not found")
            
            test_suite = {
                "id": suite.id if hasattr(suite, 'id') else None,
                "name": suite.name if hasattr(suite, 'name') else None,
                "parent_suite_id": suite.parent_suite.id if hasattr(suite, 'parent_suite') and suite.parent_suite else None,
                "state": suite.state if hasattr(suite, 'state') else None,
                "test_cases": await self._extract_test_cases_for_suite(plan_id, suite_id),
                "child_suites": []  # When using this method directly, we don't extract child suites
            }
            
            return test_suite
        except Exception as e:
            self.logger.error(f"Error extracting test suite {suite_id} from plan {plan_id}: {str(e)}", exc_info=True)
            raise
        
    async def _extract_test_steps(self, test_case_id: int) -> List[Dict]:
        """Extract all test steps for a given test case"""
        if not test_case_id:
            self.logger.warning(f"No test case ID provided, skipping test steps extraction")
            return []
        
        self.logger.info(f"Extracting test steps for test case ID: {test_case_id}")
        steps = []
        
        try:
            # Use client directly without await
            test_steps = self.client.test_client.get_test_steps(
                project=self.config.project_name,
                test_case_id=test_case_id
            )
            
            for step in test_steps:
                test_step = {
                    "id": step.id,
                    "action": step.action if hasattr(step, 'action') else None,
                    "expected_result": step.expected_result if hasattr(step, 'expected_result') else None,
                    "step_identifier": step.step_identifier if hasattr(step, 'step_identifier') else None,
                    "parameters": step.parameters if hasattr(step, 'parameters') else None,
                    "data": step.data if hasattr(step, 'data') else None,
                    "title": step.title if hasattr(step, 'title') else None,
                    "parameters_string": step.parameters_string if hasattr(step, 'parameters_string') else None
                }
                steps.append(test_step)
        except Exception as e:
            self.logger.warning(f"Error extracting test steps for test case {test_case_id}: {str(e)}")
        
        return steps
    
    async def extract_test_plans(self) -> List[Dict]:
        """Extract all test plans with their hierarchical data"""
        self.logger.info("Extracting test plans")
        test_plans = []
        
        # Get all test plans - remove await
        plans = self.client.test_client.get_test_plans(
            project=self.config.project_name
        )
        
        for plan in plans:
            test_plan = {
                "id": plan.id,
                "name": plan.name,
                "area_path": plan.area_path,
                "iteration_path": plan.iteration_path,
                "description": plan.description,
                "start_date": plan.start_date,
                "end_date": plan.end_date,
                "state": plan.state,
                "owner": self._extract_identity_ref(plan.owner) if hasattr(plan, 'owner') else None,
                "revision": plan.revision if hasattr(plan, 'revision') else None,
                "build_id": plan.build_id if hasattr(plan, 'build_id') else None,
                "build_definition": self._extract_build_definition_ref(plan.build_definition) if hasattr(plan, 'build_definition') else None,
                "release_environment_definition": self._extract_release_env_def(plan.release_environment_definition) if hasattr(plan, 'release_environment_definition') else None,
                "test_outcome_settings": plan.test_outcome_settings.sync_outcome_across_suites if hasattr(plan, 'test_outcome_settings') else None,
                "updated_date": plan.updated_date if hasattr(plan, 'updated_date') else None,
                "updated_by": self._extract_identity_ref(plan.updated_by) if hasattr(plan, 'updated_by') else None,
                "test_suites": await self._extract_test_suites(plan.id)
            }
            test_plans.append(test_plan)
            
        return test_plans
    
    async def _extract_test_suites(self, plan_id: int) -> List[Dict]:
        """Extract all test suites for a given test plan"""
        self.logger.info(f"Extracting test suites for plan ID: {plan_id}")
        suites = []
        
        # Remove await
        plan_suites = self.client.test_client.get_test_suites(
            project=self.config.project_name,
            plan_id=plan_id
        )
        
        for suite in plan_suites:
            test_suite = {
                "id": suite.id,
                "name": suite.name,
                "parent_suite_id": suite.parent_suite.id if hasattr(suite, 'parent_suite') and suite.parent_suite else None,
                "default_configurations": self._extract_test_configurations_refs(suite.default_configurations) if hasattr(suite, 'default_configurations') else None,
                "inherit_default_configurations": suite.inherit_default_configurations if hasattr(suite, 'inherit_default_configurations') else True,
                "state": suite.state if hasattr(suite, 'state') else None,
                "last_updated_by": self._extract_identity_ref(suite.last_updated_by) if hasattr(suite, 'last_updated_by') else None,
                "last_updated_date": suite.last_updated_date if hasattr(suite, 'last_updated_date') else None,
                "suite_type": suite.suite_type if hasattr(suite, 'suite_type') else None,
                "requirement_id": suite.requirement_id if hasattr(suite, 'requirement_id') else None,
                "query_string": suite.query_string if hasattr(suite, 'query_string') else None,
                "test_cases": await self._extract_test_cases(plan_id, suite.id)
            }
            suites.append(test_suite)
            
        return suites
    
    async def _extract_test_cases(self, plan_id: int, suite_id: int) -> List[Dict]:
        """Extract all test cases for a given test suite"""
        self.logger.info(f"Extracting test cases for plan ID: {plan_id}, suite ID: {suite_id}")
        test_cases = []
        
        # Remove await
        suite_test_cases = self.client.test_client.get_test_cases(
            project=self.config.project_name,
            plan_id=plan_id,
            suite_id=suite_id
        )
        
        for case in suite_test_cases:
            test_case = {
                "id": case.id,
                "name": case.name,
                "work_item_id": case.work_item.id if hasattr(case, 'work_item') and case.work_item else None,
                "work_item_url": case.work_item.url if hasattr(case, 'work_item') and case.work_item else None,
                "order": case.order if hasattr(case, 'order') else None,
                "point_assignments": self._extract_point_assignments(case.point_assignments) if hasattr(case, 'point_assignments') else None,
                "priority": case.priority if hasattr(case, 'priority') else None,
                "description": case.description if hasattr(case, 'description') else None,
                "steps": await self._extract_test_steps(case.id if hasattr(case, 'id') else None)
            }
            test_cases.append(test_case)
            
        return test_cases
    
    async def extract_test_configurations(self) -> List[Dict]:
        """Extract all test configurations"""
        self.logger.info("Extracting test configurations")
        configurations = []
        
        try:
            # Use client method directly (not async)
            config_list = self.client.get_test_configurations(
                project=self.config.project_name
            )
            
            for config in config_list:
                configuration = {
                    "id": config.id if hasattr(config, 'id') else None,
                    "name": config.name if hasattr(config, 'name') else None,
                    "description": config.description if hasattr(config, 'description') else None,
                    "state": config.state if hasattr(config, 'state') else None,
                    "values": config.values if hasattr(config, 'values') else None,
                    "is_default": config.is_default if hasattr(config, 'is_default') else False,
                    "project": config.project.name if hasattr(config, 'project') and config.project else None
                }
                configurations.append(configuration)
        except Exception as e:
            self.logger.warning(f"Error extracting test configurations: {str(e)}")
            
        return configurations
    
    async def extract_test_variables(self) -> List[Dict]:
        """Extract all test variables"""
        self.logger.info("Extracting test variables")
        variables = []
        
        try:
            # Use client method directly (not async)
            var_list = self.client.get_test_variables(
                project=self.config.project_name
            )
            
            for var in var_list:
                variable = {
                    "id": var.id if hasattr(var, 'id') else None,
                    "name": var.name if hasattr(var, 'name') else None,
                    "description": var.description if hasattr(var, 'description') else None,
                    "values": var.values if hasattr(var, 'values') else None,
                    "scope": var.scope if hasattr(var, 'scope') else None
                }
                variables.append(variable)
        except Exception as e:
            self.logger.warning(f"Error extracting test variables: {str(e)}")
            
        return variables
    
    async def extract_test_points_for_plan(self, plan_id: int) -> List[Dict]:
        """Extract all test points for a given test plan"""
        self.logger.info(f"Extracting test points for plan ID: {plan_id}")
        points = []
        
        try:
            # Get all suites for this plan - remove await
            suites = self.client.test_client.get_test_suites(
                project=self.config.project_name,
                plan_id=plan_id
            )
            
            # For each suite, get the test points
            for suite in suites:
                # Remove await
                suite_points = self.client.test_client.get_points(
                    project=self.config.project_name,
                    plan_id=plan_id,
                    suite_id=suite.id
                )
                
                for point in suite_points:
                    test_point = {
                        "id": point.id,
                        "test_case_id": point.test_case.id if hasattr(point, 'test_case') and point.test_case else None,
                        "test_case_title": point.test_case.name if hasattr(point, 'test_case') and point.test_case else None,
                        "configuration_id": point.configuration.id if hasattr(point, 'configuration') and point.configuration else None,
                        "configuration_name": point.configuration.name if hasattr(point, 'configuration') and point.configuration else None,
                        "tester": self._extract_identity_ref(point.tester) if hasattr(point, 'tester') and point.tester else None,
                        "outcome": point.outcome if hasattr(point, 'outcome') else None,
                        "state": point.state if hasattr(point, 'state') else None,
                        "plan_id": plan_id,
                        "suite_id": suite.id
                    }
                    points.append(test_point)
        except Exception as e:
            self.logger.warning(f"Error extracting test points for plan {plan_id}: {str(e)}")
            
        return points
    
    async def extract_test_results_for_point(self, point_id: int) -> List[Dict]:
        """Extract all test results for a given test point"""
        self.logger.info(f"Extracting test results for point ID: {point_id}")
        results = []
        
        try:
            # Remove await
            test_results = self.client.test_client.get_test_results(
                project=self.config.project_name,
                point_ids=[point_id]
            )
            
            for result in test_results:
                test_result = {
                    "id": result.id,
                    "test_plan_id": result.test_plan.id if hasattr(result, 'test_plan') and result.test_plan else None,
                    "test_point_id": point_id,
                    "test_case_id": result.test_case.id if hasattr(result, 'test_case') and result.test_case else None,
                    "test_run_id": result.test_run.id if hasattr(result, 'test_run') and result.test_run else None,
                    "configuration_id": result.configuration.id if hasattr(result, 'configuration') and result.configuration else None,
                    "outcome": result.outcome if hasattr(result, 'outcome') else None,
                    "error_message": result.error_message if hasattr(result, 'error_message') else None,
                    "comment": result.comment if hasattr(result, 'comment') else None,
                    "state": result.state if hasattr(result, 'state') else None,
                    "completed_date": result.completed_date if hasattr(result, 'completed_date') else None,
                    "duration_in_ms": result.duration_in_ms if hasattr(result, 'duration_in_ms') else None,
                    "started_date": result.started_date if hasattr(result, 'started_date') else None,
                    "run_by": self._extract_identity_ref(result.run_by) if hasattr(result, 'run_by') and result.run_by else None,
                    "attachments": result.attachments if hasattr(result, 'attachments') else None,
                }
                results.append(test_result)
        except Exception as e:
            self.logger.warning(f"Error extracting test results for point {point_id}: {str(e)}")
            
        return results
    
    def _extract_identity_ref(self, identity_ref: Any) -> Optional[Dict]:
        """Extract identity reference data"""
        if not identity_ref:
            return None
        
        return {
            "id": identity_ref.id if hasattr(identity_ref, 'id') else None,
            "display_name": identity_ref.display_name if hasattr(identity_ref, 'display_name') else None,
            "unique_name": identity_ref.unique_name if hasattr(identity_ref, 'unique_name') else None,
            "url": identity_ref.url if hasattr(identity_ref, 'url') else None,
        }
    
    def _extract_build_definition_ref(self, build_def: Any) -> Optional[Dict]:
        """Extract build definition reference data"""
        if not build_def:
            return None
        
        return {
            "id": build_def.id if hasattr(build_def, 'id') else None,
            "name": build_def.name if hasattr(build_def, 'name') else None,
        }
    
    def _extract_release_env_def(self, rel_env_def: Any) -> Optional[Dict]:
        """Extract release environment definition reference data"""
        if not rel_env_def:
            return None
        
        return {
            "definition_id": rel_env_def.definition_id if hasattr(rel_env_def, 'definition_id') else None,
            "environment_definition_id": rel_env_def.environment_definition_id if hasattr(rel_env_def, 'environment_definition_id') else None,
        }
    
    def _extract_test_configurations_refs(self, configs: List[Any]) -> List[Dict]:
        """Extract test configuration references data"""
        if not configs:
            return []
        
        return [{
            "id": config.id if hasattr(config, 'id') else None,
            "name": config.name if hasattr(config, 'name') else None,
        } for config in configs]
    
    def _extract_point_assignments(self, assignments: List[Any]) -> List[Dict]:
        """Extract point assignments data"""
        if not assignments:
            return []
        
        return [{
            "configuration_id": assignment.configuration_id if hasattr(assignment, 'configuration_id') else None,
            "tester": self._extract_identity_ref(assignment.tester) if hasattr(assignment, 'tester') and assignment.tester else None,
        } for assignment in assignments]
    
    def _save_extraction_data(self, data: Dict[str, Any], output_dir: str) -> None:
        """Save extraction data to JSON files"""
        # Save each entity type to a separate file
        for entity_type, entities in data.items():
            # Skip the extraction_path field
            if entity_type == "extraction_path":
                continue
                
            filename = f"{entity_type}.json"
            file_path = os.path.join(output_dir, filename)
            
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(entities, f, indent=2, default=str)
            
            self.logger.info(f"Saved {len(entities) if isinstance(entities, list) else 1} {entity_type} to {file_path}")
        
        # Also save a summary file
        summary = {
            "extraction_date": datetime.now().isoformat(),
            "project": self.config.project_name,
            "organization": self.config.organization_url,
            "counts": {
                entity_type: len(entities) if isinstance(entities, list) else 1 
                for entity_type, entities in data.items() 
                if entity_type not in ["extraction_path", "csv_mapping"]
            }
        }
        
        summary_path = os.path.join(output_dir, "extraction_summary.json")
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)
        
        self.logger.info(f"Saved extraction summary to {summary_path}")
    
    async def extract_entire_project(self, project: str = None) -> Dict[str, Any]:
        """
        Extract all test plans, suites, and test cases from an entire Azure DevOps project
        using only modern API endpoints.
        
        Args:
            project: Project name (defaults to the one in config)
            
        Returns:
            Dictionary containing extracted data and status information
        """
        project = project or self.config.project_name
        
        # Initialize result dictionary
        result = {
            "project": project,
            "timestamp": datetime.now().isoformat(),
            "status": "In Progress"
        }
        
        # Create a timestamp-based directory for this extraction
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        extraction_dir = Path(os.path.join(self.output_dir, timestamp))
        os.makedirs(extraction_dir, exist_ok=True)
        
        self.logger.info(f"Starting extraction of entire project: {project}")
        self.logger.info(f"Output directory: {extraction_dir}")
        
        try:
            # 1. Get all test plans using the modern API
            self.logger.info(f"Fetching all test plans from project {project}")
            test_plans = await self.client.get_all_test_plans_modern(project)
            
            if not test_plans:
                error_msg = f"No test plans found in project {project}"
                self.logger.error(error_msg)
                result["error"] = error_msg
                result["status"] = "ERROR: No test plans found"
                
                # Save error summary
                with open(extraction_dir / 'extraction_summary.json', 'w') as f:
                    json.dump({
                        "project_name": project,
                        "extraction_timestamp": timestamp,
                        "status": "ERROR: No test plans found",
                        "error": error_msg
                    }, f, indent=2)
                
                return result
                
            result["test_plans"] = test_plans
            result["total_plans"] = len(test_plans)
            self.logger.info(f"Found {len(test_plans)} test plans")
            
            # 2. For each test plan, fetch all test suites using modern API
            plan_ids = [plan["id"] for plan in test_plans]
            all_suites = []
            all_test_cases = []
            
            total_expected_cases = 0
            for plan_id in plan_ids:
                plan_name = next((plan["name"] for plan in test_plans if plan["id"] == plan_id), f"Plan {plan_id}")
                self.logger.info(f"Processing test plan {plan_id}: {plan_name}")
                
                try:
                    # Get all suites for this plan using modern API
                    suites = await self.client.get_all_test_suites_modern(project, plan_id)
                    self.logger.info(f"Found {len(suites)} suites in plan {plan_id}")
                    
                    if not suites:
                        self.logger.warning(f"No suites found in plan {plan_id}")
                        continue
                    
                    # Track parent-child relationships
                    for suite in suites:
                        suite["planId"] = plan_id
                    
                    # Get test cases for each suite using modern API
                    for suite in suites:
                        suite_id = suite["id"]
                        suite_name = suite.get("name", f"Suite {suite_id}")
                        self.logger.info(f"Processing suite {suite_id}: {suite_name}")
                        
                        try:
                            # Get test cases for this suite using modern API
                            test_cases = await self.client.get_test_cases_for_suite_modern(
                                project, plan_id, suite_id
                            )
                            self.logger.info(f"Found {len(test_cases)} test cases in suite {suite_id}")
                            total_expected_cases += len(test_cases)
                            
                            # Add plan and suite IDs to each test case for reference
                            for tc in test_cases:
                                tc["planId"] = plan_id
                                tc["suiteId"] = suite_id
                            
                            all_test_cases.extend(test_cases)
                            
                        except Exception as e:
                            error_msg = f"Error fetching test cases for suite {suite_id}: {str(e)}"
                            self.logger.error(error_msg, exc_info=True)
                            result["errors"] = result.get("errors", []) + [error_msg]
                    
                    all_suites.extend(suites)
                    
                except Exception as e:
                    error_msg = f"Error processing test plan {plan_id}: {str(e)}"
                    self.logger.error(error_msg, exc_info=True)
                    result["errors"] = result.get("errors", []) + [error_msg]
            
            # Update result with all found entities
            result["test_suites"] = all_suites
            result["test_cases"] = all_test_cases
            
            # Set status based on results
            if not all_suites or not all_test_cases:
                if not all_suites:
                    error_msg = "No test suites were extracted"
                    self.logger.warning(error_msg)
                    result["errors"] = result.get("errors", []) + [error_msg]
                
                if not all_test_cases:
                    error_msg = "No test cases were extracted"
                    self.logger.warning(error_msg)
                    result["errors"] = result.get("errors", []) + [error_msg]
                
                result["status"] = "WARNING: Partial extraction"
            else:
                result["status"] = "Success"
            
            # 3. Extract work items for test cases
            if all_test_cases:
                self.logger.info("Extracting work item data for test cases...")
                try:
                    # Initialize work item extractor and processor
                    work_item_extractor = WorkItemExtractor(self.client)
                    work_item_processor = WorkItemProcessor()
                    
                    # Extract work item IDs from test cases
                    work_item_ids = work_item_extractor.extract_work_item_ids(all_test_cases)
                    self.logger.info(f"Found {len(work_item_ids)} unique work item IDs to extract")
                    
                    # Get fields needed for test cases
                    test_case_fields = work_item_extractor.get_test_case_fields()
                    
                    # Extract work items
                    extraction_result = await work_item_extractor.extract_test_case_work_items(
                        work_item_ids, 
                        test_case_fields
                    )
                    
                    # Process the work items to extract structured data
                    work_items = extraction_result.get("work_items", [])
                    self.logger.info(f"Processing {len(work_items)} work items")
                    processed_work_items = work_item_processor.process_work_items(work_items)
                    
                    # Enhance test cases with work item data
                    enhanced_test_cases = work_item_processor.enhance_test_cases(all_test_cases, processed_work_items)
                    
                    # Update result with work item data
                    result["work_items"] = processed_work_items
                    result["enhanced_test_cases"] = enhanced_test_cases
                    result["work_item_extraction_status"] = extraction_result.get("status", "Unknown")
                    
                    # Save work items
                    work_item_processor.save_work_items(processed_work_items, str(extraction_dir / 'work_items.json'))
                    
                    # Save enhanced test cases
                    work_item_processor.save_enhanced_test_cases(enhanced_test_cases, str(extraction_dir / 'enhanced_test_cases.json'))
                    
                    self.logger.info(f"Work item extraction completed: {extraction_result.get('status', 'Unknown')}")
                except Exception as e:
                    error_msg = f"Error extracting work items: {str(e)}"
                    self.logger.error(error_msg, exc_info=True)
                    result["errors"] = result.get("errors", []) + [error_msg]
                    result["work_item_extraction_status"] = "ERROR: Failed to extract work items"
            
            # 4. Save the extracted data
            self.logger.info(f"Extraction completed. Saving results...")
            
            # Validate test case count
            self.logger.info(f"Expected test cases: {total_expected_cases}, Actual: {len(all_test_cases)}")
            if total_expected_cases != len(all_test_cases):
                warning_msg = f"WARNING: Test case count mismatch. Expected {total_expected_cases} but got {len(all_test_cases)}"
                self.logger.warning(warning_msg)
                result["warnings"] = result.get("warnings", []) + [warning_msg]
            
            # Save test plans
            with open(extraction_dir / 'test_plans.json', 'w') as f:
                json.dump(result["test_plans"], f, indent=2)
            self.logger.info(f"Saved {len(result['test_plans'])} test plans")
            
            # Save test suites
            with open(extraction_dir / 'test_suites.json', 'w') as f:
                json.dump(result["test_suites"], f, indent=2)
            self.logger.info(f"Saved {len(result['test_suites'])} test suites")
            
            # Save test cases
            with open(extraction_dir / 'test_cases.json', 'w') as f:
                json.dump(result["test_cases"], f, indent=2)
            self.logger.info(f"Saved {len(result['test_cases'])} test cases")
            
            # Create summary information
            summary = {
                "project_name": project,
                "extraction_timestamp": timestamp,
                "total_plans": len(result["test_plans"]),
                "total_suites": len(result["test_suites"]),
                "total_test_cases": len(result["test_cases"])
            }
            
            # Add work item information if available
            if "work_items" in result:
                summary["total_work_items"] = len(result["work_items"])
                summary["work_item_extraction_status"] = result.get("work_item_extraction_status", "Unknown")
            
            summary["status"] = result["status"]
            
            # Add errors and warnings if any
            if "errors" in result:
                summary["errors"] = result["errors"]
            if "warnings" in result:
                summary["warnings"] = result["warnings"]
            
            # Save summary
            with open(extraction_dir / 'extraction_summary.json', 'w') as f:
                json.dump(summary, f, indent=2)
            
            self.logger.info(f"Saved extraction results to {extraction_dir}")
            return result
            
        except Exception as e:
            error_msg = f"Error extracting project {project}: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            result["error"] = error_msg
            result["status"] = "ERROR: Extraction failed"
            
            # Save error summary
            with open(extraction_dir / 'extraction_summary.json', 'w') as f:
                json.dump({
                    "project_name": project,
                    "extraction_timestamp": timestamp,
                    "status": "ERROR: Extraction failed",
                    "error": error_msg
                }, f, indent=2)
                
            return result 