from typing import List, Dict, Any, Optional
import asyncio
import os
import json
import logging
from datetime import datetime
from utils.azure_client import AzureDevOpsClient
from utils.csv_parser import AzureTestPlanCSVParser
from config.config import AzureConfig

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
        
    async def _extract_specific_test_plan(self, plan_id: int, suite_ids: List[int]) -> Optional[Dict]:
        """
        Extract a specific test plan with only the specified suites
        
        Args:
            plan_id: ID of the test plan to extract
            suite_ids: List of suite IDs to extract from this plan
            
        Returns:
            Dictionary containing test plan data or None if plan not found
        """
        self.logger.info(f"Extracting test plan ID: {plan_id} with specific suites: {suite_ids}")
        
        try:
            # Get the test plan - remove await as the SDK method is not a coroutine
            plan = self.client.get_test_plan_by_id(
                project=self.config.project_name,
                plan_id=plan_id
            )
            
            if not plan:
                self.logger.warning(f"Test plan ID {plan_id} not found")
                return None
            
            # Extract only the specified suites
            test_suites = []
            for suite_id in suite_ids:
                suite = await self._extract_specific_test_suite(plan_id, suite_id)
                if suite:
                    test_suites.append(suite)
            
            # Create test plan dictionary
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
                "test_suites": test_suites
            }
            
            return test_plan
        except Exception as e:
            self.logger.error(f"Error extracting test plan {plan_id}: {str(e)}")
            return None
            
    async def _extract_specific_test_suite(self, plan_id: int, suite_id: int) -> Optional[Dict]:
        """
        Extract a specific test suite
        
        Args:
            plan_id: ID of the test plan containing the suite
            suite_id: ID of the test suite to extract
            
        Returns:
            Dictionary containing test suite data or None if suite not found
        """
        self.logger.info(f"Extracting test suite ID: {suite_id} from plan ID: {plan_id}")
        
        try:
            # Get the test suite - remove await as the SDK method is not a coroutine
            suite = self.client.get_test_suite_by_id(
                project=self.config.project_name,
                plan_id=plan_id,
                suite_id=suite_id
            )
            
            if not suite:
                self.logger.warning(f"Test suite ID {suite_id} not found in plan {plan_id}")
                return None
                
            # Extract test cases for this suite
            test_cases = await self._extract_test_cases(plan_id, suite_id)
            
            # Create test suite dictionary
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
                "test_cases": test_cases
            }
            
            return test_suite
        except Exception as e:
            self.logger.error(f"Error extracting test suite {suite_id} from plan {plan_id}: {str(e)}")
            return None
    
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
                "steps": await self._extract_test_steps(case.id)
            }
            test_cases.append(test_case)
            
        return test_cases
    
    async def _extract_test_steps(self, test_case_id: int) -> List[Dict]:
        """Extract all test steps for a given test case"""
        self.logger.info(f"Extracting test steps for test case ID: {test_case_id}")
        steps = []
        
        try:
            # Remove await
            test_steps = self.client.test_client.get_test_steps(
                project=self.config.project_name,
                test_case_id=test_case_id
            )
            
            for step in test_steps:
                test_step = {
                    "id": step.id,
                    "action": step.action,
                    "expected_result": step.expected_result,
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
    
    async def extract_test_configurations(self) -> List[Dict]:
        """Extract all test configurations"""
        self.logger.info("Extracting test configurations")
        configurations = []
        
        try:
            # Remove await - SDK method is not a coroutine
            config_list = self.client.test_client.get_test_configurations(
                project=self.config.project_name
            )
            
            for config in config_list:
                configuration = {
                    "id": config.id,
                    "name": config.name,
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
            # Remove await - SDK method is not a coroutine
            var_list = self.client.test_client.get_test_variables(
                project=self.config.project_name
            )
            
            for var in var_list:
                variable = {
                    "id": var.id,
                    "name": var.name,
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