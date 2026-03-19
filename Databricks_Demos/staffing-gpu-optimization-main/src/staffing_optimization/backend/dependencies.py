from databricks.sdk import WorkspaceClient
from fastapi import Header
from typing import Annotated, Optional

from .logger import logger


def get_obo_ws(
    token: Annotated[str | None, Header(alias="X-Forwarded-Access-Token")] = None,
) -> WorkspaceClient:
    """
    Returns a Databricks Workspace client with authentication behalf of user.
    If the request contains an X-Forwarded-Access-Token header, on behalf of user authentication is used.

    Example usage:
    @api.get("/items/")
    async def read_items(obo_ws: Annotated[WorkspaceClient, Depends(get_obo_ws)]):
        # do something with the obo_ws
        ...
    """

    if not token:
        raise ValueError(
            "OBO token is not provided in the header X-Forwarded-Access-Token"
        )

    return WorkspaceClient(
        token=token, auth_type="pat"
    )  # set pat explicitly to avoid issues with SP client


def get_current_user_email(
    token: Annotated[str | None, Header(alias="X-Forwarded-Access-Token")] = None,
) -> Optional[str]:
    """Resolve the calling user's email from the OBO token.

    Returns ``None`` when no OBO token is available (e.g. local dev)
    so that downstream code can gracefully skip user-scoping.
    """
    if not token:
        return None
    try:
        ws = WorkspaceClient(token=token, auth_type="pat")
        me = ws.current_user.me()
        return me.user_name
    except Exception as e:
        logger.warning(f"Could not resolve current user from OBO token: {e}")
        return None
