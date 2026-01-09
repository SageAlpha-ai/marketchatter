"""
LLM Factory for Azure OpenAI Cognitive Services.

This module provides a centralized factory function for creating Azure OpenAI
AzureChatOpenAI instances with consistent configuration.
"""

import os
from langchain_openai import AzureChatOpenAI


def create_azure_openai_llm(temperature: float = 0) -> AzureChatOpenAI:
    """
    Create an AzureChatOpenAI instance configured for Azure OpenAI Cognitive Services.
    
    Uses environment variables:
        AZURE_OPENAI_API_KEY: Azure OpenAI API key (required)
        AZURE_OPENAI_ENDPOINT: Azure OpenAI endpoint URL (required)
        AZURE_OPENAI_DEPLOYMENT_NAME: Azure OpenAI deployment name (required)
        AZURE_OPENAI_API_VERSION: API version (default: 2024-02-15-preview)
    
    Args:
        temperature: Temperature parameter for the LLM (default: 0)
        
    Returns:
        AzureChatOpenAI instance configured for Azure OpenAI
        
    Raises:
        ValueError: If required Azure OpenAI environment variables are missing
    """
    # Get Azure OpenAI configuration from environment variables
    api_key = os.environ["AZURE_OPENAI_API_KEY"]
    azure_endpoint = os.environ["AZURE_OPENAI_ENDPOINT"]
    deployment_name = os.environ["AZURE_OPENAI_DEPLOYMENT_NAME"]
    api_version = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")
    
    # Create AzureChatOpenAI instance with Azure configuration
    return AzureChatOpenAI(
        azure_endpoint=azure_endpoint,
        azure_deployment=deployment_name,
        api_version=api_version,
        api_key=api_key,
        temperature=temperature
    )

