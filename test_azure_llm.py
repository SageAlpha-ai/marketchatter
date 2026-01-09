"""Azure OpenAI connectivity smoke test"""

import scripts.init_env  # MUST be first

import os
from langchain_openai import AzureChatOpenAI
llm = AzureChatOpenAI(
    azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
    azure_deployment=os.environ["AZURE_OPENAI_DEPLOYMENT_NAME"],
    api_version=os.environ["AZURE_OPENAI_API_VERSION"],
    api_key=os.environ["AZURE_OPENAI_API_KEY"],
)

response = llm.invoke("Say OK if Azure OpenAI is working.")
print(response.content)
print("Deployment =", os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME"))
