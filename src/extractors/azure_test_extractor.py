from typing import List, Dict, Any, Optional
import asyncio
import os
import json
import logging
from datetime import datetime
from utils.azure_client import AzureDevOpsClient
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
            "test_results": test_results
        }
        
        # Save the extraction data
        self._save_extraction_data(extraction_result, extraction_dir)
        
        self.logger.info(f"Extraction completed successfully. Data saved in: {extraction_dir}")
        return extraction_result
        
    async def extract_test_plans(self) -> List[Dict]:
        """Extract all test plans with their hierarchical data"""
        self.logger.info("Extracting test plans")
        test_plans = []
        
        # Get all test plans
        plans = await self.client.test_client.get_test_plans(
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
        
        plan_suites = await self.client.test_client.get_test_suites(
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
        
        suite_test_cases = await self.client.test_client.get_test_cases(
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
            test_steps = await self.client.test_client.get_test_steps(
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
            config_list = await self.client.test_client.get_test_configurations(
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
            var_list = await self.client.test_client.get_test_variables(
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
            # Get all suites for this plan
            suites = await self.client.test_client.get_test_suites(
                project=self.config.project_name,
                plan_id=plan_id
            )
            
            # For each suite, get the test points
            for suite in suites:
                suite_points = await self.client.test_client.get_points(
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
            test_results = await self.client.test_client.get_test_results(
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
            filename = f"{entity_type}.json"
            file_path = os.path.join(output_dir, filename)
            
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(entities, f, indent=2, default=str)
            
            self.logger.info(f"Saved {len(entities)} {entity_type} to {file_path}")
        
        # Also save a summary file
        summary = {
            "extraction_date": datetime.now().isoformat(),
            "project": self.config.project_name,
            "organization": self.config.organization_url,
            "counts": {
                entity_type: len(entities) for entity_type, entities in data.items()
            }
        }
        
        summary_path = os.path.join(output_dir, "extraction_summary.json")
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)
        
        self.logger.info(f"Saved extraction summary to {summary_path}") 