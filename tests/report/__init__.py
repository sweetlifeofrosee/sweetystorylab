"""
Tests for scripts/report/ (the Weekly Performance Report module).

Minimal, regression-focused coverage per the module's own design
constraints: repository-first, honest about missing data, and derived
from real git history rather than fabricated timestamps. Several tests
build a real throwaway git repo under tmp_path (see conftest.py's
git_repo fixture) rather than mocking git, because the module's core
value -- and the one real bug found while building it (git log
--since/--until silently under-counting on out-of-order commit dates,
see test_git_history.py) -- only shows up against real git behavior.
"""
