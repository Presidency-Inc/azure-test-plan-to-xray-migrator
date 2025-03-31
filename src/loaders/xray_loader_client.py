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
    log_dir = 'logs/loading_process'
    os.makedirs(log_dir, exist_ok=True)
    
    # Generate log filename with timestamp
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_file = os.path.join(log_dir, f'xray_loader_{timestamp}.log')
    
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

    def import_tests(self, tests):
        """Import tests in bulk to Xray"""
        try:
            # Ensure we have a valid token
            if not self._token:
                logger.warning("No authentication token found. Authenticating first...")
                self.authenticate()

            url = f"{self.api_url}/import/test/bulk"
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {self._token}'
            }
            
            response = requests.post(url, headers=headers, json=tests)
            
            if response.status_code == 200:
                job_id = response.json().get('jobId')
                logger.info("Import job created successfully with ID: %s", job_id)
                return job_id
            
            error_msg = f"Failed to import tests. Status code: {response.status_code}"
            logger.error(error_msg)
            logger.debug("Response content: %s", response.text)
            
            raise XrayAPIError(
                error_msg,
                status_code=response.status_code,
                response=response.text
            )
            
        except requests.exceptions.RequestException as e:
            logger.error("Network error during test import: %s", str(e))
            raise XrayAPIError(f"Network error: {str(e)}")

    def check_import_status(self, job_id):
        """Check the status of an import job"""
        if not self._token:
            logger.warning("No authentication token found. Authenticating first...")
            self.authenticate()

        url = f"{self.api_url}/import/test/bulk/{job_id}/status"
        headers = {'Authorization': f'Bearer {self._token}'}
        
        try:
            response = requests.get(url, headers=headers)
            
            if response.status_code == 200:
                status_data = response.json()
                                
                return status_data
                
            elif response.status_code == 404:
                logger.error("Import job not found: %s", job_id)
                raise XrayAPIError("Import job not found", 
                    status_code=404, response=response.text)
            else:
                logger.error("Error checking job status. Status code: %d", 
                    response.status_code)
                logger.debug("Response content: %s", response.text)
                return None
        
        except requests.exceptions.RequestException as e:
            logger.error("Network error checking job status: %s", str(e))
            return None

def process_import_job(client, file_path, imported_jobs):
    """Process a single import job and track its status"""
    try:
        file_name = os.path.basename(file_path)
        logger.info(f"Processing file: {file_name}")
        
        with open(file_path, 'r', encoding='utf-8') as f:
            mapped_tests = json.load(f)
        
        # Start import job
        job_id = client.import_tests(mapped_tests)
        
        # Monitor status until completion
        final_status = None
        final_results = None
        while True:
            status_data = client.check_import_status(job_id)
            if not status_data:
                time.sleep(30)  # Wait before retrying
                continue

            status = status_data.get('status')

            if status == 'working':
                print("-" * 80)
                logger.info("Import job is still working...")
                logger.info(f"Import job {job_id} is {status_data.get('progressValue', 0)}% complete...")
                progress_messages = status_data['progress']
                if progress_messages:
                    logger.info("Last progress message: %s", progress_messages[-1])
                print("-" * 80)

            if status in ['failed', 'successful', 'partially_successful', 'unsuccessful']:
                final_status = status
                final_results = status_data.get('result', {}) 
                break
                
            time.sleep(8)  # Wait before checking again
        
        # Record job results
        job_result = {
            "imported_file": file_name,
            "job_id": job_id,
            "status": final_status,
            "result": final_results
        }
        imported_jobs.append(job_result)
        
        logger.info(f"Import completed for {file_name} with status: {final_status}")
        
    except Exception as e:
        logger.error(f"Error processing file {file_path}: {str(e)}", exc_info=True)
        # Record failed job
        job_result = {
            "imported_file": os.path.basename(file_path),
            "job_id": job_id if 'job_id' in locals() else None,
            "status": "failed"
        }
        imported_jobs.append(job_result)

def main():
    client = XrayClient()
    imported_jobs = []
    import_dir = os.path.join(os.path.dirname(__file__), '../importFiles', '../finalImportFiles')
    process_all = False  # New flag to track if we should process all files
    
    try:
        # Ensure import directory exists
        if not os.path.exists(import_dir):
            logger.error(f"Import directory {import_dir} does not exist")
            return
        
        # Get all JSON files in the import directory
        json_files = [f for f in os.listdir(import_dir) if f.endswith('.json')]
        
        if not json_files:
            logger.warning(f"No JSON files found in {import_dir}")
            return
        
        # Create results directory and file at the start
        results_dir = os.path.join(os.path.dirname(__file__), '../importFilesResults')
        if not os.path.exists(results_dir):
            os.makedirs(results_dir)
            
        results_file = os.path.join(results_dir, f'import_results_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json')
        
        # Initialize results file with empty array
        with open(results_file, 'w', encoding='utf-8') as f:
            json.dump([], f, indent=2)
        
        # Process each file
        for file_name in json_files:
            file_path = os.path.join(import_dir, file_name)
            
            # Skip user confirmation if process_all is True
            if not process_all:
                while True:
                    print(f"\nReady to process: {file_name}")
                    response = input("Would you like to proceed with this file? (y/n/q/all): ").lower().strip()
                    
                    if response in ['y', 'n', 'q', 'all']:
                        break
                    print("Invalid input. Please enter 'y' for yes, 'n' for no, 'q' to quit, or 'all' to process all remaining files.")
                
                if response == 'q':
                    print("Script execution terminated by user.")
                    logger.info("Script execution terminated by user")
                    break
                    
                elif response == 'all':
                    process_all = True
                    print("Processing all remaining files automatically.")
                    logger.info("User selected to process all remaining files")
                    
                elif response == 'n':
                    print(f"Skipping: {file_name}")
                    logger.info(f"Skipped processing of {file_name} based on user input")
                    continue
            
            # Process file if we're in process_all mode or user said 'y'
            if process_all or response == 'y':
                process_import_job(client, file_path, imported_jobs)
                print(f"Processed: {file_name}")
                
                # Update results file immediately after processing
                with open(results_file, 'w', encoding='utf-8') as f:
                    json.dump(imported_jobs, f, indent=2)
                logger.info(f"Results file updated with {file_name}")
        
        logger.info(f"Import process completed. Final results saved in {results_file}")
        
    except Exception as e:
        logger.error(f"Import process failed: {str(e)}", exc_info=True)
        raise

if __name__ == '__main__':
    main()