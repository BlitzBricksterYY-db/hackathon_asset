from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from .config import conf
from .router import api
from .utils import add_not_found_handler
from .logger import logger
from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting app with configuration:\n{conf.model_dump_json(indent=2)}")
    
    # Initialize database
    try:
        from .database import init_db
        init_db()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.warning(f"Database initialization skipped: {e}")
        logger.info("Database will be initialized when PostgreSQL is available")
    
    yield


app = FastAPI(title=f"{conf.app_name}", lifespan=lifespan)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ui = StaticFiles(directory=conf.static_assets_path, html=True)

# note the order of includes and mounts!
app.include_router(api)
app.mount("/", ui)


add_not_found_handler(app)
