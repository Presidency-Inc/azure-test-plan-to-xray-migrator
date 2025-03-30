import requests
import os
from requests.auth import HTTPBasicAuth

def get_attached_files(workItem):
    if not isinstance(workItem, dict):
        return []  # Return an empty list if workItem is not a dictionary

    relations = workItem.get("relations")
    if not isinstance(relations, list):
        return []  # Return an empty list if relations are missing or not a list

    attached_files = [relation for relation in relations if isinstance(relation, dict) and relation.get("rel") == "AttachedFile"]
    
    return attached_files

def download_azure_attachment(attachment_url, personal_access_token, output_filename=None, output_directory=None):
    """
    Downloads an attachment from Azure DevOps.
    
    Args:
        attachment_url (str): The URL of the attachment in Azure DevOps
        personal_access_token (str): Your Personal Access Token (PAT) for Azure DevOps
        output_filename (str, optional): Name of the output file. Defaults to "attachment.png".
        output_directory (str, optional): Directory to save the file. Defaults to current script directory.
    
    Returns:
        tuple: (success (bool), message (str)) indicating success/failure and a descriptive message
    """
    # Set default filename if not provided
    if not output_filename:
        output_filename = "attachment.png"
    
    # Set default directory to current script directory if not provided
    if not output_directory:
        output_directory = os.path.dirname(os.path.realpath(__file__))
    
    # Ensure the output directory exists
    os.makedirs(output_directory, exist_ok=True)
    
    # Full path for the output file
    output_path = os.path.join(output_directory, output_filename)
    
    # Add API version if not in the URL
    if "api-version" not in attachment_url:
        attachment_url += "?api-version=7.0"
    
    try:
        # Make the request to download the file
        response = requests.get(
            attachment_url, 
            auth=HTTPBasicAuth('', personal_access_token), 
            stream=True
        )
        
        # Check if the request was successful
        if response.status_code == 200:
            with open(output_path, "wb") as file:
                for chunk in response.iter_content(chunk_size=8192):  # Write in chunks
                    file.write(chunk)
            return True, f"File downloaded successfully: {output_path}"
        else:
            return False, f"Error: {response.status_code} - {response.text}"
    except Exception as e:
        return False, f"Exception occurred: {str(e)}"
