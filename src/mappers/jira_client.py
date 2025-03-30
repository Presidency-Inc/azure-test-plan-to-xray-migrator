import os
import json
import requests
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime
from dotenv import load_dotenv
import mimetypes
import base64

class JiraAPIError(Exception):
    """Custom exception for Jira/Confluence API errors"""
    def __init__(self, message, status_code=None, response=None):
        self.message = message
        self.status_code = status_code
        self.response = response
        super().__init__(self.message)

def setup_logging():
    """Configure logging with both file and console handlers"""
    # Create logs directory if it doesn't exist
    log_dir = 'logs'
    os.makedirs(log_dir, exist_ok=True)
    
    # Generate log filename with timestamp
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_file = os.path.join(log_dir, f'jira_client_{timestamp}.log')
    
    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'
    )
    
    # File handler with rotation
    file_handler = RotatingFileHandler(
        log_file, maxBytes=10*1024*1024, backupCount=5
    )
    file_handler.setFormatter(formatter)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    
    # Setup logger
    logger = logging.getLogger('jira_client')
    logger.setLevel(logging.DEBUG)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger

# Initialize logger
logger = setup_logging()

class JiraClient:
    def __init__(self):
        load_dotenv()
        self.username = os.getenv('JIRA_USERNAME')
        self.api_token = os.getenv('JIRA_API_TOKEN')
        self.base_url = os.getenv('CONFLUENCE_BASE_URL')
        self.base_reference_url = os.getenv('REFERENCE_BASE_URL')

        # config_path = os.path.join(os.path.dirname(__file__), 'config', 'space_pages.json')
        # with open(config_path, 'r', encoding='utf-8') as f:
        #     self.field_mapping = json.load(f)
        #     logger.debug(f"Confluence existing pages loaded: {len(self.field_mapping)}")
        
        # Validate environment variables
        missing_vars = []
        if not self.username:
            missing_vars.append('JIRA_USERNAME')
        if not self.api_token:
            missing_vars.append('JIRA_API_TOKEN')
        if not self.base_url:
            missing_vars.append('CONFLUENCE_BASE_URL')
        
        if missing_vars:
            error_msg = f"Missing required environment variables: {', '.join(missing_vars)}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        # Create base64 encoded credentials
        credentials = f"{self.username}:{self.api_token}"
        self.auth_header = base64.b64encode(credentials.encode()).decode()
        
        logger.info("JiraClient initialized with base URL: %s", self.base_url)

    def _make_request(self, method, endpoint, data=None, files=None, params=None):
        """Make HTTP request to Confluence API with proper headers and error handling"""
        url = f"{self.base_url}{endpoint}"
        headers = {
            'Authorization': f'Basic {self.auth_header}',
            'X-Atlassian-Token': 'no-check'
        }
        
        if not files:
            headers['Content-Type'] = 'application/json'
        
        try:
            # Log request details
            logger.debug(f"Making request to: {url}")
            logger.debug(f"Headers: {headers}")
            if data:
                logger.debug(f"Request data: {json.dumps(data, indent=2)}")
            
            response = requests.request(
                method=method,
                url=url,
                headers=headers,
                json=data if data and not files else None,
                files=files,
                params=params
            )
            
            logger.debug(f"API Request: {method} {url}")
            logger.debug(f"Response Status: {response.status_code}")
            logger.debug(f"Response Body: {response.text}")
            
            if response.status_code >= 400:
                error_msg = f"API request failed: {response.text}"
                logger.error(error_msg)
                raise JiraAPIError(
                    error_msg,
                    status_code=response.status_code,
                    response=response.text
                )
            
            return response.json() if response.text else None
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error: {str(e)}")
            raise JiraAPIError(f"Network error: {str(e)}")

    def create_page(self, space_key, title, content, parent_id=None, content_type='page'):
        """
        Create a new page in Confluence
        
        Args:
            space_key (str): The key of the space where the page will be created
            title (str): The title of the page
            content (str): The content of the page in storage format (wiki markup)
            parent_id (str, optional): The ID of the parent page
            content_type (str, optional): The type of content ('page' or 'blogpost')
            
        Returns:
            dict: The created page data
        """
        logger.info(f"Creating new page: {title} in space: {space_key}")
        
        data = {
            "type": content_type,
            "title": title,
            "space": {"key": space_key},
            "body": {
                "storage": {
                    "value": content,
                    "representation": "storage"
                }
            }
        }
        
        if parent_id:
            data["ancestors"] = [{"id": parent_id}]
        
        try:
            response = self._make_request(
                method='POST',
                endpoint='/rest/api/content',
                data=data
            )
            
            logger.info(f"Successfully created page with ID: {response.get('id')}")
            return response
            
        except Exception as e:
            logger.error(f"Failed to create page: {str(e)}")
            raise

    def attach_file(self, content_id, file_path, comment=None):
        """
        Attach a file to a Confluence page
        
        Args:
            content_id (str): The ID of the content to attach the file to
            file_path (str): The path to the file to attach
            comment (str, optional): A comment about the attachment
            
        Returns:
            dict: The attachment data
        """
        logger.info(f"Attaching file: {file_path} to content: {content_id}")
        
        if not os.path.exists(file_path):
            error_msg = f"File not found: {file_path}"
            logger.error(error_msg)
            raise FileNotFoundError(error_msg)
        
        try:
            # Prepare the file for upload
            file_name = os.path.basename(file_path)
            mime_type = mimetypes.guess_type(file_path)[0] or 'application/octet-stream'
            
            with open(file_path, 'rb') as file:
                files = {
                    'file': (file_name, file, mime_type)
                }
                
                params = {'comment': comment} if comment else None
                
                response = self._make_request(
                    method='POST',
                    endpoint=f'/rest/api/content/{content_id}/child/attachment',
                    files=files,
                    params=params
                )
                
                logger.info(f"Successfully attached file: {file_name}")
                return response
                
        except Exception as e:
            logger.error(f"Failed to attach file: {str(e)}")
            raise

    def get_space_property(self, space_key):
        try:
            response = self._make_request(
                method='GET',
                endpoint=f'/rest/api/space/{space_key}',
            )
            
            logger.debug(f"API Response: {response}")
            
            return response
            
        except Exception as e:
            logger.error(f"Failed to create page: {str(e)}")
            raise

    def index_data(self, data):
        indexed_data = {}
        for item in data:
            test_id = item["title"].split("-")[0].strip()  # Extract the first part of the title
            indexed_data[test_id] = item 

        with open('space_pages.json', 'w', encoding='utf-8') as f:
            json.dump(indexed_data, f, ensure_ascii=False, indent=4)

    def get_space_pages(self, space_id):
        try:
            space_pages_final_array = []
            response = self._make_request(
                method='GET',
                endpoint=f'/api/v2/spaces/{space_id}/pages',
            )
            
            # This function will accumulate the pages until there are no more "next" links
            def fetch_pages(response):
                nonlocal space_pages_final_array
                space_pages_final_array.extend(response.get('results', []))

                # Check if there is a 'next' link in the response
                next_link = response.get('_links', {}).get('next')
                if next_link:
                    next_link = next_link[next_link.find('/', next_link.find('/') + 1):]
                    response = self._make_request(
                        method='GET',
                        endpoint=next_link,
                    )
                    return fetch_pages(response)  # Recursive call to fetch the next page
                return space_pages_final_array  # No more "next", return the accumulated data
            
            # Start the recursive fetch
            all_pages = fetch_pages(response)
            self.index_data(all_pages)
            # Log and save the final response
            logger.debug(f"API Response: {all_pages}")

            return all_pages

        except Exception as e:
            logger.error(f"Error fetching space pages: {e}")
            return []

def main():
    try:
        # Example usage
        client = JiraClient()
        jira_space_key = os.getenv('JIRA_SPACE_KEY')
        
        # Example: Create a page
        page_data = client.create_page(
            space_key=jira_space_key,
            title="Test Page 4 - with attachment",
            content="<p>This is a test page created via API</p>"
        )

        logger.info(f"Created page: {page_data}")
        logger.info("-" * 80)

        # Example: Get a space property
        # space_property = client.get_space_property(
        #     space_key=jira_space_key,
        # )
        # logger.info(f"Space property: {space_property}")
        # logger.info("-" * 80)

        # space_id = "163842"
        # space_pages = client.get_space_pages(space_id)
        
        # Example: Attach a file to the created page
        if page_data:
            attachment_data = client.attach_file(
                content_id=page_data['id'],
                file_path="./attachmentFiles/exmple.csv",
                comment="Test attachment"
            )

            logger.info(f"Attachment link: {attachment_data['results'][0]['_links']['webui']}")
            
            
            # logger.debug(f"Response Body attachment: {attachment_data}")

        
            
    except Exception as e:
        logger.error(f"Main process failed: {str(e)}", exc_info=True)
        raise

if __name__ == '__main__':
    main()
