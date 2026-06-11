#!/usr/bin/env python3
# ==========================================
# PeriDocs/core/database.py
# save-state 2026-06-11T13:02-04:00
# ==========================================
import os
import contextlib
from typing import AsyncGenerator
from fastapi import FastAPI
from psycopg_pool import AsyncConnectionPool
from psycopg.rows import dict_row
from dotenv import load_dotenv

load_dotenv()

# Explicitly read our structural environment gatekeeper
DATABASE_MODE = os.getenv("DATABASE_MODE", "OFFLINE_MOCK").upper()

db_pool = None
ASYNC_CONN_INFO = None

# Guarded configuration setup to protect OFFLINE_MOCK mode from missing dependencies
if DATABASE_MODE in ("PRODUCTION", "LOCAL"):
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
    global db_pool
    
    if DATABASE_MODE in ("PRODUCTION", "LOCAL"):
        from psycopg_pool import AsyncConnectionPool
        from psycopg.rows import dict_row

        print(f"[STARTUP] [{DATABASE_MODE}] Connecting async pool to cluster...")
        db_pool = AsyncConnectionPool(
            conninfo=ASYNC_CONN_INFO,
            min_size=2,
            max_size=10,
            kwargs={"autocommit": False, "row_factory": dict_row},
            open=False
        )
        await db_pool.open()
        print(f"[STARTUP] [{DATABASE_MODE}] Database pipeline successfully bound.")
    else:
        print("\n====================================================================")
        print(" [WARNING] APPLICATION INITIALIZING IN LOCAL OFFLINE MOCK MODE      ")
        print("====================================================================\n")


async def close_database():
    """Explicitly called during the app's shutdown sequence."""
    global db_pool
    if DATABASE_MODE in ("PRODUCTION", "LOCAL"):
        print(f"[SHUTDOWN] [{DATABASE_MODE}] Draining connection pool...")
        if db_pool:
            await db_pool.close()
    else:
        print("[SHUTDOWN] Local mock database lifecycle concluded.")


async def get_db() -> AsyncGenerator:
    global db_pool
    if DATABASE_MODE in ("PRODUCTION", "LOCAL"):
        if db_pool is None:
            raise RuntimeError("Database pool is offline.")
        async with db_pool.connection() as session:
            async with session.transaction():
                yield session
    else:
        class LocalMockConnection:
            async def execute(self, query: str, params: tuple = None):
                print(f"[LOCAL MOCK SQL] Executing statement context: {query}")
                
                class MockCursor:
                    async def fetchone(self):
                        # Gracefully returns a dummy row to satisfy health/release checks
                        return {"release_id": "LOCAL_OFFLINE_MOCK_SANDBOX", "schema_version": "v0"}
                    async def fetchall(self):
                        return []
                return MockCursor()
        yield LocalMockConnection()