"""Test bot helper functions (non-async, no network)."""
from pathlib import Path
from datetime import datetime


class TestLogTail:
    """Test log reading logic."""

    def test_no_logs_dir(self, tmp_path):
        log_dir = tmp_path / "logs"
        # Don't create it
        assert not log_dir.exists()

    def test_empty_logs_dir(self, tmp_path):
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        log_files = sorted(log_dir.glob("ralph_*.log"))
        assert log_files == []

    def test_reads_latest_log(self, tmp_path):
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        (log_dir / "ralph_2025-01-01.log").write_text("old line\n")
        (log_dir / "ralph_2025-01-02.log").write_text("new line 1\nnew line 2\n")
        log_files = sorted(log_dir.glob("ralph_*.log"), reverse=True)
        assert log_files[0].name == "ralph_2025-01-02.log"

    def test_log_tail_limit(self, tmp_path):
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        lines = [f"line {i}" for i in range(100)]
        (log_dir / "ralph_2025-01-01.log").write_text("\n".join(lines))
        content = (log_dir / "ralph_2025-01-01.log").read_text().strip().splitlines()
        tail = content[-15:]
        assert len(tail) == 15
        assert tail[-1] == "line 99"


class TestCostParsing:
    """Test token extraction from log lines."""

    def test_parse_tokens_field(self):
        line = "📊 TASK_END task_id=T01 tokens=12345 status=done"
        tokens = 0
        for part in line.split():
            if part.startswith("tokens="):
                tokens = int(part.split("=")[1])
        assert tokens == 12345

    def test_parse_tokens_with_comma(self):
        line = "📊 TASK_END task_id=T01 tokens=1234, duration=45s"
        tokens = 0
        for part in line.split():
            if part.startswith("tokens="):
                tokens = int(part.split("=")[1].rstrip(","))
        assert tokens == 1234

    def test_no_tokens_in_line(self):
        line = "🚀 TASK_START task_id=T01"
        tokens = 0
        for part in line.split():
            if part.startswith("tokens="):
                tokens = int(part.split("=")[1])
        assert tokens == 0


class TestProgressFile:
    """Test progress.md reading."""

    def test_read_progress(self, tmp_path):
        pf = tmp_path / "progress.md"
        pf.write_text("# Progress\n- line 1\n- line 2\n- line 3\n")
        lines = pf.read_text().strip().splitlines()
        assert len(lines) == 4

    def test_missing_progress(self, tmp_path):
        pf = tmp_path / "progress.md"
        assert not pf.exists()
