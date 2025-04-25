from math import log
import os
import json
import time
import requests
from datetime import datetime
from dotenv import load_dotenv
import logging
from logging.handlers import RotatingFileHandler
from gql import gql, Client
from gql.transport.requests import RequestsHTTPTransport
from steps_parser import parse_steps, get_attached_files
from jira_client import JiraClient
from scope_client import ScopeClient
import re

class XrayAPIError(Exception):
    """Custom exception for Xray API errors"""
    def __init__(self, message, status_code=None, response=None):
        self.message = message
        self.status_code = status_code
        self.response = response
        super().__init__(self.message)

def setup_logging():
    """Configure logging with both file and console handlers"""
    # Create logs directory if it doesn't exist
    log_dir = 'logs/folder_creation'
    os.makedirs(log_dir, exist_ok=True)
    
    # Generate log filename with timestamp
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_file = os.path.join(log_dir, f'xray_folder_creation_{timestamp}.log')
    
    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'
    )
    
    # File handler with rotation
    file_handler = RotatingFileHandler(
        log_file, 
        maxBytes=100*1024*1024,    # 100MB per file
        backupCount=1000           # Keep 1000 backup files
    )
    file_handler.setFormatter(formatter)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    
    # Setup logger
    logger = logging.getLogger('xray_client')
    logger.setLevel(logging.DEBUG)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger

# Initialize logger
logger = setup_logging()

class XrayClient:    
    def __init__(self):
        load_dotenv()
        self.client_id = os.getenv('XRAY_CLIENT_ID')
        self.client_secret = os.getenv('XRAY_CLIENT_SECRET')
        self.base_url = os.getenv('XRAY_CLOUD_BASE_URL', 'https://xray.cloud.getxray.app')
        self.api_url = f"{self.base_url}/api/v2"
        self.project_id = os.getenv('JIRA_PROJECT_ID')
        self._token = None
        self._gql_client = None

        # Load the suites data
        # with open('data/output/suites.json', 'r', encoding='utf-8') as f:
        #     self.client_suites_data = json.load(f)

        attachment_files = os.path.join(os.path.dirname(__file__), 
            f'../../attachments/extraction/work_item_attachments.json')

        self.attachment_files_path = attachment_files

        if os.path.exists(attachment_files):
            with open(attachment_files, 'r', encoding='utf-8') as f:
                self.test_cases_attachment_files = json.load(f) or []
                logger.debug(f"Loaded {len(self.test_cases_attachment_files)} attachments")
        
        # Validate environment variables
        missing_vars = []
        if not self.client_id:
            missing_vars.append('XRAY_CLIENT_ID')
        if not self.client_secret:
            missing_vars.append('XRAY_CLIENT_SECRET')
        if not self.base_url:
            missing_vars.append('XRAY_CLOUD_BASE_URL')
        if not self.project_id:
            missing_vars.append('JIRA_PROJECT_ID')
        
        if missing_vars:
            error_msg = f"Missing required environment variables: {', '.join(missing_vars)}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        logger.info("XrayClient initialized with base URL: %s", self.api_url)
        # Authenticate immediately upon initialization
        self.authenticate()

    def _get_gql_client(self):
        """Initialize or return existing GraphQL client"""
        if not self._gql_client:
            if not self._token:
                logger.warning("No authentication token found. Authenticating first...")
                self.authenticate()
                
            transport = RequestsHTTPTransport(
                url=f"{self.base_url}/api/v2/graphql",
                headers={
                    'Authorization': f'Bearer {self._token}',
                    'Content-Type': 'application/json',
                }
            )
            self._gql_client = Client(transport=transport, fetch_schema_from_transport=True)
        return self._gql_client

    def authenticate(self):
        """Authenticate with Xray API"""
        try:
            logger.debug("Attempting authentication with Xray API")
            url = f"{self.api_url}/authenticate"
            logger.debug("Authentication URL: %s", url)
            
            response = requests.post(
                url,
                json={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret
                }
            )
            
            if response.status_code == 200:
                self._token = response.text.strip('"')
                logger.info("Successfully authenticated with Xray API")
                # Recreate GraphQL client with new token
                self._gql_client = None  # Force recreation of client with new token
                return True
            else:
                logger.error(f"Authentication failed. Status code: {response.status_code}")
                logger.debug(f"Response content: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Authentication error: {str(e)}")
            return False

    def create_test_repository_folder(self, folder_path, project_id=None):
        """Create a test repository folder in Xray using GraphQL"""
        try:            
            gql_client = self._get_gql_client()
            # Create folder if it doesn't exist
            create_folder_mutation = gql("""
                mutation createFolder($projectId: String!, $path: String!) {
                    createFolder(
                        projectId: $projectId,
                        path: $path
                    ) {
                        folder {
                            name
                            path
                            testsCount
                        }
                        warnings
                    }
                }
            """)

            variables = {
                "projectId": project_id,
                "path": folder_path
            }
            
            logger.debug(f"Creating folder: {folder_path}")
            result = gql_client.execute(create_folder_mutation, variable_values=variables)
            
            if result.get('createFolder', {}).get('folder'):
                logger.info(f"Successfully created folder: {folder_path}")
                return True
            else:
                logger.error(f"Failed to create folder. Response: {result}")
                return False
                
        except Exception as e:
            logger.error(f"Error creating folder {folder_path}: {str(e)}")
            return False

    def verify_folder_structure(self, project_id, folder_path):
        """Verify the folder structure in Xray"""

        try:
            if not self._token:
                self.authenticate()
                
            gql_client = self._get_gql_client()
            
            # Check if folder exists
            check_folder_query = gql("""
                query getFolder($projectId: String!, $path: String!) {
                    getFolder(projectId: $projectId, path: $path) {
                        name
                        path
                        testsCount
                        folders
                    }
                }
            """)
            
            variables = {
                "projectId": project_id,
                "path": folder_path
            }
            
            logger.debug(f"Checking if folder exists: {folder_path}")
            try:
                result = gql_client.execute(check_folder_query, variable_values=variables)
                if result.get('getFolder'):
                    logger.info(f"Folder already exists: {folder_path}")
                    return True
            except Exception as e:
                logger.debug(f"Folder does not exist: {str(e)}")
                return False
                
        except Exception as e:
            logger.error(f"Error verifying folder structure: {str(e)}")
            return False

    def create_folder_structure(self, uniqueStrings, project_id):
        """
        Create the folder structure for a list of unique folder path strings.

        Args:
            uniqueStrings (list): List of unique folder path strings.
            project_id (str): Project identifier.
        """
        logger.info("Creating folder structure in Xray")
        created_folders = set()

        for folder_path in uniqueStrings:
            try:
                # Verify if the folder exists
                if self.verify_folder_structure(project_id, folder_path):
                    logger.info(f"Folder already exists and is ready to use: {folder_path}")
                    continue

                # Create the folder since it doesn't exist
                if self.create_test_repository_folder(folder_path, project_id):
                    logger.info(f"Successfully created folder: {folder_path}")
                    created_folders.add(folder_path)
                else:
                    logger.warning(f"Failed to create folder: {folder_path}")

            except Exception as e:
                logger.error(f"Error processing folder path '{folder_path}': {str(e)}", exc_info=True)

        logger.info("Folder structure creation process completed.")


    def build_folder_path(self, suite_id, suites_data, folder_path=None):
        """Build the full folder path from the hierarchical test plans and suites."""
        if not suite_id:
            return None

        # Initialize path parts with the root folder if provided
        path_parts = [folder_path] if folder_path else [""]

        # Convert suite_id to int if it's a string
        if isinstance(suite_id, str):
            suite_id = int(suite_id)

        logger.debug(f"Starting build_folder_path with suite_id={suite_id}")

        try:
            # Find the suite in the dataset
            current = next((suite for suite in suites_data if suite['id'] == suite_id), None)

            if not current:
                logger.warning(f"Suite {suite_id} not found in suites data")
                return None

            logger.debug(f"Found suite: {current}")

            # Collect all parts of the path
            suite_parts = []

            # Get the test plan name (root level)
            # if 'planId' in current:
            #     plan_name = next((suite['plan']['name'] for suite in suites_data if suite['plan']['id'] == current['planId']), None)
            #     if plan_name:
            #         path_parts.append(plan_name)
            #         logger.debug(f"Appended plan_name: {plan_name}")
            #     else:
            #         logger.warning(f"Plan name for planId {current['planId']} not found")

            # Traverse up the suite hierarchy using parentSuite
            while current:
                suite_parts.append(current['name'])
                logger.debug(f"Appended suite name: {current['name']}")

                parent_id = current.get('parentSuite', {}).get('id')
                if parent_id:
                    logger.debug(f"Current parentSuite ID: {parent_id}")
                    # Find parent suite
                    current = next((suite for suite in suites_data if suite['id'] == parent_id), None)
                    if current:
                        logger.debug(f"Found parent suite")
                        # logger.debug(f"Found parent suite: {current}")
                    else:
                        logger.warning(f"Parent suite {parent_id} not found")
                        break
                else:
                    logger.debug("No parentSuite ID found, reached top of hierarchy")
                    break

            # Add suites in reverse order (from root to leaf)
            path_parts.extend(reversed(suite_parts))

            built_path = '/'.join(path_parts)
            logger.debug(f"Built folder path: {built_path}")
            return built_path

        except Exception as e:
            logger.error(f"Error building folder path for suite {suite_id}: {str(e)}")
            return None


    def get_suite_name(self, suite_id):
        """Retrieve the suite name given a suite ID"""
        try:
            suites_data = self.client_suites_data()
            
            # Find the suite in the data
            suite = next((suite for suite in suites_data if str(suite.get('id')) == str(suite_id)), None)
            
            if suite:
                logger.debug(f"Found suite: {suite}")
                return suite['name']
            else:
                logger.warning(f"Suite {suite_id} not found in suites data")
                return None
                
        except Exception as e:
            logger.error(f"Error getting suite name for suite_id {suite_id}: {str(e)}")
            logger.exception("Exception details:")
            return None


def parse_time_estimate(estimate_str):
    """Convert TestRail time estimate (e.g., '8m', '1h 30m') to seconds"""
    if not estimate_str:
        return None
    
    total_seconds = 0
    # Remove any whitespace and convert to lowercase
    estimate_str = estimate_str.lower().strip()
    
    # Handle hours
    if 'h' in estimate_str:
        hours_part = estimate_str.split('h')[0]
        try:
            total_seconds += int(float(hours_part)) * 3600
        except ValueError:
            pass
        estimate_str = estimate_str.split('h')[1]
    
    # Handle minutes
    if 'm' in estimate_str:
        minutes_part = estimate_str.split('m')[0]
        try:
            total_seconds += int(float(minutes_part)) * 60
        except ValueError:
            pass
    
    return total_seconds

def format_bdd_scenarios(scenarios_data):
    """Format BDD scenarios with proper structure and numbering.
    
    Args:
        scenarios_data (list): List of dictionaries containing scenario data
            Each dictionary has a 'content' key with the scenario text
        
    Returns:
        str: Formatted scenario text with proper numbering and structure
    """
    logger.info("Starting BDD scenario formatting")
    logger.debug(f"Input scenarios data: {scenarios_data}")
    
    if not scenarios_data:
        logger.warning("No scenarios data provided")
        return None
    
    formatted_scenarios = []
    scenario_count = 0
    
    try:
        # Process each scenario in the list
        for scenario in scenarios_data:
            scenario_content = scenario.get('content', '')
            logger.debug(f"Processing scenario content:\n{scenario_content}")
            
            if not scenario_content:
                continue
                
            # Split the content into lines and process each line
            lines = [line.strip() for line in scenario_content.split('\n') if line.strip()]
            logger.debug(f"Scenario lines: {lines}")
            
            if lines:
                # Start new scenario
                scenario_count += 1
                if scenario_count > 1:
                    # Add spacing between scenarios
                    formatted_scenarios.append('')
                    formatted_scenarios.append('')
                
                # Add scenario header
                formatted_scenarios.append(f'# Scenario {scenario_count}:')
                formatted_scenarios.append('')  # Empty line after header
                
                # Add each line of the scenario
                formatted_scenarios.extend(lines)
        
        result = '\n'.join(formatted_scenarios).strip()
        logger.info(f"BDD formatting complete, generated {scenario_count} scenarios")
        logger.debug(f"Final formatted output:\n{result}")
        return result
        
    except Exception as e:
        logger.error(f"Error formatting BDD scenarios: {str(e)}")
        return None

def map_test_case(test_case, sections_data, project_key, target_info, jiraClient, xrayClient):
    """Map a TestRail test case to Xray format"""

    field_mapping = {
        "priority_mapping": {
            "1": "Highest",
            "2": "High",
            "3": "Low",
            "4": "Lowest"
        }
    }

    print(f"Field mapping test case: {test_case.get('id')}")

    # return {
    #     "id": test_case.get('id'),
    #     "name": test_case.get('testCaseTitle'),
    # }

    try:
        logger.debug(f"Starting mapping for test case {test_case.get('id')}")
        
        mapped_test = {
            "fields": {
                "project": {"key": project_key},
                "issuetype": {"name": "Test"}
            }
        }

        work_item_obj = test_case.get('workItemData', {})
        logger.debug(f"Work item object for test case {test_case.get('id')}: {work_item_obj}")
    
        # Log initial mapping details
        logger.debug(f"Initial mapping created with project key: {project_key}")
        
        # Map test type
        test_type = 'Manual'
        mapped_test['testtype'] = test_type
        logger.debug(f"Mapped test type: {test_type}")

        # Map basic fields
        mapped_test['fields']['summary'] = test_case.get('testCaseTitle', '').replace('\n', '').strip()

        # Automation status
        automation_status_field = work_item_obj['fields'].get('Microsoft.VSTS.TCM.AutomationStatus')
        logger.debug(f"Automation status field for test case {test_case.get('id')}: {automation_status_field}")

        mapped_test['fields']['customfield_15904'] = {
            "value": automation_status_field if automation_status_field == 'Not Automated' else 'Completed'
        }
        

        # State
        state_field = work_item_obj['fields'].get('System.State')
        mapped_test['fields']['description'] = mapped_test['fields'].get('description', '') + f"*State:* {state_field}\n" + '\n-----------------\n'
        # Tags
        tags_field = work_item_obj["fields"].get('System.Tags', '')
        if(tags_field):
            mapped_test['fields']['description'] = mapped_test['fields'].get('description', '') + f"*Tags:* {tags_field}\n" + '\n-----------------\n'

        # Azure reference URL
        azure_reference_url = f"https://dev.azure.com/AssetmarkInc/eWM30/_workitems/edit/{work_item_obj.get('id')}"
        mapped_test['fields']['description'] = mapped_test['fields'].get('description', '') + f"*Azure reference:* {azure_reference_url}\n" + '\n-----------------\n'

        # # ------- Attachments -------
        work_item_attached_files = get_attached_files(work_item_obj)
        logger.debug(f"Length of work_item_attached_files: {len(work_item_attached_files)}")
        
        if xrayClient.test_cases_attachment_files and work_item_attached_files:

            self_link = None
            page_data = None
            file_title = None

            for attached_file in work_item_attached_files:
                attachment_reference = f"{work_item_obj.get('id')}_{attached_file.get('attributes', {}).get('id')}"
                file_title = f"{test_case.get('id')} - {test_case.get('testCaseTitle')}"
                            
                test_case_attachment_obj = xrayClient.test_cases_attachment_files[attachment_reference]
                if(test_case_attachment_obj):

                    if("confluence_url" in test_case_attachment_obj and test_case_attachment_obj["confluence_url"]):
                        self_link = test_case_attachment_obj["confluence_url"]
                    else:
                        try:
                            # creating confluence page to attach file and get the link
                            page_data = jiraClient.create_page(
                                space_key=os.getenv('JIRA_SPACE_KEY'),
                                title=file_title,
                                content="<p>Azure test cases migration</p>"
                            )
                        except Exception as e:
                            if str(e).find("A page with this title already exists: A page already exists with the same TITLE in this space") != -1:
                                logger.warning(f"Page already exists for test case {test_case.get('id')}, ignoring exception")
                                pass
                            else:
                                logger.error(f"@@=Error mapping test case {test_case.get('id')}: {e}")
                        
                        download_dir = os.path.join(os.path.dirname(__file__), f'../../attachments')

                        if page_data:
                            
                            full_file_path = os.path.join(download_dir, test_case_attachment_obj['file_name'])
                            if not os.path.exists(full_file_path):
                                logger.warning(f"File not found: {full_file_path}")
                                continue

                            attached_process = jiraClient.attach_file(
                                content_id=page_data['id'],
                                file_path=full_file_path,
                                comment=f"Attachment in {attachment_reference}"
                            )

                            logger.debug(f"Attached process response: {attached_process}")
                            
                            self_link = f"{os.getenv('JIRA_URL')}/wiki/pages/viewpageattachments.action?pageId={page_data['id']}"
                xrayClient.test_cases_attachment_files[attachment_reference]["confluence_url"] = self_link
                xrayClient.test_cases_attachment_files[attachment_reference]["test_case_title"] = file_title
                
            with open(xrayClient.attachment_files_path, 'w', encoding='utf-8') as f:
                json.dump(xrayClient.test_cases_attachment_files, f, indent=4)
                logger.debug(f"Successfully updated {xrayClient.attachment_files_path}")

            mapped_test['fields']['description'] = mapped_test['fields'].get('description', '') + f"*Attachment Files Link:* {self_link}\n" + '\n-----------------\n'
        # ------- Attachments -------
        
        # Map priority with enhanced debug logging
        priority = work_item_obj.get('fields', {}).get('Microsoft.VSTS.Common.Priority', '3')
        priority_id = str(priority)
        mapped_priority = field_mapping['priority_mapping'].get(priority_id, 'Low')
        
        logger.info(f"""Priority Mapping for Test Case {test_case.get('id')} - "{test_case.get('title')}":
            TestRail Priority ID: {priority_id}
            Mapped to Xray Priority: {mapped_priority}
        """)
        
        mapped_test['fields']['priority'] = {
            "name": mapped_priority
        }
        
        # Map test steps based on type
        if test_type == 'Manual':
            steps = []
            work_items_steps_field = work_item_obj.get('fields', {}).get('Microsoft.VSTS.TCM.Steps')
            if work_items_steps_field:
                steps.extend(parse_steps(work_items_steps_field))

            logger.debug(f"Steps for test case {test_case.get('id')}: {steps}")
                        
            if steps:
                mapped_test['steps'] = steps

        pattern = r'!\[\]\(.*?\)'
        description = re.sub(pattern, '', mapped_test['fields']['description'])

        mapped_test['fields']['description'] = description

        return mapped_test
        
    except Exception as e:
        logger.error(f"Error mapping test case {test_case.get('id')}: {str(e)}", exc_info=True)
        raise

def get_nested_value(obj, path):
    """Get a value from a nested dictionary using dot notation.
    
    Args:
        obj (dict): The dictionary to search in
        path (str): The path to the value using dot notation (e.g., 'fields.summary')
    
    Returns:
        The value if found, None otherwise
    """
    try:
        parts = path.split('.')
        current = obj
        for part in parts:
            if not isinstance(current, dict):
                return None
            current = current.get(part)
        return current
    except Exception:
        return None

def validate_test_case(mapped_test):
    """Validate required fields for Xray import"""
    required_fields = {
        'testtype': 'Test Type',
        'fields.summary': 'Summary'
    }
    
    missing_fields = []
    for field, name in required_fields.items():
        if not get_nested_value(mapped_test, field):
            missing_fields.append(name)
    
    if missing_fields:
        raise ValueError(f"Missing required fields: {', '.join(missing_fields)}")

def get_nested_children_path(source_suite_id, sections_data):
    """
    Recursively find all suites in the hierarchy, including parent and leaf suites.
    
    Args:
        source_suite_id: ID of the parent suite
        sections_data: List of all suites
        
    Returns:
        List of IDs of all suites in the hierarchy, including parent suites
    """
    # Find the current suite in the data
    current_suite = next((section for section in sections_data if str(section.get('id')) == str(source_suite_id)), None)
    
    if not current_suite:
        logger.warning(f"Suite {source_suite_id} not found in sections data during get_nested_children_path call")
        return []
    
    # Always include the current suite ID in the results
    result_ids = [str(source_suite_id)]
    
    # If this suite has children, find and add them too
    if current_suite.get('hasChildren'):
        # Find all direct children of this suite
        children = [section for section in sections_data 
                   if section.get('parentSuite') and str(section.get('parentSuite').get('id')) == str(source_suite_id)]
        
        if children:
            # Sort children by ID to ensure consistent processing
            children.sort(key=lambda x: x.get('id'))
            
            # Get all child IDs (recursively)
            for child in children:
                child_id = str(child.get('id'))
                # Recursively get all children for this child
                child_ids = get_nested_children_path(child_id, sections_data)
                # Add all child IDs found
                result_ids.extend(child_ids)
    
    return result_ids

def get_ancestor_and_self_ids(start_suite_id, sections_data):
    """
    Collects the start_suite_id and all its direct ancestor suite IDs.
    Traverses upwards from the start_suite_id using the parentSuite link.
    
    Args:
        start_suite_id (str): The ID of the suite to start traversal from.
        sections_data (list): List of all suite data dictionaries.
        
    Returns:
        list: A list of suite IDs including the start_suite_id and all its ancestors.
              Returns an empty list if the start_suite_id is not found.
    """
    logger.debug(f"Collecting ancestor IDs starting from suite {start_suite_id}")
    ancestor_suite_ids = []

    # Create a quick lookup map for efficiency
    sections_map = {str(suite.get('id')): suite for suite in sections_data if suite.get('id')}

    current_id = str(start_suite_id)

    while current_id:
        current_suite_obj = sections_map.get(current_id)

        if not current_suite_obj:
            logger.error(f"Suite ID {current_id} (part of ancestor chain for {start_suite_id}) not found in sections_data. Stopping upward traversal.")
            # Decide if we should return partial list or empty
            # Returning partial might be useful, but could also hide data issues.
            # Let's return what we found so far, but log clearly.
            break 

        # Add the current suite ID to our list
        if current_id not in ancestor_suite_ids: # Avoid duplicates if data is weird
             ancestor_suite_ids.append(current_id)
             logger.debug(f"Added suite {current_id} to ancestor list.")
        else:
             logger.warning(f"Detected potential loop or duplicate entry for suite {current_id} during ancestor traversal.")
             break # Break to prevent infinite loop

        # Get the parent suite ID
        parent_info = current_suite_obj.get('parentSuite')
        if not parent_info or not parent_info.get('id'):
            logger.debug(f"Reached top-level suite (no parent found for {current_id}). Stopping upward traversal.")
            current_id = None # No more parents, exit loop
        else:
            parent_id = str(parent_info.get('id'))
            logger.debug(f"Moving from suite {current_id} up to parent {parent_id}.")
            current_id = parent_id
            
    if not ancestor_suite_ids and str(start_suite_id) not in sections_map:
         logger.error(f"The initial start_suite_id {start_suite_id} was not found in sections_data at all.")
         return [] # Return empty list if the starting point itself wasn't found

    logger.info(f"Collected {len(ancestor_suite_ids)} suite IDs (self and ancestors) for starting suite {start_suite_id}: {ancestor_suite_ids}")
    return ancestor_suite_ids

def main():
    try:
        logger.info("Starting Xray test import process")
        client = XrayClient()
        scope_client = ScopeClient()
        jiraClient = JiraClient()

        logger.info(f"Loaded {scope_client.projects_counter()} projects to migrate")

        # Load sections data (suites.json)
        sections_file = os.path.join(os.path.dirname(__file__), 
            f'../../output/data/extraction/extracted_data/test_suites.json')
        with open(sections_file, 'r', encoding='utf-8') as f:
            sections_data = json.load(f)
            logger.debug(f"Loaded {len(sections_data)} sections (suites)")
        
        # Create a quick lookup map for sections_data by ID for efficiency (moved here for single load)
        # sections_map = {str(suite.get('id')): suite for suite in sections_data if suite.get('id')}
        # logger.debug(f"Created sections map with {len(sections_map)} entries.")
        # Note: sections_map is created within find_branch_root_and_all_ids now


        test_cases_file = os.path.join(os.path.dirname(__file__), 
            f'../../output/data/extraction/extracted_data/test_cases.json')
        with open(test_cases_file, 'r', encoding='utf-8') as f:
            test_cases = json.load(f)
            logger.info(f"Loaded {len(test_cases)} test cases")

        for project in scope_client.migration_projects:
            source_plan_id = str(project['source_plan_id'])
            source_suite_id = str(project['source_suite_id']) # This is the suite ID from the scope file
            logger.info(f"Processing scope entry: Plan ID {source_plan_id}, Suite ID {source_suite_id}")
            
            # Find the complete set of suite IDs for the hierarchy branch
            # containing source_suite_id within the source_plan_id.
            effective_suite_ids = get_ancestor_and_self_ids(source_suite_id, sections_data)

            if not effective_suite_ids:
                logger.warning(f"Could not determine effective suite IDs for starting suite {source_suite_id}. Skipping this scope entry.")
                continue

            try:
                mapped_tests = []
                
                scope_client.update_current_scope(source_plan_id, source_suite_id) # Keep using original source_suite_id for scope context if needed downstream
                target_info = scope_client.get_current_target_info()
                logger.debug(f"Target info for project mode: {json.dumps(target_info, indent=2)}")

                uniqueStrings = set() # For folder paths

                for test_case in test_cases:
                    try:
                        test_suite_id = str(test_case.get('suiteId'))
                        test_plan_id = str(test_case.get('planId'))
                        
                        # Check if this test case belongs to the correct plan and any suite in our full branch list
                        if test_plan_id != source_plan_id or test_suite_id not in effective_suite_ids:
                            continue # Ignore test case

                        logger.debug(f"Mapping test case {test_case.get('id')} from suite {test_suite_id} (Plan: {test_plan_id})")
                        mapped_test = map_test_case(test_case, sections_data, 
                            target_info['project_target_key'], target_info, jiraClient, client)
                        logger.debug(f"Successfully mapped test case {test_case.get('id')}")
                        
                        # Folder path generation still uses the original test_case['suiteId']
                        if test_case.get('suiteId'):
                            # Pass sections_data list to build_folder_path as it likely expects the original structure
                            folder_path = client.build_folder_path(test_case['suiteId'], sections_data, target_info['folder_path'])
                            if folder_path:
                                mapped_test['xray_test_repository_folder'] = folder_path
                                logger.debug(f"Added folder path: {folder_path}")
                                uniqueStrings.add(folder_path) # Collect unique folder paths
                        
                        # validate_test_case(mapped_test) # Assuming validation is desired
                        mapped_tests.append(mapped_test)
                        logger.debug(f"Test case {test_case.get('id')} added to mapped tests")
                        
                    except Exception as e:
                        logger.error(f"Error mapping test case {test_case.get('id')}: {str(e)}", exc_info=True)
                        continue # Skip this test case

                # Convert set back to list if needed for folder creation
                uniqueFolderPaths = list(uniqueStrings)

                logger.info(f"Found {len(uniqueFolderPaths)} unique folder paths for scope entry (Plan: {source_plan_id}, Suite: {source_suite_id})")
                # Create folder structure based on paths derived from all mapped test cases in the branch
                client.create_folder_structure(uniqueFolderPaths, target_info['project_target_id'])
                
                # Save mapped tests to file, named using plan and the specific source_suite_id from scope file
                if mapped_tests:
                    logger.info(f"Saving {len(mapped_tests)} mapped tests to file")
                    folder_path = os.path.join(os.path.dirname(__file__), '../importFiles')
                    os.makedirs(folder_path, exist_ok=True)
                    
                    # Use the original source_suite_id from the scope file for the output filename
                    output_file = os.path.join(folder_path, f'test_cases_{source_plan_id}_{source_suite_id}.json') 
                    with open(output_file, 'w', encoding='utf-8') as f:
                        json.dump(mapped_tests, f, indent=2, ensure_ascii=False)
                    logger.info(f"Successfully wrote mapped tests for scope entry ({source_plan_id}, {source_suite_id}) to {output_file}")
                else:
                    logger.warning(f"No test cases were mapped for scope entry (Plan: {source_plan_id}, Suite: {source_suite_id}) containing {len(effective_suite_ids)} effective suites.")


                logger.info(f"Successfully processed scope entry (Plan: {source_plan_id}, Suite: {source_suite_id})")
                
            except Exception as e:
                logger.error(f"Error processing scope entry (Plan: {source_plan_id}, Suite: {source_suite_id}): {str(e)}", exc_info=True)
                
    except Exception as e:
        logger.error(f"Import process failed: {str(e)}", exc_info=True)
        raise

if __name__ == '__main__':
    main()
