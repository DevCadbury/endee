# =============================================================================
# main.py — FastAPI Application Entry Point
# =============================================================================
# Sets up the FastAPI app with:
# - Lifespan events (startup/shutdown for DB, Redis, Endee, Embeddings)
# - CORS middleware for frontend + widget origins
# - All API routers mounted under /api/v1/
# =============================================================================

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.config import get_settings
from services.mongo import connect_db, close_db
from services.redis_cache import connect_redis, close_redis
from services.embedding import embedding_service
from services.endee_client import endee_client
from api.auth import router as auth_router
from api.kb import router as kb_router
from api.chat import router as chat_router
from api.dashboard import router as dashboard_router
from api.admin import router as admin_router
from api.widget import router as widget_router
from api.conversations import router as conversations_router
from api.superadmin import router as superadmin_router
from api.ws import router as ws_router

# --- Configure Logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# =============================================================================
# Application Lifespan (Startup & Shutdown)
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manages application lifecycle:
    
    Startup:
        1. Connect to MongoDB and create indexes
        2. Connect to Redis
        3. Load the embedding model into memory (singleton)
        4. Ensure Endee vector index exists
    
    Shutdown:
        1. Close MongoDB connection
        2. Close Redis connection
    """
    settings = get_settings()

    # --- Startup ---
    logger.info("=" * 60)
    logger.info("AI Customer Support Platform — Starting Up")
    logger.info("=" * 60)

    # 1. MongoDB
    await connect_db()

    # 2. Redis
    await connect_redis()

    # 3. Embedding Model (loaded into memory once)
    embedding_service.load_model()

    # 4. Endee Index
    try:
        endee_client.ensure_index(
            name=settings.ENDEE_INDEX_NAME,
            dimension=384,  # bge-small output dimension
        )
    except Exception as e:
        logger.warning(
            f"Could not connect to Endee at startup: {e}. "
            f"Will retry on first request."
        )

    logger.info("=" * 60)
    logger.info("All services initialized — Server ready")
    logger.info("=" * 60)

    yield  # Application runs here

    # --- Shutdown ---
    logger.info("Shutting down services...")
    await close_db()
    await close_redis()
    logger.info("Shutdown complete.")


# =============================================================================
# FastAPI Application
# =============================================================================

app = FastAPI(
    title="ResolveAI — AI Customer Support Platform",
    description=(
        "Multi-tenant AI customer support automation with RBAC. "
        "Roles: SuperAdmin > Admin > Staff > Customer. "
        "Auto-resolves repeatable issues via RAG, escalates to staff, "
        "and continuously learns from every human resolution."
    ),
    version="2.0.0",
    lifespan=lifespan,
)


# =============================================================================
# CORS Middleware
# =============================================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # Widget is embeddable on any site; JWT goes in headers, not cookies
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)


# =============================================================================
# Router Inclusions
# =============================================================================

app.include_router(auth_router)
app.include_router(kb_router)
app.include_router(chat_router)
app.include_router(dashboard_router)
app.include_router(admin_router)
app.include_router(widget_router)
app.include_router(conversations_router)
app.include_router(superadmin_router)
app.include_router(ws_router)


# =============================================================================
# Health Check
# =============================================================================

@app.get("/health", tags=["Health"])
async def health_check():
    """
    Health check endpoint. Returns service status.
    Use this to verify the server is running.
    """
    return {
        "status": "healthy",
        "service": "ResolveAI — AI Customer Support Platform",
        "version": "2.0.0",
    }


@app.get("/", tags=["Root"])
async def root():
    """Root endpoint — redirects to docs."""
    return {
        "message": "AI Customer Support Platform API",
        "docs": "/docs",
        "health": "/health",
    }
