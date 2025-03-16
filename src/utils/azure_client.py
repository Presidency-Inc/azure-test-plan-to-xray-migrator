from azure.devops.connection import Connection
from msrest.authentication import BasicAuthentication
import logging
from typing import List, Dict, Any
import time
import asyncio
import os
import sys

# Add the project root to the Python path
file_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if file_path not in sys.path:
    sys.path.append(file_path)

from src.config.config import AzureConfig

async def retry_async(func, *args, retries=3, delay=2, backoff=2, **kwargs):
    """
    Retry an async function with exponential backoff
    
    Args:
        func: The async function to retry
        args: Positional arguments to pass to the function
        retries: Number of times to retry before giving up
        delay: Initial delay between retries in seconds
        backoff: Backoff multiplier e.g. value of 2 will double the delay each retry
        kwargs: Keyword arguments to pass to the function
        
    Returns:
        The return value of the function
        
    Raises:
        The last exception raised by the function
    """
    last_exception = None
    current_delay = delay
    
    # Try to call the function
    for retry_count in range(retries + 1):  # +1 because we want to try once, then retry 'retries' times
        try:
            if retry_count > 0:
                logger = logging.getLogger(__name__)
                logger.warning(f"Retry attempt {retry_count}/{retries} for {func.__name__} after {current_delay}s delay")
            return await func(*args, **kwargs)
        except Exception as e:
            last_exception = e
            if retry_count < retries:  # No need to sleep after the last retry
                logger = logging.getLogger(__name__)
                logger.warning(f"Exception during {func.__name__}: {str(e)}. Retrying in {current_delay}s...")
                await asyncio.sleep(current_delay)
                current_delay *= backoff  # Exponential backoff
            else:
                # Last retry failed, re-raise the exception
                logger = logging.getLogger(__name__)
                logger.error(f"All {retries} retries failed for {func.__name__}: {str(e)}")
                raise

class AzureDevOpsClient:
    def __init__(self, config: AzureConfig):
        self.config = config
        self._connection = None
        self._test_client = None
        self._test_plan_client = None
        self._work_item_client = None
        self._git_client = None
        self.logger = logging.getLogger(__name__)
        
    @property
    def connection(self):
        if not self._connection:
            # Log configuration details for debugging (mask the PAT)
            masked_pat = self.config.personal_access_token[:4] + "..." if self.config.personal_access_token else "None"
            self.logger.info(f"Connecting to Azure DevOps with:")
            self.logger.info(f"  Organization URL: {self.config.organization_url}")
            self.logger.info(f"  Project Name: {self.config.project_name}")
            self.logger.info(f"  PAT (masked): {masked_pat}")
            
            # Ensure organization URL is correctly formatted
            org_url = self.config.organization_url.rstrip('/')
            
            # Create credentials
            credentials = BasicAuthentication('', self.config.personal_access_token)
            
            try:
                self._connection = Connection(
                    base_url=org_url,
                    creds=credentials
                )
                self.logger.info("Connected to Azure DevOps successfully")
            except Exception as e:
                self.logger.error(f"Failed to connect to Azure DevOps: {str(e)}")
                raise
        return self._connection
    
    @property
    def test_client(self):
        if not self._test_client:
            self.logger.info("Initializing Azure DevOps Test Client")
            # Print available client methods for debugging
            self.logger.info("Available clients:")
            for client_method in dir(self.connection.clients):
                if not client_method.startswith('_'):
                    self.logger.info(f"  - {client_method}")
                    
            # First try to use the test_plan_client (newer API)
            try:
                self.logger.info("Attempting to use test_plan_client (modern API)")
                self._test_plan_client = self.connection.clients.get_test_plan_client()
                self.logger.info("Successfully initialized test_plan_client")
                # If we get here, use test_plan_client as a fallback for test_client
                self._test_client = self.connection.clients.get_test_client()
                self.logger.info("Also initialized test_client for legacy API operations")
                return self._test_client
            except Exception as tpc_error:
                self.logger.warning(f"Failed to initialize Test Plan Client: {str(tpc_error)}")
                # Fall back to test_client
                pass
                    
            # Try the legacy test_client
            try:
                self.logger.info("Attempting to use test_client (legacy API)")
                self._test_client = self.connection.clients.get_test_client()
                self.logger.info("Azure DevOps Test Client initialized successfully")
            except Exception as e:
                self.logger.error(f"Failed to initialize Test Client: {str(e)}")
                raise
        return self._test_client
    
    @property
    def test_plan_client(self):
        """Get the test plan client (newer API)"""
        if not self._test_plan_client:
            self.logger.info("Initializing Azure DevOps Test Plan Client")
            try:
                self._test_plan_client = self.connection.clients.get_test_plan_client()
                self.logger.info("Azure DevOps Test Plan Client initialized successfully")
            except Exception as e:
                self.logger.error(f"Failed to initialize Test Plan Client: {str(e)}")
                raise
        return self._test_plan_client
    
    @property
    def work_item_client(self):
        if not self._work_item_client:
            self.logger.info("Initializing Azure DevOps Work Item Client")
            self._work_item_client = self.connection.clients.get_work_item_tracking_client()
        return self._work_item_client
    
    @property
    def git_client(self):
        if not self._git_client:
            self.logger.info("Initializing Azure DevOps Git Client")
            self._git_client = self.connection.clients.get_git_client()
        return self._git_client
    
    def get_work_item(self, work_item_id):
        """Get a work item by ID"""
        try:
            self.logger.info(f"Retrieving work item: {work_item_id}")
            return self.work_item_client.get_work_item(work_item_id, self.config.project_name)
        except Exception as e:
            self.logger.error(f"Error retrieving work item {work_item_id}: {str(e)}")
            return None
    
    def get_test_plan_by_id(self, project, plan_id):
        """Get a test plan by ID"""
        try:
            # Log retrieval attempt
            self.logger.info(f"Retrieving test plan: {plan_id} from project: {project}")
            
            # Try using test_plan_client first (newer API)
            if self._test_plan_client:
                try:
                    self.logger.info("Using test_plan_client API")
                    return self._test_plan_client.get_test_plan_by_id(project, plan_id)
                except Exception as e:
                    self.logger.warning(f"Test plan client failed, falling back to test client: {str(e)}")
            
            # Fall back to test_client
            return self.test_client.get_test_plan_by_id(project, plan_id)
        except Exception as e:
            self.logger.error(f"Error retrieving test plan {plan_id}: {str(e)}")
            return None
    
    def get_test_suite_by_id(self, project, plan_id, suite_id):
        """Get a test suite by ID"""
        try:
            # Log retrieval attempt
            self.logger.info(f"Retrieving test suite: {suite_id} from plan {plan_id} in project: {project}")
            
            # Try using test_plan_client first (newer API)
            if self._test_plan_client:
                try:
                    self.logger.info("Using test_plan_client API")
                    return self._test_plan_client.get_test_suite_by_id(project, plan_id, suite_id)
                except Exception as e:
                    self.logger.warning(f"Test plan client failed, falling back to test client: {str(e)}")
            
            # Fall back to test_client
            return self.test_client.get_test_suite_by_id(project, plan_id, suite_id)
        except Exception as e:
            self.logger.error(f"Error retrieving test suite {suite_id} from plan {plan_id}: {str(e)}")
            return None
    
    def get_test_suites(self, project: str, plan_id: int) -> List:
        """
        Get all test suites for a test plan
        """
        self.logger.info(f"Getting test suites for plan {plan_id} in project {project}")
        suites = []
        
        try:
            # Use the modern client if available
            if hasattr(self, 'test_plan_client'):
                self.logger.info(f"Using modern TestPlanClient to get test suites")
                test_plan_suites = self.test_plan_client.get_test_suites_for_plan(project=project, plan_id=plan_id)
                suites = test_plan_suites
            else:
                # Fall back to legacy client
                self.logger.info(f"Using legacy TestClient to get test suites")
                client_response = self.test_client.get_test_suites(project=project, plan_id=plan_id)
                suites = client_response
                
            self.logger.info(f"Retrieved {len(suites) if suites else 0} test suites")
            return suites
        except Exception as e:
            self.logger.error(f"Error getting test suites for plan {plan_id}: {str(e)}")
            return []
    
    def get_test_suite_hierarchy(self, project: str, plan_id: int) -> Dict[int, Any]:
        """
        Get the complete test suite hierarchy for a test plan
        
        Returns:
            Dictionary of suite_id -> suite_object
        """
        self.logger.info(f"Getting test suite hierarchy for plan {plan_id} in project {project}")
        suite_dict = {}
        
        try:
            # Get all suites first
            suites = self.get_test_suites(project=project, plan_id=plan_id)
            if not suites:
                self.logger.warning(f"No suites found for plan {plan_id}")
                return {}
            
            # Convert list to dictionary by suite ID
            for suite in suites:
                suite_id = suite.id if hasattr(suite, 'id') else None
                if suite_id:
                    suite_dict[suite_id] = suite
            
            self.logger.info(f"Created suite hierarchy dictionary with {len(suite_dict)} suites")
            return suite_dict
        except Exception as e:
            self.logger.error(f"Error getting test suite hierarchy for plan {plan_id}: {str(e)}")
            return {}
    
    def get_test_cases(self, project: str, plan_id: int, suite_id: int) -> List:
        """
        Get test cases for a test suite
        """
        self.logger.info(f"Getting test cases for plan {plan_id}, suite {suite_id} in project {project}")
        
        try:
            # Try using the modern client first
            if hasattr(self, 'test_plan_client'):
                self.logger.info(f"Using modern TestPlanClient to get test cases")
                try:
                    test_cases = self.test_plan_client.get_test_case_list(
                        project=project,
                        plan_id=plan_id,
                        suite_id=suite_id
                    )
                    if test_cases:
                        self.logger.info(f"Retrieved {len(test_cases)} test cases using TestPlanClient.get_test_case_list")
                        return test_cases
                    else:
                        self.logger.warning("No test cases found using TestPlanClient.get_test_case_list, trying alternative methods")
                except Exception as e:
                    self.logger.warning(f"Error using TestPlanClient.get_test_case_list: {str(e)}. Trying alternative methods.")
            
            # Try using the suite API if get_test_case_list failed
            try:
                test_cases = self.test_plan_client.get_suite_test_cases(
                    project=project,
                    plan_id=plan_id,
                    suite_id=suite_id
                )
                if test_cases:
                    self.logger.info(f"Retrieved {len(test_cases)} test cases using TestPlanClient.get_suite_test_cases")
                    return test_cases
                else:
                    self.logger.warning("No test cases found using TestPlanClient.get_suite_test_cases, trying work item client")
            except Exception as e:
                self.logger.warning(f"Error using TestPlanClient.get_suite_test_cases: {str(e)}. Trying work item client.")
                
            # Try getting test cases via work items as a last resort
            return self.get_test_cases_via_work_items(project=project, plan_id=plan_id, suite_id=suite_id)
            
            # Fall back to legacy client
            self.logger.info(f"Using legacy TestClient to get test cases")
            test_cases = self.test_client.get_test_cases(
                project=project,
                plan_id=plan_id,
                suite_id=suite_id
            )
            self.logger.info(f"Retrieved {len(test_cases) if test_cases else 0} test cases using legacy client")
            return test_cases
        except Exception as e:
            self.logger.error(f"Error getting test cases for suite {suite_id} in plan {plan_id}: {str(e)}")
            return []
    
    def get_test_cases_via_work_items(self, project: str, plan_id: int, suite_id: int) -> List:
        """
        Get test cases by querying work items
        This is a fallback method when the regular test case API methods fail
        """
        self.logger.info(f"Attempting to get test cases via work items for plan {plan_id}, suite {suite_id}")
        
        try:
            # Get the suite to find the test case IDs
            suite = self.get_test_suite_by_id(project=project, plan_id=plan_id, suite_id=suite_id)
            if not suite or not hasattr(suite, 'test_case_ids') or not suite.test_case_ids:
                self.logger.warning(f"Suite {suite_id} has no test_case_ids attribute or it's empty")
                
                # Try to get test case IDs through other means if available
                if hasattr(self, 'work_item_tracking_client'):
                    # Query for test cases in this suite using WIQL
                    wiql = {
                        "query": f"""
                        SELECT [System.Id], [System.Title], [System.Description], [System.WorkItemType]
                        FROM WorkItems
                        WHERE [System.WorkItemType] = 'Test Case'
                        AND [Microsoft.VSTS.TCM.TestSuiteId] = {suite_id}
                        ORDER BY [System.Id]
                        """
                    }
                    
                    self.logger.info(f"Executing WIQL query to find test cases for suite {suite_id}")
                    wiql_result = self.work_item_tracking_client.query_by_wiql(wiql, project=project)
                    
                    if not wiql_result or not hasattr(wiql_result, 'work_items') or not wiql_result.work_items:
                        self.logger.warning(f"No test cases found via WIQL query for suite {suite_id}")
                        return []
                        
                    # Get work item IDs from the query result
                    work_item_ids = [item.id for item in wiql_result.work_items]
                    self.logger.info(f"Found {len(work_item_ids)} test case work item IDs: {work_item_ids}")
                    
                    # Get the full work items
                    if work_item_ids:
                        work_items = self.work_item_tracking_client.get_work_items(work_item_ids)
                        
                        # Convert work items to test case format
                        test_cases = []
                        for wi in work_items:
                            # Create a mock test case object from the work item
                            test_case = type('TestCase', (), {
                                'id': wi.id,
                                'name': wi.fields.get('System.Title', f'Test Case {wi.id}'),
                                'description': wi.fields.get('System.Description', ''),
                                'priority': wi.fields.get('Microsoft.VSTS.Common.Priority', 2),
                                'work_item': type('WorkItem', (), {
                                    'id': wi.id,
                                    'url': wi.url if hasattr(wi, 'url') else None
                                })
                            })
                            test_cases.append(test_case)
                            
                        self.logger.info(f"Created {len(test_cases)} test cases from work items")
                        return test_cases
            else:
                # We have test case IDs, get the work items
                test_case_ids = suite.test_case_ids
                self.logger.info(f"Found {len(test_case_ids)} test case IDs in suite {suite_id}: {test_case_ids}")
                
                # Get the work items for these test cases
                if test_case_ids and hasattr(self, 'work_item_tracking_client'):
                    work_items = self.work_item_tracking_client.get_work_items(test_case_ids)
                    
                    # Convert work items to test case format
                    test_cases = []
                    for wi in work_items:
                        # Create a mock test case object from the work item
                        test_case = type('TestCase', (), {
                            'id': wi.id,
                            'name': wi.fields.get('System.Title', f'Test Case {wi.id}'),
                            'description': wi.fields.get('System.Description', ''),
                            'priority': wi.fields.get('Microsoft.VSTS.Common.Priority', 2),
                            'work_item': type('WorkItem', (), {
                                'id': wi.id,
                                'url': wi.url if hasattr(wi, 'url') else None
                            })
                        })
                        test_cases.append(test_case)
                        
                    self.logger.info(f"Created {len(test_cases)} test cases from work items")
                    return test_cases
                
            # If we reached here, we couldn't get test cases
            self.logger.warning(f"Could not retrieve test cases via work items for suite {suite_id}")
            return []
        except Exception as e:
            self.logger.error(f"Error getting test cases via work items for suite {suite_id}: {str(e)}")
            return []
    
    def get_test_configurations(self, project):
        """Get test configurations for a project"""
        try:
            self.logger.info(f"Retrieving test configurations for project: {project}")
            # Use the test_client directly
            try:
                return self.test_client.get_test_configurations(project)
            except AttributeError:
                # If the method doesn't exist, return an empty list
                self.logger.warning("get_test_configurations method not available in Azure DevOps SDK")
                return []
        except Exception as e:
            self.logger.error(f"Error retrieving test configurations: {str(e)}")
            return []
    
    def get_test_variables(self, project):
        """Get test variables for a project"""
        try:
            self.logger.info(f"Retrieving test variables for project: {project}")
            # Use the test_client directly
            try:
                return self.test_client.get_test_variables(project)
            except AttributeError:
                # If the method doesn't exist, return an empty list
                self.logger.warning("get_test_variables method not available in Azure DevOps SDK")
                return []
        except Exception as e:
            self.logger.error(f"Error retrieving test variables: {str(e)}")
            return []
    
    def get_test_plans(self, project: str) -> List:
        """
        Get all test plans for a project using the modern Test Plan API
        See: https://learn.microsoft.com/en-us/rest/api/azure/devops/test/test-plans/list
        """
        self.logger.info(f"Getting all test plans for project {project}")
        
        try:
            if not hasattr(self, 'test_plan_client') or not self.test_plan_client:
                self.logger.error("Test plan client not initialized")
                return []
                
            # Modern API method to get all test plans - NOT async
            test_plans = self.test_plan_client.get_test_plans(project=project)
            self.logger.info(f"Retrieved {len(test_plans) if test_plans else 0} test plans")
            return test_plans
        except Exception as e:
            self.logger.error(f"Error getting test plans: {str(e)}")
            return []
            
    def get_test_suites_for_plan(self, project: str, plan_id: int) -> List:
        """
        Get all test suites for a plan using the modern Test Suite API
        See: https://learn.microsoft.com/en-us/rest/api/azure/devops/test/test-suites/list
        """
        self.logger.info(f"Getting all test suites for plan {plan_id} in project {project}")
        
        try:
            if not hasattr(self, 'test_plan_client') or not self.test_plan_client:
                self.logger.error("Test plan client not initialized")
                return []
                
            # Get test suites - NOT async
            test_suites = self.test_plan_client.get_test_suites_for_plan(
                project=project,
                plan_id=plan_id
            )
            self.logger.info(f"Retrieved {len(test_suites) if test_suites else 0} test suites for plan {plan_id}")
            return test_suites
        except Exception as e:
            self.logger.error(f"Error getting test suites for plan {plan_id}: {str(e)}")
            return []

    def get_test_cases_for_suite(self, project: str, plan_id: int, suite_id: int) -> List:
        """
        Get all test cases for a test suite using the modern API
        """
        self.logger.info(f"Getting test cases for suite {suite_id} in plan {plan_id}")
        
        try:
            if not hasattr(self, 'test_plan_client') or not self.test_plan_client:
                self.logger.error("Test plan client not initialized")
                return []
                
            # Get test cases - NOT async, using modern API
            test_cases = self.test_plan_client.get_test_case_list(
                project=project,
                plan_id=plan_id,
                suite_id=suite_id
            )
            self.logger.info(f"Retrieved {len(test_cases) if test_cases else 0} test cases for suite {suite_id}")
            return test_cases
        except Exception as e:
            self.logger.error(f"Error getting test cases for suite {suite_id}: {str(e)}")
            return []

    def get_suite_hierarchy(self, project: str, plan_id: int) -> Dict[int, Any]:
        """
        Build a complete hierarchy of all suites in a plan using modern API only
        """
        self.logger.info(f"Building suite hierarchy for plan {plan_id} in project {project}")
        
        suite_hierarchy = {}
        try:
            # Get all suites in the plan
            suites = self.get_test_suites_for_plan(project=project, plan_id=plan_id)
            
            if not suites:
                self.logger.warning(f"No suites found for plan {plan_id}")
                return {}
                
            # Build the hierarchy dictionary
            for suite in suites:
                suite_id = suite.id if hasattr(suite, 'id') else None
                if suite_id:
                    suite_hierarchy[suite_id] = suite
                    
            self.logger.info(f"Built suite hierarchy with {len(suite_hierarchy)} suites")
            return suite_hierarchy
        except Exception as e:
            self.logger.error(f"Error building suite hierarchy: {str(e)}")
            return {}

    # Modern API methods (using REST API directly)
    async def get_all_test_plans_modern(self, project_name=None) -> List[Dict]:
        """
        Get all test plans in a project using the modern REST API
        
        Args:
            project_name: The name of the project (defaults to the one in config)
            
        Returns:
            List of test plans
        """
        async def _get_test_plans():
            project = project_name or self.config.project_name
            self.logger.info(f"API CALL: Getting all test plans for project '{project}' using modern API")
            
            # Create the REST URL for test plans
            org_url = self.config.organization_url.rstrip('/')
            api_url = f"{org_url}/{project}/_apis/testplan/plans?api-version=7.0"
            self.logger.info(f"API URL: {api_url}")
            
            # Use the requests session from the connection object
            self.logger.info(f"Sending GET request to {api_url}")
            response = self.connection.client.session.get(api_url)
            self.logger.info(f"API Response Status: {response.status_code}")
            response.raise_for_status()
            
            # Extract and parse the response
            data = response.json()
            plans = data.get('value', [])
            
            self.logger.info(f"API RESULT: Successfully retrieved {len(plans)} test plans from project '{project}'")
            
            # Log the first plan as a sample (masked for privacy)
            if plans and len(plans) > 0:
                sample_plan = plans[0].copy()
                self.logger.info(f"API SAMPLE RESULT: First plan ID: {sample_plan.get('id')}, Name: {sample_plan.get('name')}")
            
            return plans
        
        try:
            # Use retry logic
            return await retry_async(_get_test_plans, retries=3, delay=2)
        except Exception as e:
            self.logger.error(f"API ERROR: Failed to get test plans using modern API: {str(e)}", exc_info=True)
            return []
    
    async def get_all_test_suites_modern(self, project_name=None, plan_id=None) -> List[Dict]:
        """
        Get all test suites for a test plan using the modern REST API
        
        Args:
            project_name: The name of the project (defaults to the one in config)
            plan_id: The ID of the test plan
            
        Returns:
            List of test suites
        """
        async def _get_test_suites():
            project = project_name or self.config.project_name
            self.logger.info(f"API CALL: Getting all test suites for plan {plan_id} in project '{project}' using modern API")
            
            if not plan_id:
                self.logger.error("API ERROR: Plan ID is required")
                return []
            
            # Create the REST URL for test suites
            org_url = self.config.organization_url.rstrip('/')
            api_url = f"{org_url}/{project}/_apis/testplan/Plans/{plan_id}/suites?api-version=7.0"
            self.logger.info(f"API URL: {api_url}")
            
            # Use the requests session from the connection object
            self.logger.info(f"Sending GET request to {api_url}")
            response = self.connection.client.session.get(api_url)
            self.logger.info(f"API Response Status: {response.status_code}")
            response.raise_for_status()
            
            # Extract and parse the response
            data = response.json()
            suites = data.get('value', [])
            
            self.logger.info(f"API RESULT: Successfully retrieved {len(suites)} test suites from plan {plan_id}")
            
            # Log the first suite as a sample (masked for privacy)
            if suites and len(suites) > 0:
                sample_suite = suites[0].copy()
                self.logger.info(f"API SAMPLE RESULT: First suite ID: {sample_suite.get('id')}, Name: {sample_suite.get('name')}")
                
                # Log parent-child relationships for debugging
                parent_ids = set()
                for suite in suites:
                    parent_id = suite.get('parentSuiteId')
                    if parent_id:
                        parent_ids.add(parent_id)
                self.logger.info(f"API RESULT: Found {len(parent_ids)} unique parent suite IDs")
            
            return suites
        
        try:
            # Use retry logic
            return await retry_async(_get_test_suites, retries=3, delay=2)
        except Exception as e:
            self.logger.error(f"API ERROR: Failed to get test suites using modern API: {str(e)}", exc_info=True)
            return []
    
    async def get_test_cases_for_suite_modern(self, project_name=None, plan_id=None, suite_id=None) -> List[Dict]:
        """
        Get all test cases for a test suite using the modern REST API
        
        Args:
            project_name: The name of the project (defaults to the one in config)
            plan_id: The ID of the test plan
            suite_id: The ID of the test suite
            
        Returns:
            List of test cases
        """
        async def _get_test_cases():
            project = project_name or self.config.project_name
            self.logger.info(f"API CALL: Getting test cases for suite {suite_id} in plan {plan_id} using modern API")
            
            if not plan_id or not suite_id:
                self.logger.error("API ERROR: Plan ID and Suite ID are required")
                return []
            
            # Create the REST URL for test cases
            org_url = self.config.organization_url.rstrip('/')
            api_url = f"{org_url}/{project}/_apis/testplan/Plans/{plan_id}/Suites/{suite_id}/TestCase?api-version=7.0"
            self.logger.info(f"API URL: {api_url}")
            
            # Use the requests session from the connection object
            self.logger.info(f"Sending GET request to {api_url}")
            response = self.connection.client.session.get(api_url)
            self.logger.info(f"API Response Status: {response.status_code}")
            response.raise_for_status()
            
            # Extract and parse the response
            data = response.json()
            test_cases = data.get('value', [])
            
            self.logger.info(f"API RESULT: Successfully retrieved {len(test_cases)} test cases from suite {suite_id}")
            
            # For each test case, get the work item details if needed
            enriched_test_cases = []
            for tc in test_cases:
                test_case = {
                    "id": tc.get("id"),
                    "workItemId": tc.get("workItem", {}).get("id"),
                    "testCaseTitle": tc.get("workItem", {}).get("name"),
                    "pointAssignments": tc.get("pointAssignments", []),
                    "rev": tc.get("rev"),
                    "planId": plan_id,
                    "suiteId": suite_id
                }
                enriched_test_cases.append(test_case)
            
            # Log the first test case as a sample (masked for privacy)
            if enriched_test_cases and len(enriched_test_cases) > 0:
                sample_tc = enriched_test_cases[0].copy()
                self.logger.info(f"API SAMPLE RESULT: Test case ID: {sample_tc.get('id')}, Work Item ID: {sample_tc.get('workItemId')}, Title: {sample_tc.get('testCaseTitle')}")
            
            return enriched_test_cases
        
        try:
            # Use retry logic
            return await retry_async(_get_test_cases, retries=3, delay=2)
        except Exception as e:
            self.logger.error(f"API ERROR: Failed to get test cases using modern API: {str(e)}", exc_info=True)
            return [] 