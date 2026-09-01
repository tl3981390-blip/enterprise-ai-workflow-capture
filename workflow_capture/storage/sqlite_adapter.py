"""LOCAL_SQLITE storage adapter — the reference implementation.

Used for local tests, single-user personal capture, and as the executable
specification of the Storage Adapter Contract.
"""

from .. import database
from . import KIND_LOCAL_SQLITE, StorageAdapter


class SQLiteAdapter(StorageAdapter):
    kind = KIND_LOCAL_SQLITE

    def __init__(self, db_path):
        self.db_path = str(db_path)

    def _connected(self, fn):
        connection = database.connect(self.db_path)
        try:
            return fn(connection)
        finally:
            connection.close()

    def health(self):
        def check(connection):
            version = database.migrate(connection)
            return {
                "adapter": self.kind,
                "database": self.db_path,
                "schema_version": version,
                "foreign_keys": bool(connection.execute("PRAGMA foreign_keys").fetchone()[0]),
                "integrity_check": connection.execute("PRAGMA integrity_check").fetchone()[0],
            }

        return self._connected(check)

    def ensure_schema(self):
        return self._connected(database.migrate)

    def create_confirmation(self, payload):
        return self._connected(lambda connection: database.create_confirmation(connection, payload))

    def read_confirmation(self, confirmation_id):
        return self._connected(lambda connection: database.read_confirmation(connection, confirmation_id))

    def confirm_confirmation(self, confirmation_id, expected_payload_hash, method, identity=None, source=None):
        return self._connected(
            lambda connection: database.confirm_confirmation(
                connection, confirmation_id, expected_payload_hash, method, identity=identity, source=source
            )
        )

    def persist_confirmed(self, confirmation_id, expected_payload_hash):
        return self._connected(
            lambda connection: database.persist_confirmed(connection, confirmation_id, expected_payload_hash)
        )

    def persist_authorized(self, payload, authorization_record):
        return self._connected(
            lambda connection: database.persist_authorized(connection, payload, authorization_record)
        )

    def read_task(self, task_id):
        return self._connected(lambda connection: database.read_task(connection, task_id))

    def similar_tasks(self, task_type, limit=10):
        return self._connected(lambda connection: database.similar_tasks(connection, task_type, limit))

    def verify_evidence_chains(self):
        return self._connected(database.verify_evidence_chains)
