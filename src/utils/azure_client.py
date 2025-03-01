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
            self.logger.info(f"Connecting to Azure DevOps: {self.config.organization_url}")
            credentials = BasicAuthentication('', self.config.personal_access_token)
            self._connection = Connection(
                base_url=self.config.organization_url,
                creds=credentials
            )
            self.logger.info("Connected to Azure DevOps successfully")
        return self._connection
    
    @property
    def test_client(self):
        if not self._test_client:
            self.logger.info("Initializing Azure DevOps Test Client")
            self._test_client = self.connection.clients.get_test_client()
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