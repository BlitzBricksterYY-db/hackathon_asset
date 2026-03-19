import os
import requests
from dotenv import load_dotenv

# Function to get dashboard embedding OAuth token
def get_dashboard_embedding_oauth_token(external_data, external_viewer_id, dashboard_name):
    # Pull Environment Variables from .env file
    load_dotenv()

    databricks_host = os.environ['DATABRICKS_HOST']
    databricks_client_id = os.environ['DATABRICKS_CLIENT_ID']
    databricks_client_secret = os.environ['DATABRICKS_CLIENT_SECRET']
    if dashboard_name == "defects":
        dashboard_id = os.environ['DATABRICKS_DASHBOARD_ID']

    # Updated OAuth scopes to include SQL and data table permissions
    oauth_scopes = "dashboards.query-execution dashboards.lakeview-embedded:read sql.redash-config:read settings:read sql:read sql:write sql.analytics:read sql.dashboards:read"
    custom_claim = f'urn:aibi:external_data:{external_data}:{external_viewer_id}:{dashboard_id}'

    # Make M2M OAuth Request to Databricks server to get a Databricks Access Token
    token_url = f"https://{databricks_host}/oidc/v1/token"

    payload = {
        "grant_type": "client_credentials",
        "client_id": databricks_client_id,
        "client_secret": databricks_client_secret,
        "scope": oauth_scopes,
        # This custom claim will be used to filter data in the SQL statement
        "custom_claim": custom_claim
    }

    response = requests.post(token_url, data=payload)

    # No need to worry about token expiration, since the dashboard embedding library will automatically reissue expired tokens
    token_data = response.json()

    # Store the access token and its expiration time
    access_token = token_data["access_token"]

    return access_token
