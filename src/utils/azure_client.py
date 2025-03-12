from azure.devops.connection import Connection
from msrest.authentication import BasicAuthentication
from config.config import AzureConfig
import logging

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
    
    def get_test_cases(self, project, plan_id, suite_id):
        """Get test cases for a test suite"""
        try:
            self.logger.info(f"Retrieving test cases for plan {plan_id}, suite {suite_id} in project: {project}")
            
            # Log the current client being used
            self.logger.info(f"Test client type: {type(self.test_client)}")
            
            # First try the standard test_client method
            try:
                self.logger.info("Attempting to retrieve test cases using standard method")
                test_cases = self.test_client.get_test_cases(project, plan_id, suite_id)
                test_case_count = len(test_cases) if test_cases else 0
                self.logger.info(f"Retrieved {test_case_count} test cases using standard method")
                return test_cases
            except AttributeError as ae:
                self.logger.warning(f"Standard test case retrieval method not available: {str(ae)}")
                
                # Try an alternative approach - Test Plan API
                try:
                    self.logger.info("Attempting to retrieve test cases using test plan client")
                    if self._test_plan_client:
                        # Check if test plan client has get_test_cases method
                        if hasattr(self._test_plan_client, 'get_test_cases'):
                            test_cases = self._test_plan_client.get_test_cases(project, plan_id, suite_id)
                            self.logger.info(f"Retrieved test cases using test plan client")
                            return test_cases
                        # Try get_test_case_list if available
                        elif hasattr(self._test_plan_client, 'get_test_case_list'):
                            self.logger.info("Trying get_test_case_list method")
                            test_cases = self._test_plan_client.get_test_case_list(project, plan_id, suite_id)
                            self.logger.info(f"Retrieved test cases using get_test_case_list")
                            return test_cases
                except Exception as e:
                    self.logger.warning(f"Alternative test case retrieval method failed: {str(e)}")
                    
                # Try through suite API if available
                try:
                    self.logger.info("Attempting to retrieve test cases through suite API")
                    if hasattr(self.test_client, 'get_suite_test_cases'):
                        test_cases = self.test_client.get_suite_test_cases(project, suite_id)
                        self.logger.info(f"Retrieved test cases using suite API")
                        return test_cases
                except Exception as e:
                    self.logger.warning(f"Suite API test case retrieval method failed: {str(e)}")
                
                # Try using work item tracking client as a fallback
                try:
                    self.logger.info("Attempting to retrieve test cases using work item tracking client")
                    test_cases = self.get_test_cases_via_work_items(project, plan_id, suite_id)
                    if test_cases:
                        self.logger.info(f"Retrieved test cases using work item tracking client")
                        return test_cases
                except Exception as e:
                    self.logger.warning(f"Work item tracking client test case retrieval failed: {str(e)}")
                
                # If all methods fail, log the issue and return empty list
                self.logger.error("All test case retrieval methods failed")
                return []
            
        except Exception as e:
            self.logger.error(f"Error retrieving test cases for suite {suite_id} in plan {plan_id}: {str(e)}")
            return []
    
    def get_test_cases_via_work_items(self, project, plan_id, suite_id):
        """
        Fallback method to get test cases by querying work items
        This is a custom implementation that simulates the structure returned by get_test_cases
        """
        try:
            self.logger.info(f"Using work item tracking client to retrieve test cases for suite {suite_id}")
            
            # First, try to get test case IDs from either test client or test plan client
            test_case_refs = []
            try:
                if hasattr(self.test_client, 'get_test_case_references'):
                    self.logger.info("Getting test case references from test client")
                    test_case_refs = self.test_client.get_test_case_references(project, plan_id, suite_id)
                elif hasattr(self._test_plan_client, 'get_test_case_references'):
                    self.logger.info("Getting test case references from test plan client")
                    test_case_refs = self._test_plan_client.get_test_case_references(project, plan_id, suite_id)
            except Exception as e:
                self.logger.warning(f"Could not get test case references: {str(e)}")
                return []
            
            # If we got references, extract work item IDs
            work_item_ids = []
            for ref in test_case_refs:
                if hasattr(ref, 'id'):
                    work_item_ids.append(ref.id)
                elif hasattr(ref, 'work_item') and hasattr(ref.work_item, 'id'):
                    work_item_ids.append(ref.work_item.id)
            
            if not work_item_ids:
                self.logger.warning("No work item IDs found in test case references")
                # Try to query for test case work items as a last resort
                try:
                    # WIQL query to find test cases
                    from azure.devops.v6_0.work_item_tracking.models import Wiql
                    wiql = Wiql(
                        query=f"SELECT [System.Id] FROM WorkItems WHERE [System.WorkItemType] = 'Test Case' AND [System.TeamProject] = '{project}'"
                    )
                    wiql_results = self.work_item_client.query_by_wiql(wiql).work_items
                    work_item_ids = [int(result.id) for result in wiql_results]
                    self.logger.info(f"Retrieved {len(work_item_ids)} potential test case work items via WIQL query")
                except Exception as wiql_error:
                    self.logger.warning(f"WIQL query failed: {str(wiql_error)}")
                    return []
            
            # Get the work items for these IDs
            if not work_item_ids:
                return []
            
            self.logger.info(f"Retrieving {len(work_item_ids)} work items for test cases")
            
            # Get work items in batches to avoid exceeding API limits
            batch_size = 100
            all_work_items = []
            
            for i in range(0, len(work_item_ids), batch_size):
                batch = work_item_ids[i:i+batch_size]
                try:
                    # Get work items with detailed fields
                    work_items = self.work_item_client.get_work_items(
                        project=project,
                        ids=batch,
                        expand="All"
                    )
                    all_work_items.extend(work_items)
                except Exception as batch_error:
                    self.logger.warning(f"Error retrieving batch of work items: {str(batch_error)}")
            
            # Convert work items to test case format
            self.logger.info(f"Converting {len(all_work_items)} work items to test case format")
            test_cases = []
            for work_item in all_work_items:
                # Only include test cases
                if hasattr(work_item.fields, 'System.WorkItemType') and work_item.fields['System.WorkItemType'] == 'Test Case':
                    # Create a simulated test case object
                    from types import SimpleNamespace
                    test_case = SimpleNamespace()
                    test_case.id = work_item.id
                    test_case.name = work_item.fields.get('System.Title', f"Test Case {work_item.id}")
                    
                    # Create a work item reference
                    work_item_ref = SimpleNamespace()
                    work_item_ref.id = work_item.id
                    work_item_ref.url = work_item.url if hasattr(work_item, 'url') else None
                    
                    # Attach work item reference to test case
                    test_case.work_item = work_item_ref
                    
                    # Add any other available properties
                    if 'Microsoft.VSTS.Common.Priority' in work_item.fields:
                        test_case.priority = work_item.fields['Microsoft.VSTS.Common.Priority']
                    
                    if 'System.Description' in work_item.fields:
                        test_case.description = work_item.fields['System.Description']
                    
                    test_cases.append(test_case)
            
            self.logger.info(f"Successfully created {len(test_cases)} test case objects from work items")
            return test_cases
        
        except Exception as e:
            self.logger.error(f"Error in get_test_cases_via_work_items: {str(e)}")
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