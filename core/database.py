#!/usr/bin/env python3
import os
import contextlib
from typing import AsyncGenerator
from fastapi import FastAPI
from psycopg_pool import AsyncConnectionPool
from psycopg.rows import dict_row
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("CRITICAL: DATABASE_URL variable missing from environment configuration.")

try:
    import psycopg
    conn_params = psycopg.conninfo.conninfo_to_dict(DATABASE_URL)
    conn_params["dbname"] = "peridocs_db"
    conn_params["target_session_attrs"] = "read-write"
    ASYNC_CONN_INFO = psycopg.conninfo.make_conninfo(**conn_params)
except Exception as e:
    raise RuntimeError(f"Failed to cryptographically parse connection parameters: {e}")

db_pool: AsyncConnectionPool | None = None

@contextlib.asynccontextmanager
async def database_lifespan(app: FastAPI):
    """
    Handles the asynchronous database connection pool initialization 
    and systemic teardown safely within the root core namespace.
    """
    global db_pool
    print("[STARTUP] Initializing async connection pool under root core/ namespace...")
    db_pool = AsyncConnectionPool(
        conninfo=ASYNC_CONN_INFO,
        min_size=2,
        max_size=10,
        kwargs={"autocommit": False, "row_factory": dict_row},
        open=False
    )
    await db_pool.open()
    print("[STARTUP] Remote database connection pool verified active and bound.")
    
    yield # System execution transition boundary
    
    print("[SHUTDOWN] Draining active transaction pipelines and terminating pool...")
    if db_pool:
        await db_pool.close()
    print("[SHUTDOWN] Database pool closed cleanly.")

async def get_db() -> AsyncGenerator[psycopg.AsyncConnection, None]:
    """
    FastAPI Dependency Injector. Yields a secure, isolated transaction connection.
    """
    global db_pool
    if db_pool is None:
        raise RuntimeError("Core database connection pool is offline.")
    async with db_pool.connection() as session:
        async with session.transaction():
            yield session