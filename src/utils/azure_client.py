from azure.devops.connection import Connection
from msrest.authentication import BasicAuthentication
from config.config import AzureConfig
import logging

class AzureDevOpsClient:
    def __init__(self, config: AzureConfig):
        self.config = config
        self._connection = None
        self._test_client = None
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
                    
            try:
                self._test_client = self.connection.clients.get_test_client()
                self.logger.info("Azure DevOps Test Client initialized successfully")
            except Exception as e:
                self.logger.error(f"Failed to initialize Test Client: {str(e)}")
                raise
        return self._test_client
    
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
    
    async def get_work_item(self, work_item_id):
        """Get a work item by ID"""
        try:
            self.logger.info(f"Retrieving work item: {work_item_id}")
            return await self.work_item_client.get_work_item(work_item_id, self.config.project_name)
        except Exception as e:
            self.logger.error(f"Error retrieving work item {work_item_id}: {str(e)}")
            return None
    
    async def get_test_plan_by_id(self, project, plan_id):
        """Get a test plan by ID"""
        try:
            self.logger.info(f"Retrieving test plan: {plan_id} from project: {project}")
            return await self.test_client.get_test_plan_by_id(project, plan_id)
        except Exception as e:
            self.logger.error(f"Error retrieving test plan {plan_id}: {str(e)}")
            return None
    
    async def get_test_suite_by_id(self, project, plan_id, suite_id):
        """Get a test suite by ID"""
        try:
            self.logger.info(f"Retrieving test suite: {suite_id} from plan {plan_id} in project: {project}")
            return await self.test_client.get_test_suite_by_id(project, plan_id, suite_id)
        except Exception as e:
            self.logger.error(f"Error retrieving test suite {suite_id} from plan {plan_id}: {str(e)}")
            return None 