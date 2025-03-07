from pydantic_settings import BaseSettings
from pydantic import Field

class AzureConfig(BaseSettings):
    organization_url: str = Field(..., description="Azure DevOps organization URL")
    personal_access_token: str = Field(..., description="Azure DevOps PAT")
    project_name: str = Field(..., description="Azure DevOps project name")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8" 