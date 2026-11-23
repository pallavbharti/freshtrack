import pytest

from scripts import check_lock
from scripts.check_lock import check, normalize, pins


def make(tmp_path, req, dev, lock, dev_lock):
    (tmp_path / "requirements.txt").write_text(req)
    (tmp_path / "requirements-dev.txt").write_text(dev)
    (tmp_path / "requirements.lock").write_text(lock)
    (tmp_path / "requirements-dev.lock").write_text(dev_lock)
    return tmp_path


def test_committed_lock_files_match_pins():
    assert check() == []


def test_normalize_names():
    assert normalize("Scikit_Learn") == normalize("scikit-learn") == "scikit-learn"


def test_pins_follow_includes_and_extras(tmp_path):
    root = make(tmp_path, "uvicorn[standard]==1.0\nfastapi==2.0\n", "-r requirements.txt\npytest==3.0\n", "", "")
    assert pins(root / "requirements-dev.txt") == {"uvicorn": "1.0", "fastapi": "2.0", "pytest": "3.0"}


def test_lock_with_hashes_is_parsed(tmp_path):
    lock = "numpy==2.5.3 \\\n    --hash=sha256:abc \\\n    --hash=sha256:def\n"
    (tmp_path / "x.lock").write_text(lock)
    assert pins(tmp_path / "x.lock") == {"numpy": "2.5.3"}


def test_matching_lock_passes(tmp_path):
    root = make(tmp_path, "numpy==2.5.3\n", "-r requirements.txt\nruff==1.0\n",
                "numpy==2.5.3 \\\n    --hash=sha256:a\n", "numpy==2.5.3 \\\n    --hash=sha256:a\nruff==1.0\n")
    assert check(root) == []


def test_bumped_pin_without_new_lock_fails(tmp_path):
    root = make(tmp_path, "numpy==2.5.5\n", "-r requirements.txt\n", "numpy==2.5.3\n", "numpy==2.5.3\n")
    problems = check(root)
    assert any("numpy is 2.5.3, requirements.txt pins 2.5.5" in p for p in problems)
    assert any(p.startswith("regenerate with: uv pip compile requirements.txt") for p in problems)


def test_missing_package_in_lock_fails(tmp_path):
    root = make(tmp_path, "numpy==1.0\n", "-r requirements.txt\npytest==9.0\n", "numpy==1.0\n", "numpy==1.0\n")
    assert any("pytest is missing" in p for p in check(root))


@pytest.mark.parametrize("ok", [True, False])
def test_main_exit_code(monkeypatch, capsys, ok):
    monkeypatch.setattr(check_lock, "check", lambda: [] if ok else ["requirements.lock: x is 1, pins 2"])
    with pytest.raises(SystemExit) as e:
        check_lock.main()
    assert e.value.code == (0 if ok else 1)
    assert ("match" in capsys.readouterr().out) is ok
