from azure.devops.connection import Connection
from msrest.authentication import BasicAuthentication
from config.config import AzureConfig
import logging
import os
import sys

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
            
            # Try connection with PAT
            try:
                self.logger.info("Attempting connection with PAT...")
                credentials = BasicAuthentication('', self.config.personal_access_token)
                self._connection = Connection(
                    base_url=org_url,
                    creds=credentials
                )
                self.logger.info("Connected to Azure DevOps successfully using PAT")
            except Exception as e:
                self.logger.error(f"PAT authentication failed: {str(e)}")
                
                # If PAT fails, check if we have username/password environment variables
                username = os.environ.get("AZURE_USERNAME")
                password = os.environ.get("AZURE_PASSWORD")
                
                if username and password:
                    try:
                        self.logger.info(f"Attempting connection with username: {username[:3]}...")
                        credentials = BasicAuthentication(username, password)
                        self._connection = Connection(
                            base_url=org_url,
                            creds=credentials
                        )
                        self.logger.info("Connected to Azure DevOps successfully using username/password")
                    except Exception as e:
                        self.logger.error(f"Username/password authentication failed: {str(e)}")
                        raise Exception("All authentication methods failed")
                else:
                    self.logger.error("No alternative authentication methods available")
                    raise
        return self._connection
    
    @property
    def test_client(self):
        if not self._test_client:
            self.logger.info("Initializing Azure DevOps Test Client")
            try:
                # Print available client methods for debugging
                self.logger.info("Available clients:")
                for client_method in dir(self.connection.clients):
                    if not client_method.startswith('_'):
                        self.logger.info(f"  - {client_method}")
                
                self._test_client = self.connection.clients.get_test_client()
                self.logger.info("Azure DevOps Test Client initialized successfully")
            except Exception as e:
                self.logger.error(f"Failed to initialize Test Client: {str(e)}")
                # Try to use core client as a test
                try:
                    self.logger.info("Testing with core client as fallback...")
                    core_client = self.connection.clients.get_core_client()
                    projects = core_client.get_projects()
                    proj_names = [p.name for p in projects]
                    self.logger.info(f"Projects accessible: {proj_names}")
                    if self.config.project_name not in proj_names:
                        self.logger.error(f"Project {self.config.project_name} not found in accessible projects!")
                except Exception as inner_e:
                    self.logger.error(f"Core client test failed: {str(inner_e)}")
                
                self.logger.error(f"Error getting test client from client's connection: {str(e)}")
                return None
        return self._test_client
    
    @property
    def work_item_client(self):
        if not self._work_item_client:
            self.logger.info("Initializing Azure DevOps Work Item Client")
            try:
                self._work_item_client = self.connection.clients.get_work_item_tracking_client()
            except Exception as e:
                self.logger.error(f"Failed to initialize Work Item Client: {str(e)}")
                return None
        return self._work_item_client
    
    @property
    def git_client(self):
        if not self._git_client:
            self.logger.info("Initializing Azure DevOps Git Client")
            try:
                self._git_client = self.connection.clients.get_git_client()
            except Exception as e:
                self.logger.error(f"Failed to initialize Git Client: {str(e)}")
                return None
        return self._git_client
    
    async def get_work_item(self, work_item_id):
        """Get a work item by ID"""
        try:
            self.logger.info(f"Retrieving work item: {work_item_id}")
            if not self.work_item_client:
                self.logger.error("Work item client not initialized")
                return None
            return await self.work_item_client.get_work_item(work_item_id, self.config.project_name)
        except Exception as e:
            self.logger.error(f"Error retrieving work item {work_item_id}: {str(e)}")
            return None
    
    async def get_test_plan_by_id(self, project, plan_id):
        """Get a test plan by ID"""
        try:
            self.logger.info(f"Retrieving test plan: {plan_id} from project: {project}")
            if not self.test_client:
                self.logger.error("Test client not initialized")
                return None
            return await self.test_client.get_test_plan_by_id(project, plan_id)
        except Exception as e:
            self.logger.error(f"Error retrieving test plan {plan_id}: {str(e)}")
            return None
    
    async def get_test_suite_by_id(self, project, plan_id, suite_id):
        """Get a test suite by ID"""
        try:
            self.logger.info(f"Retrieving test suite: {suite_id} from plan {plan_id} in project: {project}")
            if not self.test_client:
                self.logger.error("Test client not initialized")
                return None
            return await self.test_client.get_test_suite_by_id(project, plan_id, suite_id)
        except Exception as e:
            self.logger.error(f"Error retrieving test suite {suite_id} from plan {plan_id}: {str(e)}")
            return None 