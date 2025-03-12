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
            # Always use the test_client for test cases as the test_plan_client might not have this method
            return self.test_client.get_test_cases(project, plan_id, suite_id)
        except Exception as e:
            self.logger.error(f"Error retrieving test cases for suite {suite_id} in plan {plan_id}: {str(e)}")
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