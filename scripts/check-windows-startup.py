"""Exercise the documented launchers on Windows PowerShell 5.1, without Docker."""
from __future__ import annotations

import http.cookiejar
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[1]
SECRET = "private-startup-test-password"


def launch(script: Path, *args: str) -> list[str]:
    return ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), *args]


def run(command: list[str], *, cwd: Path, env: dict[str, str], success: bool, contains: str = "") -> str:
    result = subprocess.run(command, cwd=cwd, env=env, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", timeout=300)
    assert (result.returncode == 0) == success, result.stdout
    assert contains in result.stdout, result.stdout
    assert SECRET not in result.stdout, "Database credentials leaked into diagnostics"
    return result.stdout


def wait_http(url: str, process: subprocess.Popen, *, timeout: int = 90) -> dict | str:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise AssertionError(f"Launcher exited before {url} became ready")
        try:
            with urllib.request.urlopen(url, timeout=3) as response:
                data = response.read().decode("utf-8")
                return json.loads(data) if "json" in response.headers.get("Content-Type", "") else data
        except (OSError, urllib.error.HTTPError):
            time.sleep(0.5)
    raise AssertionError(f"Timed out waiting for {url}")


def stop_tree(process: subprocess.Popen | None) -> None:
    if process is not None and process.poll() is None:
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        process.wait(timeout=20)


def main() -> None:
    assert os.name == "nt" and sys.version_info[:2] == (3, 12)
    env = dict(os.environ)
    for name in ("DATABASE_URL", "APP_ENV", "COOKIE_SECURE", "WEB_ORIGINS", "PYTHONPATH"):
        env.pop(name, None)
    with tempfile.TemporaryDirectory(prefix="mentor native ") as temporary:
        work = Path(temporary)
        project = work / "project with spaces"
        api = project / "apps" / "api"
        shutil.copytree(ROOT / "apps" / "api", api,
                        ignore=shutil.ignore_patterns(".venv", "__pycache__", ".pytest_cache", "*.db", "*.sqlite3"))
        scripts = project / "scripts"
        scripts.mkdir()
        for name in ("start-api.ps1", "local-api.py"):
            shutil.copy2(ROOT / "scripts" / name, scripts / name)
        api_script = scripts / "start-api.ps1"
        database = api / "mentor-local.db"

        run(launch(api_script, "-PythonPath", str(work / "missing-python.exe"), "-UseSqlite", "-PrepareOnly"),
            cwd=work, env=env, success=False, contains="Python 3.12 was not found")
        assert not (api / ".venv").exists() and not database.exists()
        print("PASS: missing Python stops before dependency installation or database creation")

        invalid_venv = api / ".venv"
        invalid_venv.mkdir()
        sentinel = invalid_venv / "keep.txt"
        sentinel.write_text("Do not delete existing environments", encoding="utf-8")
        run(launch(api_script, "-UseSqlite", "-PrepareOnly"), cwd=work, env=env,
            success=False, contains="incomplete or does not use Python 3.12")
        assert sentinel.is_file() and not database.exists()
        shutil.rmtree(invalid_venv)  # Only the disposable fixture created above.
        print("PASS: incomplete existing venv is preserved and reported")

        python311 = env.get("STARTUP_TEST_PYTHON311")
        if python311:
            subprocess.run([python311, "-m", "venv", str(invalid_venv)], check=True, timeout=60)
            run(launch(api_script, "-UseSqlite", "-PrepareOnly"), cwd=work, env=env,
                success=False, contains="does not use Python 3.12")
            assert (invalid_venv / "Scripts" / "python.exe").is_file() and not database.exists()
            shutil.rmtree(invalid_venv)
            run(launch(api_script, "-PythonPath", python311, "-UseSqlite", "-PrepareOnly"),
                cwd=work, env=env, success=False, contains="Python 3.12 was not found")
            assert not invalid_venv.exists() and not database.exists()
            print("PASS: actual Python 3.11 is rejected both as an existing venv and as a bootstrap interpreter")

        requirements = api / "requirements.lock"
        locked = requirements.read_bytes()
        requirements.write_text("mentor-startup-test-nonexistent-package==0.0.0\n", encoding="ascii")
        run(launch(api_script, "-PythonPath", sys.executable, "-UseSqlite", "-PrepareOnly"),
            cwd=work, env={**env, "PIP_NO_INDEX": "1"}, success=False, contains="Dependency installation failed")
        assert not database.exists()
        requirements.write_bytes(locked)
        print("PASS: failed pip installation stops before migrations and server startup")

        # The configured PostgreSQL server is intentionally unavailable. SQLite
        # must never become an implicit fallback; explicit selection overrides it.
        dotenv = project / ".env"
        dotenv.write_text(f"DATABASE_URL=postgresql+psycopg://mentor:{SECRET}@127.0.0.1:1/mentor\n"
                          "APP_ENV=development\n", encoding="utf-8")
        run(launch(api_script, "-PrepareOnly"), cwd=work, env=env,
            success=False, contains="no fallback database was selected")
        assert not database.exists()
        print("PASS: unavailable configured PostgreSQL stops without fallback or credential disclosure")

        run(launch(api_script, "-SkipInstall", "-UseSqlite", "-PrepareOnly"), cwd=work,
            env={**env, "APP_ENV": "production"}, success=False, contains="development only")
        assert not database.exists()
        print("PASS: development launcher refuses a production environment")

        run(launch(api_script, "-SkipInstall", "-UseSqlite", "-PrepareOnly"), cwd=work,
            env=env, success=True, contains="API environment and schema are ready")
        expected_revision = subprocess.check_output([
            str(api / ".venv" / "Scripts" / "python.exe"), "-m", "alembic", "heads",
        ], cwd=api, env=env, text=True).split()[0]
        with sqlite3.connect(database) as connection:
            assert connection.execute("SELECT version_num FROM alembic_version").fetchone()[0] == expected_revision
        print("PASS: explicit SQLite selection applies all migrations under a project path containing spaces")

        failing_npm = work / "failed npm"
        failing_npm.mkdir()
        (failing_npm / "npm.cmd").write_text("@exit /b 17\n", encoding="ascii")
        run(launch(ROOT / "scripts" / "start-web.ps1", "-PrepareOnly"), cwd=work,
            env={**env, "PATH": str(failing_npm) + os.pathsep + env["PATH"]},
            success=False, contains="npm ci failed. Frontend was not started")
        print("PASS: failed npm installation stops before frontend startup")

        run(launch(ROOT / "scripts" / "start-web.ps1", "-PrepareOnly"), cwd=work, env=env,
            success=True, contains="Frontend dependencies and local API proxy configuration are ready")
        api_process = web_process = None
        try:
            with (work / "api.log").open("w", encoding="utf-8") as api_log, \
                    (work / "web.log").open("w", encoding="utf-8") as web_log:
                api_process = subprocess.Popen(launch(api_script, "-SkipInstall", "-UseSqlite"), cwd=work,
                                               env=env, stdout=api_log, stderr=subprocess.STDOUT)
                assert wait_http("http://127.0.0.1:8000/ready", api_process) == {"status": "ready"}
                web_process = subprocess.Popen(launch(ROOT / "scripts" / "start-web.ps1", "-SkipInstall"),
                                               cwd=work, env=env, stdout=web_log, stderr=subprocess.STDOUT)
                assert wait_http("http://127.0.0.1:3000/api/ready", web_process) == {"status": "ready"}
                html = wait_http("http://127.0.0.1:3000/register", web_process)
                assert isinstance(html, str) and "<html" in html
                cookies = http.cookiejar.CookieJar()
                client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookies))
                account = {"email": f"native-{uuid.uuid4().hex}@example.test", "password": "Native test password 123!"}
                request = urllib.request.Request("http://127.0.0.1:3000/api/auth/register",
                    data=json.dumps(account).encode(), headers={"Content-Type": "application/json",
                    "Origin": "http://localhost:3000"}, method="POST")
                with client.open(request, timeout=20) as response:
                    assert response.status == 201
                    assert json.load(response)["onboarding_required"] is True
                with client.open("http://127.0.0.1:3000/api/me", timeout=20) as response:
                    assert json.load(response)["email"] == account["email"]
                with sqlite3.connect(database) as connection:
                    assert connection.execute("SELECT COUNT(*) FROM users WHERE email = ?", (account["email"],)).fetchone()[0] == 1
                print("PASS: Windows API + Next.js proxy, registration and session-backed profile work without Docker")
        except Exception:
            for name in ("api.log", "web.log"):
                if (work / name).is_file():
                    # Diagnostics contain only synthetic test accounts/configuration.
                    print((work / name).read_text(encoding="utf-8", errors="replace").replace(SECRET, "[redacted]"))
            raise
        finally:
            stop_tree(web_process)
            stop_tree(api_process)

        # A second run must preserve the account, not recreate the file database.
        run(launch(api_script, "-SkipInstall", "-UseSqlite", "-PrepareOnly"), cwd=work,
            env=env, success=True, contains="API environment and schema are ready")
        with sqlite3.connect(database) as connection:
            assert connection.execute("SELECT COUNT(*) FROM users WHERE email = ?", (account["email"],)).fetchone()[0] == 1
        print("PASS: repeated preparation preserves the existing account")


if __name__ == "__main__":
    main()
