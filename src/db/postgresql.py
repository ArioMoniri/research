"""postgresql adapter: registered, not yet implemented."""
from .base import NotImplementedAdapter


class PostgresqlAdapter(NotImplementedAdapter):
    engine = "postgresql"
