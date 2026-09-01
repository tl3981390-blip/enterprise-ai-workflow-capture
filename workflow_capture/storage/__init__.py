"""Storage Adapter Contract.

The skill never hard-codes a single storage backend. `LOCAL_SQLITE` is the
reference implementation for local tests and single-user personal use. An
enterprise deploys its own adapter module (e.g. backed by PostgreSQL, an
internal API, or an approved database service) and points the runtime at it
through the environment:

- ``WORKFLOW_CAPTURE_STORAGE`` — ``local_sqlite`` (default) or ``enterprise_adapter``.
- ``WORKFLOW_CAPTURE_STORAGE_ADAPTER_MODULE`` — dotted module path or a ``.py``
  file path of the enterprise-supplied adapter (enterprise_adapter only).
  The module must expose ``create_adapter()`` returning an object that
  implements the adapter contract below. Credentials for enterprise storage
  are read by that module from its own environment or key service — never
  from this repository, a candidate payload, or a CLI flag.

Contract methods (see references/storage-adapter-contract.md for the full
specification): health, ensure_schema, create_confirmation, read_confirmation,
confirm_confirmation, persist_confirmed, persist_authorized, read_task,
similar_tasks, verify_evidence_chains.
"""

import importlib
import importlib.util
import os
from abc import ABC, abstractmethod
from pathlib import Path

from ..errors import CaptureError, StorageError

ENV_STORAGE_KIND = "WORKFLOW_CAPTURE_STORAGE"
ENV_ADAPTER_MODULE = "WORKFLOW_CAPTURE_STORAGE_ADAPTER_MODULE"
ENV_LOCAL_DB = "WORKFLOW_CAPTURE_DB"

KIND_LOCAL_SQLITE = "local_sqlite"
KIND_ENTERPRISE = "enterprise_adapter"

DEFAULT_LOCAL_DB = str(Path(".workflow-capture") / "workflows.db")

CONTRACT_METHODS = (
    "health",
    "ensure_schema",
    "create_confirmation",
    "read_confirmation",
    "confirm_confirmation",
    "persist_confirmed",
    "persist_authorized",
    "read_task",
    "similar_tasks",
    "verify_evidence_chains",
)


class StorageAdapter(ABC):
    """Persistence boundary every storage backend must implement."""

    kind = "unknown"

    @abstractmethod
    def health(self):
        """Return a dict describing adapter health; never raises raw driver errors."""

    @abstractmethod
    def ensure_schema(self):
        """Migrate to the supported schema; returns the schema version."""

    @abstractmethod
    def create_confirmation(self, payload):
        """Store a PREPARED confirmation intent; returns (confirmation_id, payload_hash, prepared_at)."""

    @abstractmethod
    def read_confirmation(self, confirmation_id):
        """Return the confirmation row as a dict, or None."""

    @abstractmethod
    def confirm_confirmation(self, confirmation_id, expected_payload_hash, method, identity=None, source=None):
        """Atomically transition PREPARED → CONFIRMED for the exact payload hash."""

    @abstractmethod
    def persist_confirmed(self, confirmation_id, expected_payload_hash):
        """Atomically consume a CONFIRMED intent and insert the task; returns (task_id, duplicate)."""

    @abstractmethod
    def persist_authorized(self, payload, authorization_record):
        """Idempotently persist an enterprise-managed capture.

        Returns {"task_id", "duplicate", "payload_hash"}. The same
        capture_session_id must never create a second task; the same session id
        with a different payload must be refused.
        """

    @abstractmethod
    def read_task(self, task_id):
        """Return the stored task record (including payload), or None."""

    @abstractmethod
    def similar_tasks(self, task_type, limit=10):
        """Return candidate matches by normalized task type (not semantic truth)."""

    @abstractmethod
    def verify_evidence_chains(self):
        """Mechanically recompute evidence chains; returns a status dict."""


def _load_enterprise_module(module_ref):
    path_candidate = Path(module_ref)
    if module_ref.endswith(".py") or path_candidate.exists():
        if not path_candidate.is_file():
            raise StorageError(f"enterprise storage adapter module not found: {module_ref}")
        spec = importlib.util.spec_from_file_location("enterprise_storage_adapter", path_candidate)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    return importlib.import_module(module_ref)


def check_contract(adapter):
    """Mechanical contract check: required methods exist and kind is declared."""
    missing = [name for name in CONTRACT_METHODS if not callable(getattr(adapter, name, None))]
    if missing:
        raise StorageError(f"storage adapter does not implement the contract methods: {', '.join(missing)}")
    kind = getattr(adapter, "kind", None)
    if not isinstance(kind, str) or not kind.strip() or kind == "unknown":
        raise StorageError("storage adapter must declare a non-empty 'kind'")
    return adapter


def resolve_adapter(db_path=None, env=None):
    """Resolve the storage adapter. An explicit db_path always means LOCAL_SQLITE;
    otherwise the environment decides. Fail closed on misconfiguration."""
    from .sqlite_adapter import SQLiteAdapter

    env = os.environ if env is None else env
    if db_path:
        return SQLiteAdapter(db_path)
    kind = env.get(ENV_STORAGE_KIND, KIND_LOCAL_SQLITE).strip()
    if kind == KIND_LOCAL_SQLITE:
        return SQLiteAdapter(env.get(ENV_LOCAL_DB, DEFAULT_LOCAL_DB))
    if kind == KIND_ENTERPRISE:
        module_ref = env.get(ENV_ADAPTER_MODULE)
        if not module_ref or not module_ref.strip():
            raise StorageError(
                f"{KIND_ENTERPRISE} storage is selected but {ENV_ADAPTER_MODULE} is not configured"
            )
        try:
            module = _load_enterprise_module(module_ref.strip())
        except StorageError:
            raise
        except Exception as exc:
            raise StorageError(f"enterprise storage adapter could not be loaded ({exc.__class__.__name__})")
        create_adapter = getattr(module, "create_adapter", None)
        if not callable(create_adapter):
            raise StorageError("enterprise storage adapter module must expose create_adapter()")
        try:
            adapter = create_adapter()
        except Exception as exc:
            raise StorageError(f"enterprise storage adapter initialization failed ({exc.__class__.__name__})")
        return check_contract(adapter)
    raise CaptureError(f"unknown storage kind: {kind}")
