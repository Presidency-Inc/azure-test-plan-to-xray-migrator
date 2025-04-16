from azure.devops.connection import Connection
from msrest.authentication import BasicAuthentication
import logging
from typing import List, Dict, Any
import time
import asyncio
import os
import sys
import requests
import base64
from src.utils.attachment_extractor import get_attached_files, download_azure_attachment
from src.utils.json_utils import load_json, save_json_data


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
                
                # Extract and log response body for HTTP errors
                if hasattr(e, 'response') and hasattr(e.response, 'text'):
                    logger.warning(f"Exception during {func.__name__}: {str(e)}\nResponse Body: {e.response.text}. Retrying in {current_delay}s...")
                else:
                    logger.warning(f"Exception during {func.__name__}: {str(e)}. Retrying in {current_delay}s...")
                
                await asyncio.sleep(current_delay)
                current_delay *= backoff  # Exponential backoff
            else:
                # Last retry failed, re-raise the exception
                logger = logging.getLogger(__name__)
                
                # Extract and log response body for HTTP errors on final attempt
                if hasattr(e, 'response') and hasattr(e.response, 'text'):
                    logger.error(f"All {retries} retries failed for {func.__name__}: {str(e)}\nResponse Body: {e.response.text}")
                else:
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
        self.attachment_custom_path = "attachments/extraction"
        self.attachment_path_file = "work_item_attachments.json"
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
            self.logger.info(f"API CALL: Getting test plan 218 for project '{project}' using modern API")
            
            # Create the REST URL for test plans
            org_url = self.config.organization_url.rstrip('/')
            
            # MODIFIED: Get plan 218 directly
            api_url = f"{org_url}/{project}/_apis/testplan/plans/218?api-version=7.0"
            self.logger.info(f"API URL: {api_url}")
            
            # Create auth header with PAT
            auth_header = {
                'Authorization': f'Basic {self._get_basic_auth_string()}'
            }
            
            # Use the requests library directly
            self.logger.info(f"Sending GET request to {api_url}")
            response = requests.get(api_url, headers=auth_header)
            self.logger.info(f"API Response Status: {response.status_code}")
            
            # Log the full response content if there's an error
            if response.status_code >= 400:
                self.logger.error(f"API Error Response: {response.text}")
                self.logger.error(f"API Request URL: {api_url}")
                self.logger.error(f"API Request Headers: {auth_header}")
                
                # If direct access fails, try the original approach to get all plans and filter
                self.logger.info(f"Direct access to plan 218 failed, trying to get all plans and filter")
                all_plans_url = f"{org_url}/{project}/_apis/testplan/plans?api-version=7.0"
                all_plans_response = requests.get(all_plans_url, headers=auth_header)
                
                if all_plans_response.status_code >= 400:
                    self.logger.error(f"API Error Response: {all_plans_response.text}")
                    all_plans_response.raise_for_status()
                    
                all_plans_data = all_plans_response.json()
                all_plans = all_plans_data.get('value', [])
                plans = [plan for plan in all_plans if str(plan.get('id')) == '218']
                
                if plans:
                    self.logger.info(f"Found plan 218 in the list of all plans")
                    return plans
                else:
                    self.logger.error(f"Plan 218 not found in any API response")
                    response.raise_for_status()  # Raise the original error
            else:
                # Direct access succeeded
                plan_data = response.json()
                self.logger.info(f"API RESULT: Successfully retrieved plan ID 218")
                return [plan_data]
            
            # This line should not be reached if everything works correctly
            return []
        
        try:
            # Use retry logic
            return await retry_async(_get_test_plans, retries=3, delay=2)
        except Exception as e:
            self.logger.error(f"API ERROR: Failed to get test plans using modern API: {str(e)}", exc_info=True)
            return []
    
    def _get_basic_auth_string(self):
        """
        Create a base64 encoded authorization string using the PAT
        
        Returns:
            Base64 encoded authorization string
        """
        # The format for basic auth is ":{pat}" (note the colon with empty username)
        auth_string = f":{self.config.personal_access_token}"
        encoded_auth = base64.b64encode(auth_string.encode('utf-8')).decode('utf-8')
        return encoded_auth
    
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
            self.logger.info(f"API CALL: Getting test suites for plan {plan_id} in project '{project}' using modern API")
            
            if not plan_id:
                self.logger.error("API ERROR: Plan ID is required")
                return []
            
            # Skip if not plan 218
            if str(plan_id) != '218':
                self.logger.info(f"Plan ID {plan_id} is not 218, returning empty list")
                return []
                
            # Create the REST URL for test suites
            org_url = self.config.organization_url.rstrip('/')
            
            # MODIFIED: Get only the specific suites we want
            target_suite_ids = ['9035', '9036']
            suites = []
            
            # Get each suite directly
            for suite_id in target_suite_ids:
                api_url = f"{org_url}/{project}/_apis/testplan/Plans/{plan_id}/suites/{suite_id}?api-version=7.0"
                self.logger.info(f"API URL for suite {suite_id}: {api_url}")
                
                # Create auth header with PAT
                auth_header = {
                    'Authorization': f'Basic {self._get_basic_auth_string()}'
                }
                
                # Use the requests library directly
                self.logger.info(f"Sending GET request to {api_url}")
                response = requests.get(api_url, headers=auth_header)
                self.logger.info(f"API Response Status for suite {suite_id}: {response.status_code}")
                
                # Process response
                if response.status_code == 200:
                    suite_data = response.json()
                    suites.append(suite_data)
                    self.logger.info(f"Successfully retrieved suite {suite_id}")
                else:
                    self.logger.error(f"Error retrieving suite {suite_id}: {response.text}")
            
            self.logger.info(f"API RESULT: Retrieved {len(suites)} suites for plan {plan_id}")
            
            # Log the suites for debugging
            if suites:
                for suite in suites:
                    self.logger.info(f"Suite ID: {suite.get('id')}, Name: {suite.get('name')}")
            
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
            
            # Create auth header with PAT
            auth_header = {
                'Authorization': f'Basic {self._get_basic_auth_string()}'
            }
            
            # Use the requests library directly
            self.logger.info(f"Sending GET request to {api_url}")
            response = requests.get(api_url, headers=auth_header)
            self.logger.info(f"API Response Status: {response.status_code}")
            
            # Log the full response content if there's an error
            if response.status_code >= 400:
                self.logger.error(f"API Error Response: {response.text}")
                self.logger.error(f"API Request URL: {api_url}")
                self.logger.error(f"API Request Headers: {auth_header}")
            
            response.raise_for_status()
            
            # Extract and parse the response
            data = response.json()
            test_cases = data.get('value', [])
            
            self.logger.info(f"API RESULT: Successfully retrieved {len(test_cases)} test cases from suite {suite_id}")
            
            # For each test case, get the work item details if needed
            enriched_test_cases = []
            for tc in test_cases:
                # Get the point assignment ID for the first point assignment if available
                point_assignments = tc.get("pointAssignments", [])
                test_point_id = point_assignments[0].get("id") if point_assignments and len(point_assignments) > 0 else None
                
                test_case = {
                    "id": test_point_id,  # Use test point ID as the test case ID
                    "workItemId": tc.get("workItem", {}).get("id"),
                    "testCaseTitle": tc.get("workItem", {}).get("name"),
                    "pointAssignments": point_assignments,
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
            
    # Work Item API methods
    async def get_work_items_batch(self, work_item_ids: List[int], fields: List[str] = None, project_name=None) -> List[Dict]:
        """
        Get work items in a batch (up to 200 items) using the modern REST API
        
        Args:
            work_item_ids: List of work item IDs to retrieve
            fields: List of specific fields to include (optional)
            project_name: The name of the project (defaults to the one in config)
            
        Returns:
            List of work items
        """
        if not work_item_ids:
            self.logger.warning("No work item IDs provided for batch retrieval")
            return []
            
        # Azure DevOps API can handle up to 200 IDs at once
        if len(work_item_ids) > 200:
            self.logger.warning(f"Too many work item IDs provided ({len(work_item_ids)}). Limiting to first 200.")
            work_item_ids = work_item_ids[:200]
            
        async def _get_work_items_batch():
            project = project_name or self.config.project_name
            id_list_str = ','.join(map(str, work_item_ids))
            
            self.logger.info(f"API CALL: Getting {len(work_item_ids)} work items from project '{project}' using modern API")
            
            # Create the REST URL for work items
            org_url = self.config.organization_url.rstrip('/')
            # Base URL for work items batch API
            api_url = f"{org_url}/{project}/_apis/wit/workitems"
            
            # Create query parameters
            params = {
                '$expand': 'all',
                'ids': id_list_str,
                'api-version': '7.0'
            }
              
            # Create auth header with PAT
            auth_header = {
                'Authorization': f'Basic {self._get_basic_auth_string()}'
            }
            
            # Use the requests library with params instead of building URL manually
            self.logger.info(f"Sending GET request to Azure DevOps API")
            response = requests.get(api_url, params=params, headers=auth_header)
            self.logger.info(f"API Response Status: {response.status_code}")
            
            # Log the full response content if there's an error
            if response.status_code >= 400:
                self.logger.error(f"API Error Response: {response.text}")
                self.logger.error(f"API Request URL: {api_url}")
                self.logger.error(f"API Request Headers: {auth_header}")
            
            response.raise_for_status()
            
            # Extract and parse the response
            data = response.json()
            work_items = data.get('value', [])
            
            self.logger.info(f"API RESULT: Successfully retrieved {len(work_items)} work items")
            
            # Load existing attachment data - JSON file
            attachment_data = load_json(f"{self.attachment_custom_path}/{self.attachment_path_file}")
            
            # Log a sample work item for debugging
            if work_items and len(work_items) > 0:
                # Extract attachments
                for workItem in work_items:
                    workitem_id = workItem.get("id", "")

                    self.logger.info(f"[EXTRACTION] - Work item {workitem_id} details: {workItem}")

                    attached_files = get_attached_files(workItem)

                    if(attached_files):
                        for attached_file in attached_files:
                            attributes = attached_file.get("attributes", {})
                            name = attributes.get("name", "")
                            file_id = attributes.get("id", "")
                            file_name = f"{workitem_id}_{name}"

                            attachment_item_reference = f"{workitem_id}_{file_id}"

                            # Check if workitem_id exists
                            if attachment_item_reference not in attachment_data:
                                new_attachment_item = {
                                    "project": project,
                                    "work_item_id": workitem_id,
                                    "file_name": file_name,
                                    "og_name": name,
                                    "file_id": file_id
                                }

                                # Add new item to attachment_data
                                attachment_data[attachment_item_reference] = new_attachment_item

                            success, message = download_azure_attachment(
                                attached_file["url"], 
                                self.config.personal_access_token, 
                                output_filename=file_name,
                                output_directory="./attachments"
                            )

                            if(success):
                                self.logger.info(f"[EXTRACTION] - {file_name}: {message}")
                            else:
                                raise Exception(message)
                                
                        print(len(attached_files))

                save_json_data(attachment_data, self.attachment_path_file, base_path=self.attachment_custom_path)
            return work_items
        
        try:
            # Use retry logic
            return await retry_async(_get_work_items_batch, retries=3, delay=2)
        except Exception as e:
            self.logger.error(f"API ERROR: Failed to get work items batch using modern API: {str(e)}", exc_info=True)
            return []
            
    async def get_work_item(self, work_item_id: int, fields: List[str] = None, project_name=None) -> Dict:
        """
        Get a single work item using the modern REST API
        
        Args:
            work_item_id: The ID of the work item to retrieve
            fields: List of specific fields to include (optional)
            project_name: The name of the project (defaults to the one in config)
            
        Returns:
            Work item details as a dictionary
        """
        async def _get_work_item():
            project = project_name or self.config.project_name
            
            self.logger.info(f"API CALL: Getting work item {work_item_id} from project '{project}' using modern API")
            
            # Create the REST URL for the work item
            org_url = self.config.organization_url.rstrip('/')
            # Construct base API URL
            api_url = f"{org_url}/{project}/_apis/wit/workitems/{work_item_id}"

            # Create query parameters
            params = {
                '$expand': 'all',
                'api-version': '7.0'
            }

            # Add fields parameter if provided
            if fields:
                params['fields'] = ','.join(fields)

            # Log the full URL being constructed
            import urllib.parse
            full_url = f"{api_url}?{urllib.parse.urlencode(params)}"
            self.logger.info(f"API URL being constructed: {full_url}")
            
            # Create auth header with PAT
            auth_header = {
                'Authorization': f'Basic {self._get_basic_auth_string()}'
            }
            
            # Use the requests library with params instead of building URL manually
            self.logger.info(f"Sending GET request to Azure DevOps API")
            response = requests.get(api_url, params=params, headers=auth_header)
            self.logger.info(f"API Response Status: {response.status_code}")
            
            # Log the full response content if there's an error
            if response.status_code >= 400:
                self.logger.error(f"API Error Response: {response.text}")
                self.logger.error(f"API Request URL: {api_url}")
                self.logger.error(f"API Request Headers: {auth_header}")
            
            response.raise_for_status()
            
            # Extract and parse the response
            work_item = response.json()
            
            self.logger.info(f"API RESULT: Successfully retrieved work item {work_item_id}")
            
            # Log basic info about the work item
            if 'fields' in work_item:
                field_keys = list(work_item['fields'].keys())
                self.logger.info(f"API RESULT: Work item fields retrieved: {len(field_keys)}")
            
            return work_item
        
        try:
            # Use retry logic
            return await retry_async(_get_work_item, retries=3, delay=2)
        except Exception as e:
            self.logger.error(f"API ERROR: Failed to get work item {work_item_id} using modern API: {str(e)}", exc_info=True)
            return {}
            
    async def get_fields(self, project_name=None) -> List[Dict]:
        """
        Get all work item fields available in the organization
        
        Args:
            project_name: The name of the project (defaults to the one in config)
            
        Returns:
            List of field definitions
        """
        async def _get_fields():
            project = project_name or self.config.project_name
            
            self.logger.info(f"API CALL: Getting work item fields from project '{project}' using modern API")
            
            # Create the REST URL for fields
            org_url = self.config.organization_url.rstrip('/')
            api_url = f"{org_url}/_apis/wit/fields?api-version=7.0"
            
            self.logger.info(f"API URL: {api_url}")
            
            # Create auth header with PAT
            auth_header = {
                'Authorization': f'Basic {self._get_basic_auth_string()}'
            }
            
            # Use the requests library directly
            self.logger.info(f"Sending GET request to Azure DevOps API")
            response = requests.get(api_url, headers=auth_header)
            self.logger.info(f"API Response Status: {response.status_code}")
            
            # Log the full response content if there's an error
            if response.status_code >= 400:
                self.logger.error(f"API Error Response: {response.text}")
                self.logger.error(f"API Request URL: {api_url}")
                self.logger.error(f"API Request Headers: {auth_header}")
            
            response.raise_for_status()
            
            # Extract and parse the response
            data = response.json()
            fields = data.get('value', [])
            
            self.logger.info(f"API RESULT: Successfully retrieved {len(fields)} work item fields")
            
            return fields
        
        try:
            # Use retry logic
            return await retry_async(_get_fields, retries=3, delay=2)
        except Exception as e:
            self.logger.error(f"API ERROR: Failed to get work item fields using modern API: {str(e)}", exc_info=True)
            return []
            
    async def get_work_item_attachments(self, work_item_id: int, project_name=None) -> List[Dict]:
        """
        Get attachments for a work item
        
        Args:
            work_item_id: The ID of the work item
            project_name: The name of the project (defaults to the one in config)
            
        Returns:
            List of attachment metadata
        """
        async def _get_attachments():
            project = project_name or self.config.project_name
            
            self.logger.info(f"API CALL: Getting attachments for work item {work_item_id} in project '{project}'")
            
            # First get the work item to find attachment references
            work_item = await self.get_work_item(work_item_id, project_name=project)
            
            if not work_item or 'relations' not in work_item:
                self.logger.warning(f"No relations found in work item {work_item_id}")
                return []
                
            # Filter for attachment relations
            attachment_relations = [
                relation for relation in work_item.get('relations', [])
                if relation.get('rel', '').lower() == 'attachedfile'
            ]
            
            self.logger.info(f"Found {len(attachment_relations)} attachment relations in work item {work_item_id}")
            
            attachments = []
            for relation in attachment_relations:
                # Extract attachment metadata
                attachment = {
                    'url': relation.get('url'),
                    'attributes': relation.get('attributes', {}),
                }
                
                # Add name from attributes if available
                if 'name' in relation.get('attributes', {}):
                    attachment['name'] = relation['attributes']['name']
                    
                attachments.append(attachment)
                
            self.logger.info(f"Processed {len(attachments)} attachments for work item {work_item_id}")
            return attachments
            
        try:
            # Use retry logic
            return await retry_async(_get_attachments, retries=3, delay=2)
        except Exception as e:
            self.logger.error(f"API ERROR: Failed to get attachments for work item {work_item_id}: {str(e)}", exc_info=True)
            return []
            
    async def get_attachment_content(self, attachment_url: str) -> bytes:
        """
        Download attachment content
        
        Args:
            attachment_url: The URL of the attachment
            
        Returns:
            Attachment content as bytes
        """
        async def _get_attachment():
            self.logger.info(f"API CALL: Downloading attachment from URL")
            
            # Create auth header with PAT
            auth_header = {
                'Authorization': f'Basic {self._get_basic_auth_string()}'
            }
            
            # Use the requests library directly
            self.logger.info(f"Sending GET request to download attachment")
            response = requests.get(attachment_url, headers=auth_header)
            self.logger.info(f"API Response Status: {response.status_code}")
            
            # Log the full response content if there's an error
            if response.status_code >= 400:
                self.logger.error(f"API Error Response: {response.text}")
                self.logger.error(f"API Request URL: {attachment_url}")
                self.logger.error(f"API Request Headers: {auth_header}")
            
            response.raise_for_status()
            
            # Return the raw content
            return response.content
            
        try:
            # Use retry logic
            return await retry_async(_get_attachment, retries=3, delay=2)
        except Exception as e:
            self.logger.error(f"API ERROR: Failed to download attachment: {str(e)}", exc_info=True)
            return bytes() 