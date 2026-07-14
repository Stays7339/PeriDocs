#!/usr/bin/env python3
# ==========================================
# PeriDocs/core/database.py
# save-state 2026-07-13T11:48-04:00
# ==========================================
import os
import logging
import contextlib
from typing import AsyncGenerator
from fastapi import FastAPI
from psycopg_pool import AsyncConnectionPool
from psycopg.rows import dict_row
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Explicitly read our structural environment gatekeeper
DATABASE_MODE = os.getenv("DATABASE_MODE", "OFFLINE_MOCK").upper()

db_pool = None
ASYNC_CONN_INFO = None

# --- NEW ADDITION: EXPOSE THE COHESIVE ENGINE FACADE FOR THE DOMAIN ---
db_engine = None

# Guarded configuration setup to protect OFFLINE_MOCK mode from missing dependencies
if DATABASE_MODE in ("PRODUCTION", "SANDBOX"):
    import psycopg

    env_var = "DATABASE_URL" if DATABASE_MODE == "PRODUCTION" else "LOCAL_DATABASE_URL"
    raw_url = os.getenv(env_var)
    if not raw_url:
        raise RuntimeError(f"CRITICAL: DATABASE_MODE set to {DATABASE_MODE} but {env_var} is missing.")
    try:
        conn_params = psycopg.conninfo.conninfo_to_dict(raw_url)
        conn_params["dbname"] = "peridocs_db"
        conn_params["target_session_attrs"] = "read-write"
        ASYNC_CONN_INFO = psycopg.conninfo.make_conninfo(**conn_params)
    except Exception as e:
        raise RuntimeError(f"Failed to parse database connection parameters: {e}")


async def initialize_database():
    """Explicitly called during the app's startup sequence."""
    # Added db_engine to the global namespace allocation block
    global db_pool, db_engine
    
    if DATABASE_MODE in ("PRODUCTION", "SANDBOX"):
        from psycopg_pool import AsyncConnectionPool
        from psycopg.rows import dict_row

        logger.info(f"[Database mode: {DATABASE_MODE}] Connecting async pool to cluster...")
        db_pool = AsyncConnectionPool(
            conninfo=ASYNC_CONN_INFO,
            min_size=2,
            max_size=10,
            kwargs={"autocommit": False, "row_factory": dict_row},
            open=False
        )
        await db_pool.open()
        logger.info(f"[Database mode: {DATABASE_MODE}] Database pipeline successfully bound.")
        
        # --- NEW ADDITION: BIND THE LIVE RELATIONAL STORAGE ENGINE ---
        try:
            from database_management.storage_engines import StorageEngineFactory
            db_engine = StorageEngineFactory.get_engine(
                engine_type="POSTGRES", 
                connection_pool=db_pool
            )
            logger.debug(f"[DATABASE MODE: {DATABASE_MODE}] Storage engine facade safely bound to pool.")
        except ImportError:
            print("[WARNING] Could not import StorageEngineFactory. Verify python path mappings.")
            raise
    else:
        print("\n====================================================================")
        print(" [WARNING] APPLICATION INITIALIZING IN LOCAL OFFLINE MOCK MODE      ")
        print("====================================================================\n")
        

async def close_database():
    """Explicitly called during the app's shutdown sequence."""
    global db_pool
    if DATABASE_MODE in ("PRODUCTION", "SANDBOX"):
        logger.info(f"[Database Mode: {DATABASE_MODE}] Draining connection pool...")
        if db_pool:
            await db_pool.close()
    else:
        logger.info("[Database Mode: Local mock database lifecycle concluded.")


async def get_db() -> AsyncGenerator:
    global db_pool
    if DATABASE_MODE in ("PRODUCTION", "SANDBOX"):
        if db_pool is None:
            raise RuntimeError("Database pool is offline.")
        async with db_pool.connection() as session:
            async with session.transaction():
                yield session
    else:
        class LocalMockConnection:
            async def execute(self, query: str, params: tuple = None):
                logger.info(f"[SANDBOX LOCAL MOCK SQL] Executing statement context: {query}")
                
                class MockCursor:
                    async def fetchone(self):
                        # Gracefully returns a dummy row to satisfy health/release checks
                        return {"release_id": "LOCAL_OFFLINE_MOCK_SANDBOX", "schema_version": "v0"}
                    async def fetchall(self):
                        return []
                return MockCursor()
        yield LocalMockConnection()