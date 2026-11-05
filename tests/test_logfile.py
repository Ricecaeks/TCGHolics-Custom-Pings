import logging
import os
import time

from tcgpings.logfile import file_handler


def _record(msg: str, created: float | None = None) -> logging.LogRecord:
    record = logging.LogRecord("t", logging.INFO, __file__, 1, msg, None, None)
    if created is not None:
        record.created = created
    return record


def _files(path) -> list[str]:
    return sorted(os.listdir(path))


def test_rolls_over_at_size_and_keeps_only_the_newest(tmp_path):
    handler = file_handler(str(tmp_path / "logs"), max_mb=1, keep=2, node_name="nuc1")
    handler.maxBytes = 200  # bytes, to keep the test small
    for i in range(20):
        handler.emit(_record(f"line {i} " + "x" * 50))
    handler.close()
    assert _files(tmp_path / "logs") == ["bot-nuc1.log", "bot-nuc1.log.1", "bot-nuc1.log.2"]
    assert all(os.path.getsize(tmp_path / "logs" / f) <= 200 for f in _files(tmp_path / "logs"))
    assert "line 19" in (tmp_path / "logs" / "bot-nuc1.log").read_text()


def test_starts_a_new_file_each_day(tmp_path):
    handler = file_handler(str(tmp_path), max_mb=25, keep=7, node_name="nuc1")
    handler.emit(_record("today"))
    handler.emit(_record("tomorrow", created=time.time() + 86400))
    handler.close()
    assert (tmp_path / "bot-nuc1.log.1").read_text().strip().endswith("today")
    assert (tmp_path / "bot-nuc1.log").read_text().strip().endswith("tomorrow")


def test_file_left_from_an_earlier_day_rolls_on_first_line(tmp_path):
    old = tmp_path / "bot-nuc1.log"
    old.write_text("yesterday\n")
    two_days_ago = time.time() - 2 * 86400
    os.utime(old, (two_days_ago, two_days_ago))
    handler = file_handler(str(tmp_path), max_mb=25, keep=7, node_name="nuc1")
    handler.emit(_record("now"))
    handler.close()
    assert (tmp_path / "bot-nuc1.log.1").read_text() == "yesterday\n"
    assert (tmp_path / "bot-nuc1.log").read_text().strip() == "now"
