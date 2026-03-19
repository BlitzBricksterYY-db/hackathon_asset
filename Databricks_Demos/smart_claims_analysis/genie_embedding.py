import requests
import json
import time
import pandas as pd
from dotenv import load_dotenv
import os
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class GenieAPI:
    def __init__(self):
        load_dotenv()  # This will load local .env if it exists, but Databricks env vars take precedence
        
        # Get required environment variables with error handling
        self.databricks_host = os.environ.get('DATABRICKS_HOST')
        self.databricks_client_id = os.environ.get('DATABRICKS_CLIENT_ID')
        self.databricks_client_secret = os.environ.get('DATABRICKS_CLIENT_SECRET')
        self.space_id_apex = os.environ.get('DATABRICKS_GENIE_SPACE_ID_APEX')
        self.space_id_synergy = os.environ.get('DATABRICKS_GENIE_SPACE_ID_SYNERGY')
        self.access_token = None
        self.token_expiry = None
        
        # Remove 'https://' if present in host
        if self.databricks_host and self.databricks_host.startswith('https://'):
            self.databricks_host = self.databricks_host[8:]
        
        # Validate required credentials
        missing_vars = []
        if not self.databricks_host:
            missing_vars.append('DATABRICKS_HOST')
        if not self.databricks_client_id:
            missing_vars.append('DATABRICKS_CLIENT_ID')
        if not self.databricks_client_secret:
            missing_vars.append('DATABRICKS_CLIENT_SECRET')
        
        if missing_vars:
            error_msg = f"Missing required Databricks credentials: {', '.join(missing_vars)}"
            logger.error(error_msg)
            raise ValueError(error_msg)

    def get_space_id(self, app):
        """Get the appropriate space ID based on the app"""
        if app == 'va':
            space_id = self.space_id_apex
        else:
            space_id = self.space_id_synergy
            
        if not space_id:
            logger.error(f"No space ID found for app: {app}")
            raise ValueError(f"No space ID found for app: {app}")
            
        return space_id

    def get_oauth_token(self, force_refresh=False):
        """Get OAuth token for API authentication"""
        try:
            # Check if we need to refresh the token
            if not force_refresh and self.access_token and self.token_expiry and time.time() < self.token_expiry:
                return self.access_token

            token_url = f"https://{self.databricks_host}/oidc/v1/token"
            payload = {
                "grant_type": "client_credentials",
                "client_id": self.databricks_client_id,
                "client_secret": self.databricks_client_secret,
                "scope": "all-apis genie-api"
            }
            logger.info(f"Requesting OAuth token from {token_url}")
            response = requests.post(token_url, data=payload)
            response.raise_for_status()
            
            data = response.json()
            if 'access_token' not in data:
                raise ValueError("No access token in response")
                
            self.access_token = data["access_token"]
            # Set token expiry to 90% of the actual expiry time to be safe
            self.token_expiry = time.time() + (int(data.get("expires_in", 3600)) * 0.9)
            logger.info("Successfully obtained OAuth token")
            return self.access_token
        except Exception as e:
            logger.error(f"Failed to get OAuth token: {e}")
            raise

    def _make_request(self, method, url, headers=None, json=None, data=None, retry_count=0):
        """Make an API request with automatic token refresh"""
        try:
            if not headers:
                headers = {}
            if not self.access_token:
                self.get_oauth_token()
            headers["Authorization"] = f"Bearer {self.access_token}"
            
            response = requests.request(method, url, headers=headers, json=json, data=data)
            
            # If unauthorized, try refreshing token once
            if response.status_code == 401 and retry_count == 0:
                logger.info("Token expired, refreshing...")
                self.get_oauth_token(force_refresh=True)
                return self._make_request(method, url, headers, json, data, retry_count=1)
                
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed: {e}")
            raise

    def start_conversation(self, question, app='va'):
        """Start a new conversation with Genie"""
        try:
            space_id = self.get_space_id(app)
            url = f"https://{self.databricks_host}/api/2.0/lakehouse-ai/conversations"
            headers = {"Content-Type": "application/json"}
            payload = {
                "space_id": space_id,
                "content": question
            }
            
            response = self._make_request("POST", url, headers=headers, json=payload)
            data = response.json()
            
            conversation_id = data.get("conversation_id")
            message_id = data.get("message_id")
            
            if not conversation_id or not message_id:
                raise ValueError("Invalid response format from Genie API")
                
            return {
                "conversation_id": conversation_id,
                "message_id": message_id
            }
        except Exception as e:
            logger.error(f"Failed to start conversation: {e}")
            raise

    def continue_conversation(self, conversation_id, question, app='va'):
        """Continue an existing conversation"""
        try:
            space_id = self.get_space_id(app)
            url = f"https://{self.databricks_host}/api/2.0/lakehouse-ai/conversations/{conversation_id}/messages"
            headers = {"Content-Type": "application/json"}
            payload = {
                "space_id": space_id,
                "content": question
            }
            
            response = self._make_request("POST", url, headers=headers, json=payload)
            data = response.json()
            
            message_id = data.get("message_id")
            if not message_id:
                raise ValueError("Invalid response format from Genie API")
            
            return {
                "message_id": message_id
            }
        except Exception as e:
            logger.error(f"Failed to continue conversation: {e}")
            raise

    def get_message_status(self, conversation_id, message_id, app='va'):
        """Poll for message status and get results when ready"""
        try:
            space_id = self.get_space_id(app)
            url = f"https://{self.databricks_host}/api/2.0/lakehouse-ai/conversations/{conversation_id}/messages/{message_id}"
            
            max_retries = 12
            retry_count = 0
            
            while retry_count < max_retries:
                response = self._make_request("GET", url)
                data = response.json()
                
                status = data.get("status")
                if status == "COMPLETED":
                    return {
                        "status": "COMPLETED",
                        "content": data.get("content"),
                        "query_result": data.get("query_result"),
                        "description": data.get("description"),
                        "conversation_id": conversation_id
                    }
                elif status in ["FAILED", "CANCELLED"]:
                    return {
                        "status": status,
                        "error": data.get("error", "Request failed or was cancelled")
                    }
                
                retry_count += 1
                time.sleep(10)
            
            return {"status": "TIMEOUT", "error": "Request timed out"}
        except Exception as e:
            logger.error(f"Failed to get message status: {e}")
            raise

def get_genie_response(question, conversation_id=None, app='va'):
    """Main function to get responses from Genie"""
    genie = GenieAPI()
    
    try:
        logger.info(f"Initializing Genie request - App: {app}, Conversation ID: {conversation_id}")
        logger.info(f"Using Databricks host: {genie.databricks_host}")
        
        if conversation_id:
            # Continue existing conversation
            logger.info(f"Continuing conversation {conversation_id}")
            result = genie.continue_conversation(conversation_id, question, app)
            message_id = result["message_id"]
            logger.info(f"Got message ID: {message_id} for continued conversation")
        else:
            # Start new conversation
            logger.info("Starting new conversation")
            result = genie.start_conversation(question, app)
            conversation_id = result["conversation_id"]
            message_id = result["message_id"]
            logger.info(f"Started new conversation - ID: {conversation_id}, Message ID: {message_id}")
        
        # Poll for results
        logger.info(f"Polling for results (conversation_id: {conversation_id}, message_id: {message_id})")
        response = genie.get_message_status(conversation_id, message_id, app)
        
        # Log response status
        logger.info(f"Genie response status: {response.get('status')}")
        if response.get("status") == "ERROR":
            error_msg = response.get("error") or "An unknown error occurred with Genie."
            logger.error(f"Genie API error: {error_msg}")
            return {"status": "ERROR", "error": error_msg}
            
        # If no content in response, return error
        if not response.get("content"):
            logger.error("No content in Genie response")
            return {"status": "ERROR", "error": "Failed to get response from Genie"}
            
        logger.info("Successfully got Genie response")
        return response
        
    except Exception as e:
        logger.exception(f"Error getting Genie response: {e}")
        return {"status": "ERROR", "error": str(e)}