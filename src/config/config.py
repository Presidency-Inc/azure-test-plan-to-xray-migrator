from pydantic_settings import BaseSettings
from pydantic import Field
import os
from dotenv import load_dotenv, find_dotenv

# Try to find the .env file in various locations
dotenv_path = find_dotenv(usecwd=True)
if dotenv_path:
    load_dotenv(dotenv_path)
    print(f"Loaded .env from: {dotenv_path}")
else:
    print("Warning: Could not find .env file!")

class AzureConfig(BaseSettings):
    organization_url: str = Field(..., description="Azure DevOps organization URL")
    personal_access_token: str = Field(..., description="Azure DevOps PAT")
    project_name: str = Field(..., description="Azure DevOps project name")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8" 