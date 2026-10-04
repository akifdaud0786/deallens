"""Dependency rules from docs/codebase-design.md §3, enforced by reading imports."""
import ast
import re
import os
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "deallens"
INFRA = {"sqlite3", "urllib", "socket", "http", "requests", "streamlit", "anthropic", "subprocess"}


def imports(path: Path) -> set[str]:
    out = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            out |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module)
    return out


def package_imports(pkg: str) -> set[str]:
    target = SRC / pkg
    files = [target] if target.suffix == ".py" else list(target.rglob("*.py"))
    return set().union(*(imports(f) for f in files))


def offenders(found: set[str], banned: set[str]) -> set[str]:
    return {m for m in found if any(m == b or m.startswith(b + ".") for b in banned)}


def test_domain_imports_no_infrastructure_or_other_modules():
    found = package_imports("domain.py")
    assert not offenders(found, INFRA | {"deallens"})


def test_market_and_analysis_stay_pure():
    banned = INFRA | {"deallens.serpapi", "deallens.evidence", "deallens.collector", "deallens.projection",
                      "deallens.investigation", "deallens.cli", "os"}
    assert not offenders(package_imports("market"), banned)
    assert not offenders(package_imports("analysis"), banned)


def test_collector_knows_nothing_about_matching_or_claims():
    banned = {"deallens.market", "deallens.analysis", "deallens.projection", "deallens.serpapi.http"}
    assert not offenders(package_imports("collector"), banned)


def test_adapters_do_not_reach_into_the_core():
    banned = {"deallens.market", "deallens.analysis", "deallens.collector"}
    for pkg in ("serpapi", "evidence", "projection"):
        assert not offenders(package_imports(pkg), banned), pkg


def test_only_the_cli_imports_the_live_serpapi_adapter():
    users = [f.relative_to(SRC).as_posix() for f in SRC.rglob("*.py")
             if offenders(imports(f), {"deallens.serpapi.http"}) and f.name != "http.py"]
    assert users == ["cli.py"]


def test_no_paid_endpoint_or_raw_http_outside_the_http_adapter():
    """Every paid SerpApi call must go through serpapi.CallBudget -> HttpSerpApi; no ad-hoc paid scripts."""
    repo = SRC.parents[1]
    allowed = SRC / "serpapi" / "http.py"
    files = [f for d in ("src", "scripts") if (repo / d).exists() for f in (repo / d).rglob("*.py")]
    offenders_ = [f.relative_to(repo).as_posix() for f in files if f != allowed and
                  any(s in f.read_text(encoding="utf-8") for s in ("serpapi.com", "urlopen", "urllib.request"))]
    assert offenders_ == []


def test_credit_guard_has_one_implementation():
    """min_remaining is enforced only inside serpapi.CallBudget; callers never re-implement the comparison."""
    import re
    compare = re.compile(r"<\s*[\w.]*min_remaining")
    guards = [f.relative_to(SRC).as_posix() for f in SRC.rglob("*.py") if "credit guard:" in f.read_text(encoding="utf-8")]
    comparisons = [f.relative_to(SRC).as_posix() for f in SRC.rglob("*.py") if compare.search(f.read_text(encoding="utf-8"))]
    assert guards == ["serpapi/__init__.py"] and comparisons == ["serpapi/__init__.py"]


def test_only_the_cli_reads_environment_variables():
    readers = [f.relative_to(SRC).as_posix() for f in SRC.rglob("*.py")
               if "os.environ" in f.read_text(encoding="utf-8") or "getenv" in f.read_text(encoding="utf-8")]
    assert readers == ["cli.py"]


def test_streamlit_is_only_used_by_the_app():
    users = [f.relative_to(SRC).as_posix() for f in SRC.rglob("*.py") if offenders(imports(f), {"streamlit"})]
    assert all(u.startswith("app/") for u in users)


def test_public_mode_never_loads_the_live_adapter_even_with_a_key(tmp_path):
    code = ("import sys, deallens.public as p; p.open_public_reader(sys.argv[1]); "
            "bad = [m for m in sys.modules if m in ('deallens.serpapi.http', 'deallens.collector', "
            "'deallens.investigation', 'urllib.request')]; print(bad); sys.exit(1 if bad else 0)")
    env = {**os.environ, "SERPAPI_API_KEY": "would-be-live-key", "DEALLENS_MODE": "live",
           "PYTHONPATH": str(SRC.parent)}
    r = subprocess.run([sys.executable, "-c", code, str(tmp_path)], env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


# ---------- future Streamlit app: presentation only ----------

APP_ALLOWED_DEALLENS = ("deallens.public", "deallens.projection", "deallens.text", "deallens.app")
APP_BANNED = {"os", "sqlite3", "subprocess", "urllib", "socket", "http", "requests", "anthropic"}


def app_violations(app_dir: Path) -> list[str]:
    """Every import or environment read in app_dir that breaks the presentation-only boundary."""
    found = []
    for f in sorted(app_dir.rglob("*.py")) if app_dir.exists() else []:
        text = f.read_text(encoding="utf-8")
        if "os.environ" in text or "getenv" in text:
            found.append(f"{f.name}: reads environment")
        for m in imports(f):
            if m.startswith("deallens") and not any(m == a or m.startswith(a + ".") for a in APP_ALLOWED_DEALLENS):
                found.append(f"{f.name}: imports {m}")
            elif offenders({m}, APP_BANNED):
                found.append(f"{f.name}: imports {m}")
    return found


def test_app_package_is_presentation_only():
    assert app_violations(SRC / "app") == []


def test_app_boundary_check_catches_violations(tmp_path):
    """Positive control: the rule above must reject each forbidden dependency."""
    bad = tmp_path / "app"
    bad.mkdir()
    (bad / "ok.py").write_text("\n".join([
        "import streamlit as st",
        "from deallens.public import open_public_reader",
        "from deallens.text import inr",
    ]), encoding="utf-8")
    (bad / "bad.py").write_text("\n".join([
        "import os",
        "import sqlite3",
        "from deallens.serpapi.http import HttpSerpApi",
        "from deallens.collector import collect",
        "from deallens.investigation import investigate",
        "from deallens.analysis import analyse",
        "KEY = os.environ.get('X')",
    ]), encoding="utf-8")
    assert sorted(app_violations(bad)) == sorted([
        "bad.py: reads environment", "bad.py: imports os", "bad.py: imports sqlite3",
        "bad.py: imports deallens.serpapi.http", "bad.py: imports deallens.collector",
        "bad.py: imports deallens.investigation", "bad.py: imports deallens.analysis"])


# ---------- read-only API adapter ----------

API_ALLOWED_DEALLENS = ("deallens.public", "deallens.app.views", "deallens.app.labels", "deallens.text", "deallens.api")
API_BANNED = {"os", "sqlite3", "subprocess", "urllib", "socket", "requests", "anthropic", "streamlit"}


def test_api_adapter_is_read_only_and_presentation_only():
    found = []
    for f in sorted((SRC / "api").rglob("*.py")):
        text = f.read_text(encoding="utf-8")
        if "os.environ" in text or "getenv" in text:
            found.append(f"{f.name}: reads environment")
        for m in imports(f):
            if m.startswith("deallens") and m != "deallens.app" and \
                    not any(m == a or m.startswith(a + ".") for a in API_ALLOWED_DEALLENS):
                found.append(f"{f.name}: imports {m}")
            elif offenders({m}, API_BANNED):
                found.append(f"{f.name}: imports {m}")
        assert not re.search(r"@app\.(post|put|patch|delete)", text), f.name
    assert (SRC / "api").exists() and found == []


def test_api_never_loads_the_live_adapter_even_with_a_key(tmp_path):
    code = ("import sys; from deallens.api import create_app; create_app(sys.argv[1]); "
            "bad = [m for m in sys.modules if m in ('deallens.serpapi.http', 'deallens.collector', "
            "'deallens.investigation', 'urllib.request', 'streamlit')]; print(bad); sys.exit(1 if bad else 0)")
    env = {**os.environ, "SERPAPI_API_KEY": "would-be-live-key", "DEALLENS_MODE": "live", "PYTHONPATH": str(SRC.parent)}
    r = subprocess.run([sys.executable, "-c", code, str(tmp_path)], env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
