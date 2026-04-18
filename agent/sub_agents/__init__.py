"""Per–database-type labels (fork README parity); execution stays unified in ``OracleForgePipeline``."""

from .duckdb_agent import DATABASE_KEY as DUCKDB_KEY
from .mongo_agent import DATABASE_KEY as MONGODB_KEY
from .postgres_agent import DATABASE_KEY as POSTGRES_KEY
from .sqlite_agent import DATABASE_KEY as SQLITE_KEY

SUB_AGENT_DATABASE_KEYS = (POSTGRES_KEY, MONGODB_KEY, SQLITE_KEY, DUCKDB_KEY)

__all__ = [
    "DUCKDB_KEY",
    "MONGODB_KEY",
    "POSTGRES_KEY",
    "SQLITE_KEY",
    "SUB_AGENT_DATABASE_KEYS",
]
