"""Append-only Log — Layer 0.

Local append-only ledger of all ExecutionRecords. Every skill execution
is recorded here before optional batch settlement to the Base chain.

The log is append-only by construction: records are never modified or
deleted after being written (I3 invariant).
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

DEFAULT_LOG_DIR = Path.home() / ".aims" / "ledger"


@dataclass
class ExecutionRecord:
    """A single skill execution record, persisted in the append-only log."""

    record_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    skill_id: str = ""
    input_hash: str = ""
    output_hash: str = ""
    duration_ms: float = 0.0
    status: str = "success"  # success | error
    points_delta: int = 0
    timestamp: float = field(default_factory=time.time)


class AppendOnlyLog:
    """Append-only log backed by a local JSONL file."""

    def __init__(self, log_dir: Path = DEFAULT_LOG_DIR) -> None:
        self._log_dir = log_dir
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._log_file = self._log_dir / f"ledger-{time.strftime('%Y%m%d')}.jsonl"
        self._buffer: List[ExecutionRecord] = []

    def append(self, record: ExecutionRecord) -> str:
        """Write a record to the buffer (does not flush immediately).

        Returns the record_id for traceability.
        """
        self._buffer.append(record)
        return record.record_id

    def flush(self) -> int:
        """Flush buffered records to disk. Returns count written."""
        if not self._buffer:
            return 0
        lines = [json.dumps(asdict(r), sort_keys=True) + "\n" for r in self._buffer]
        with open(self._log_file, "a", encoding="utf-8") as f:
            f.writelines(lines)
        count = len(self._buffer)
        self._buffer.clear()
        return count

    def query(
        self,
        skill_id: Optional[str] = None,
        since: Optional[float] = None,
        limit: int = 100,
    ) -> List[ExecutionRecord]:
        """Read records from the log file(s) with optional filtering."""
        results: List[ExecutionRecord] = []
        for log_file in sorted(self._log_dir.glob("ledger-*.jsonl")):
            with open(log_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    data = json.loads(line)
                    rec = ExecutionRecord(**data)
                    if skill_id and rec.skill_id != skill_id:
                        continue
                    if since and rec.timestamp < since:
                        continue
                    results.append(rec)
                    if len(results) >= limit:
                        return results
        return results

    @property
    def pending_count(self) -> int:
        return len(self._buffer)
