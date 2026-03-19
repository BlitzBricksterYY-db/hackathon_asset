import os
import os.path
from pathlib import Path

import uvicorn
from databricks.sdk.core import Config
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.responses import RedirectResponse, FileResponse

cfg = Config()
token = cfg.authenticate()["Authorization"].split(" ")[1]
host = f"https://{os.environ['DATABRICKS_HOST']}"

app = FastAPI(title="UHG - Workforce Management")

app.mount("/admin/static", StaticFiles(directory=f"./build/static/"), name="static")

@app.get("/admin/{full_path:path}")
async def serve_react_app(full_path: str):
    return FileResponse("./build/index.html")

@app.get("/")
async def root():
    response = RedirectResponse(url=f"{os.environ['DATABRICKS_APP_URL']}/admin/")
    response.set_cookie(key="genie_dbapp_url", value=os.environ.get('GENIE_DBAPP_URL'))
    return response

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0")
