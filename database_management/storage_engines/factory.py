# database_management/storage_engines/factory.py
from .postgres_engine import PostgresStorageEngine

class StorageEngineFactory:
    @classmethod
    def get_engine(cls, engine_type: str, **kwargs):
        engine_type = engine_type.upper()
        if engine_type == "POSTGRES":
            pool = kwargs.get("connection_pool")
            if not pool:
                raise ValueError("Postgres storage engine requires an active 'connection_pool'.")
            return PostgresStorageEngine(pool)
        elif engine_type == "FLAT_FILE":
            class FlatFileMockEngine:
                async def save_ledger_bundle(self, state): pass
                async def save_entries_bundle(self, *args, **kwargs): pass
            return FlatFileMockEngine()
        else:
            raise ValueError(f"Unknown storage engine target: {engine_type}")