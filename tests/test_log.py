"""Tests for Append-only Log and Merkle tree."""
import json
import tempfile
from pathlib import Path

from src.ledger.log import AppendOnlyLog, ExecutionRecord
from src.ledger.merkle import compute_root, hash_record


class TestAppendOnlyLog:
    def test_append_returns_id(self):
        log = AppendOnlyLog(log_dir=Path(tempfile.mkdtemp()))
        rec = ExecutionRecord(skill_id="test", status="success")
        rid = log.append(rec)
        assert rid == rec.record_id
        assert log.pending_count == 1

    def test_flush_writes_to_disk(self):
        log_dir = Path(tempfile.mkdtemp())
        log = AppendOnlyLog(log_dir=log_dir)
        rec = ExecutionRecord(skill_id="flush_test", status="success")
        log.append(rec)
        count = log.flush()
        assert count == 1
        assert log.pending_count == 0

        # Verify on disk
        log_files = list(log_dir.glob("ledger-*.jsonl"))
        assert len(log_files) >= 1

    def test_flush_empty(self):
        log = AppendOnlyLog(log_dir=Path(tempfile.mkdtemp()))
        assert log.flush() == 0

    def test_query_by_skill_id(self):
        log_dir = Path(tempfile.mkdtemp())
        log = AppendOnlyLog(log_dir=log_dir)
        rec1 = ExecutionRecord(skill_id="skill_a", status="success")
        rec2 = ExecutionRecord(skill_id="skill_b", status="success")
        log.append(rec1)
        log.append(rec2)
        log.flush()

        # Re-read via query
        results = log.query(skill_id="skill_a")
        assert len(results) >= 1
        assert results[0].skill_id == "skill_a"

    def test_query_limit(self):
        log_dir = Path(tempfile.mkdtemp())
        log = AppendOnlyLog(log_dir=log_dir)
        for i in range(5):
            log.append(ExecutionRecord(skill_id="limit_test", status="success"))
        log.flush()

        results = log.query(limit=2)
        assert len(results) == 2

    def test_record_has_timestamp(self):
        rec = ExecutionRecord(skill_id="ts_test", status="success")
        assert rec.timestamp > 0

    def test_record_fields(self):
        rec = ExecutionRecord(
            skill_id="fields_test",
            input_hash="abc",
            output_hash="def",
            duration_ms=100.0,
            status="error",
            points_delta=5,
        )
        assert rec.skill_id == "fields_test"
        assert rec.status == "error"
        assert rec.points_delta == 5
        assert rec.duration_ms == 100.0


class TestMerkleTree:
    def test_empty_list(self):
        assert compute_root([]) == b""

    def test_single_record(self):
        rec = ExecutionRecord(skill_id="single", status="success")
        root = compute_root([rec])
        assert len(root) == 32  # SHA-256

    def test_multiple_records(self):
        recs = [
            ExecutionRecord(skill_id="a", status="success"),
            ExecutionRecord(skill_id="b", status="error"),
        ]
        root = compute_root(recs)
        assert len(root) == 32

    def test_deterministic(self):
        recs = [
            ExecutionRecord(skill_id="det", status="success"),
            ExecutionRecord(skill_id="det2", status="success"),
        ]
        root1 = compute_root(recs)
        root2 = compute_root(recs)
        assert root1 == root2

    def test_hash_record_is_bytes(self):
        rec = ExecutionRecord(skill_id="hash_test", status="success")
        h = hash_record(rec)
        assert isinstance(h, bytes)
        assert len(h) == 32
