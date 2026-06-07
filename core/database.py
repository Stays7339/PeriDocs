#!/usr/bin/env python3
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

# ============================================================================
#                           REMOTE PRODUCTION HOOKS
# ============================================================================
if DATABASE_MODE == "PRODUCTION":
    from psycopg_pool import AsyncConnectionPool
    from psycopg.rows import dict_row
    import psycopg

    DATABASE_URL = os.getenv("DATABASE_URL")
    if not DATABASE_URL:
        raise RuntimeError("CRITICAL: DATABASE_MODE set to PRODUCTION but DATABASE_URL is missing.")

    try:
        conn_params = psycopg.conninfo.conninfo_to_dict(DATABASE_URL)
        conn_params["dbname"] = "peridocs_db"
        conn_params["target_session_attrs"] = "read-write"
        ASYNC_CONN_INFO = psycopg.conninfo.make_conninfo(**conn_params)
    except Exception as e:
        raise RuntimeError(f"Failed to parse production connection parameters: {e}")

    db_pool: AsyncConnectionPool | None = None

    @contextlib.asynccontextmanager
    async def database_lifespan(app: FastAPI):
        global db_pool
        print("[STARTUP] [PRODUCTION] Connecting async pool to Hetzner cloud cluster...")
        db_pool = AsyncConnectionPool(
            conninfo=ASYNC_CONN_INFO,
            min_size=2,
            max_size=10,
            kwargs={"autocommit": False, "row_factory": dict_row},
            open=False
        )
        await db_pool.open()
        print("[STARTUP] [PRODUCTION] Remote database pipeline successfully bound.")
        yield
        print("[SHUTDOWN] [PRODUCTION] Draining connection pool...")
        if db_pool:
            await db_pool.close()

    async def get_db() -> AsyncGenerator[psycopg.AsyncConnection, None]:
        global db_pool
        if db_pool is None:
            raise RuntimeError("Database pool is offline.")
        async with db_pool.connection() as session:
            async with session.transaction():
                yield session

elif DATABASE_MODE == "LOCAL":
    from psycopg_pool import AsyncConnectionPool
    from psycopg.rows import dict_row
    import psycopg

    DATABASE_URL = os.getenv("LOCAL_DATABASE_URL")
    if not DATABASE_URL:
        raise RuntimeError("CRITICAL: DATABASE_MODE set to LOCAL but LOCAL_DATABASE_URL is missing.")

    try:
        conn_params = psycopg.conninfo.conninfo_to_dict(DATABASE_URL)
        conn_params["dbname"] = "peridocs_db"
        conn_params["target_session_attrs"] = "read-write"
        ASYNC_CONN_INFO = psycopg.conninfo.make_conninfo(**conn_params)
    except Exception as e:
        raise RuntimeError(f"Failed to parse production connection parameters: {e}")

    db_pool: AsyncConnectionPool | None = None

    @contextlib.asynccontextmanager
    async def database_lifespan(app: FastAPI):
        global db_pool
        print("[STARTUP] [LOCAL] Connecting async pool to local cluster...")
        db_pool = AsyncConnectionPool(
            conninfo=ASYNC_CONN_INFO,
            min_size=2,
            max_size=10,
            kwargs={"autocommit": False, "row_factory": dict_row},
            open=False
        )
        await db_pool.open()
        print("[STARTUP] [LOCAL] Local database pipeline successfully bound.")
        yield
        print("[SHUTDOWN] [LOCAL] Draining connection pool...")
        if db_pool:
            await db_pool.close()

    async def get_db() -> AsyncGenerator[psycopg.AsyncConnection, None]:
        global db_pool
        if db_pool is None:
            raise RuntimeError("Database pool is offline.")
        async with db_pool.connection() as session:
            async with session.transaction():
                yield session

# ============================================================================
#                              LOCAL OR OFFLINE MODE 
# ============================================================================
else:    
    @contextlib.asynccontextmanager
    async def database_lifespan(app: FastAPI):
        print("\n====================================================================")
        print(" [WARNING] APPLICATION INITIALIZING IN LOCAL OFFLINE MOCK MODE      ")
        print("====================================================================\n")
        yield
        print("[SHUTDOWN] Local mock database lifecycle concluded.")

    async def get_db() -> AsyncGenerator[any, None]:
        """
        Yields a dynamic adapter object so Ember's local route endpoints
        can safely call 'await db.execute()' without throwing Python exceptions.
        """
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

# DATABASE_URL = os.getenv("DATABASE_URL")

# if not DATABASE_URL:
#     raise RuntimeError("CRITICAL: DATABASE_URL variable missing from environment configuration.")

# try:
#     import psycopg
#     conn_params = psycopg.conninfo.conninfo_to_dict(DATABASE_URL)
#     conn_params["dbname"] = "peridocs_db"
#     conn_params["target_session_attrs"] = "read-write"
#     ASYNC_CONN_INFO = psycopg.conninfo.make_conninfo(**conn_params)
# except Exception as e:
#     raise RuntimeError(f"Failed to cryptographically parse connection parameters: {e}")

# db_pool: AsyncConnectionPool | None = None

# @contextlib.asynccontextmanager
# async def database_lifespan(app: FastAPI):
#     """
#     Handles the asynchronous database connection pool initialization 
#     and systemic teardown safely within the root core namespace.
#     """
#     global db_pool
#     print("[STARTUP] Initializing async connection pool under root core/ namespace...")
#     db_pool = AsyncConnectionPool(
#         conninfo=ASYNC_CONN_INFO,
#         min_size=2,
#         max_size=10,
#         kwargs={"autocommit": False, "row_factory": dict_row},
#         open=False
#     )
#     await db_pool.open()
#     print("[STARTUP] Remote database connection pool verified active and bound.")
    
#     yield # System execution transition boundary
    
#     print("[SHUTDOWN] Draining active transaction pipelines and terminating pool...")
#     if db_pool:
#         await db_pool.close()
#     print("[SHUTDOWN] Database pool closed cleanly.")

# async def get_db() -> AsyncGenerator[psycopg.AsyncConnection, None]:
#     """
#     FastAPI Dependency Injector. Yields a secure, isolated transaction connection.
#     """
#     global db_pool
#     if db_pool is None:
#         raise RuntimeError("Core database connection pool is offline.")
#     async with db_pool.connection() as session:
#         async with session.transaction():
#             yield session
