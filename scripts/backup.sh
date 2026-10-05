#!/usr/bin/env bash
# Shared Python engine; PowerShell extracts the same block (no Bash/WSL required).
set -euo pipefail
export BACKUP_REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
if command -v cygpath >/dev/null 2>&1; then
  export BACKUP_REPO_ROOT="$(cygpath -w "$BACKUP_REPO_ROOT")"
fi
exec "${PYTHON:-python3}" -I - "${BACKUP_MODE:-backup}" "$@" <<'PYTHON_ENGINE'
import argparse
import base64
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import uuid

class SafeError(Exception):
    pass

class SafeArgumentParser(argparse.ArgumentParser):
    def error(self, _message):
        self.exit(2, "operation_failed:invalid_arguments\n")

def require(condition, message):
    if not condition:
        raise SafeError(message)

def run(argv, *, env=None, cwd=None, timeout=3600):
    # Raw PostgreSQL errors can contain SQL, connection details or row data.
    result = subprocess.run(argv, env=env, cwd=cwd, capture_output=True, timeout=timeout)
    require(result.returncode == 0, "command_failed:" + Path(argv[0]).stem)
    return result.stdout

def plain_name(value):
    require(bool(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,62}", value or "")),
            "database_name_required:no_URI_or_connection_string")
    return value

def safe_path(path):
    path = Path(path).absolute()
    for component in (path, *path.parents):
        require(not component.is_symlink() and not component.is_junction(),
                "symlink_or_junction_not_allowed")
    return path.resolve()

def secure_directory(path):
    if os.name == "nt":
        # Replace rather than augment an existing DACL, then verify it.
        script = r"""
$ErrorActionPreference='Stop'
$path='__PATH__'
$sid=[System.Security.Principal.WindowsIdentity]::GetCurrent().User
$system=New-Object System.Security.Principal.SecurityIdentifier('S-1-5-18')
$acl=[IO.Directory]::GetAccessControl($path,[System.Security.AccessControl.AccessControlSections]::Access)
$acl.SetAccessRuleProtection($true,$false)
foreach($rule in @($acl.GetAccessRules($true,$true,[System.Security.Principal.SecurityIdentifier]))) {
  [void]$acl.RemoveAccessRuleSpecific($rule)
}
foreach($id in @($sid,$system)) {
  $rule=New-Object System.Security.AccessControl.FileSystemAccessRule($id,'FullControl','ContainerInherit,ObjectInherit','None','Allow')
  $acl.AddAccessRule($rule)
}
[IO.Directory]::SetAccessControl($path,$acl)
$check=Get-Acl -LiteralPath $path
$rules=@($check.GetAccessRules($true,$true,[System.Security.Principal.SecurityIdentifier]))
if(-not $check.AreAccessRulesProtected -or $rules.Count -ne 2) { throw 'ACL verification failed' }
foreach($rule in $rules) {
  if($rule.IdentityReference.Value -notin @($sid.Value,$system.Value) -or
     $rule.AccessControlType -ne 'Allow' -or $rule.FileSystemRights -ne 'FullControl') {
    throw 'ACL verification failed'
  }
}
""".replace("__PATH__", str(path).replace("'", "''"))
        encoded = base64.b64encode(script.encode("utf-16-le")).decode()
        run(["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
            timeout=30)
    else:
        require(path.stat().st_uid == os.getuid(), "backup_directory_not_owned")
        path.chmod(0o700)

def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def secure_bundle_files(bundle):
    for path in bundle.iterdir():
        path = safe_path(path)
        require(path.is_file(), "unexpected_bundle_entry")
        if os.name == "nt":
            # Reset protected file ACLs to inherit the verified private parent.
            run(["icacls.exe", str(path), "/reset"], timeout=30)
        else:
            require(path.stat().st_uid == os.getuid(), "backup_file_not_owned")
            path.chmod(0o600)

def tool(args, name):
    path = Path(args.pg_bin) / (name + (".exe" if os.name == "nt" else "")) if args.pg_bin else shutil.which(name)
    require(bool(path) and Path(path).is_file(), "missing_tool:" + name)
    return str(path)

def load_manifest(path):
    require(path.stat().st_size <= 4 * 1024 * 1024, "manifest_too_large")
    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, "duplicate_manifest_key")
            result[key] = value
        return result
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_pairs)
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise SafeError("invalid_manifest") from None
    require(isinstance(manifest, dict), "invalid_manifest")
    required = {"format", "created_at", "source_database", "server_major",
                "sha256", "counts", "row_sha256", "columns", "revisions"}
    require(set(manifest) == required, "invalid_manifest_keys")
    require(manifest["format"] == "mentor-pg-backup-v2", "unsupported_manifest")
    require(isinstance(manifest["created_at"], str) and
            re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?\+00:00",
                         manifest["created_at"]) is not None, "invalid_manifest_time")
    plain_name(manifest["source_database"])
    require(isinstance(manifest["server_major"], int) and 10 <= manifest["server_major"] <= 99,
            "invalid_manifest_server_major")
    require(isinstance(manifest["sha256"], str) and
            re.fullmatch(r"[0-9a-f]{64}", manifest["sha256"]) is not None,
            "invalid_manifest_digest")
    require(isinstance(manifest["counts"], dict) and all(
        isinstance(key, str) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,62}\.[A-Za-z_][A-Za-z0-9_]{0,62}", key)
        and isinstance(value, int) and value >= 0 for key, value in manifest["counts"].items()),
            "invalid_manifest_counts")
    require(isinstance(manifest["row_sha256"], dict) and
            set(manifest["row_sha256"]) == set(manifest["counts"]) and all(
                isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value)
                for value in manifest["row_sha256"].values()), "invalid_manifest_row_digest")
    require(isinstance(manifest["columns"], list) and all(
        isinstance(row, list) and len(row) == 6 and all(isinstance(value, (str, int)) for value in row)
        for row in manifest["columns"]), "invalid_manifest_columns")
    require(isinstance(manifest["revisions"], list) and all(
        isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_]{1,64}", value)
        for value in manifest["revisions"]), "invalid_manifest_revisions")
    return manifest

def connect(database, *, autocommit=False, admin=False):
    import psycopg
    extra = {"host": os.environ["PGHOST"], "port": os.environ["PGPORT"],
             "user": os.environ["PGUSER"]}
    if admin:
        require(bool(os.environ.get("DRILL_ADMIN_USER")), "DRILL_ADMIN_USER_required")
        extra["user"] = os.environ["DRILL_ADMIN_USER"]
        require(bool(os.environ.get("DRILL_ADMIN_PASSFILE") or os.environ.get("PGPASSFILE")),
                "DRILL_ADMIN_PASSFILE_or_PGPASSFILE_required")
        # Empty explicit password avoids accidental use of inherited PGPASSWORD.
        extra["password"] = ""
        extra["passfile"] = os.environ.get("DRILL_ADMIN_PASSFILE") or os.environ["PGPASSFILE"]
    return psycopg.connect(dbname=plain_name(database), autocommit=autocommit,
                          connect_timeout=10, options="-c statement_timeout=300000 -c lock_timeout=30000",
                          **extra)

def child_env():
    # Never propagate gateway/runner/admin secrets into PostgreSQL clients or API.
    allowed = {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "HOME", "APPDATA",
               "VIRTUAL_ENV", "LANG", "LC_ALL", "LD_LIBRARY_PATH"}
    env = {k: v for k, v in os.environ.items() if k.upper() in allowed or
           k in {"PGHOST", "PGPORT", "PGUSER", "PGPASSFILE", "PGSSLMODE",
                 "PGSSLROOTCERT", "PGSSLCERT", "PGSSLKEY", "PGCONNECT_TIMEOUT"}}
    env["PGCONNECT_TIMEOUT"] = "10"
    return env

def inventory(connection):
    from psycopg import sql
    rows = connection.execute("""
        SELECT n.nspname, c.relname FROM pg_class c
        JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE c.relkind IN ('r','p') AND n.nspname !~ '^pg_'
        AND n.nspname <> 'information_schema' ORDER BY 1,2
    """).fetchall()
    required = {"users", "lesson_completions", "skill_evidence", "ai_usage_ledger", "alembic_version"}
    require(required <= {t for s, t in rows if s == "public"}, "required_tables_missing")
    counts, row_sha256 = {}, {}
    connection.execute("SET LOCAL TIME ZONE 'UTC'")
    connection.execute("SET LOCAL bytea_output = 'hex'")
    connection.execute("SET LOCAL DateStyle = 'ISO, YMD'")
    connection.execute("SET LOCAL IntervalStyle = 'postgres'")
    connection.execute("SET LOCAL extra_float_digits = 3")
    for schema, table in rows:
        key = schema + "." + table
        counts[key] = connection.execute(
            sql.SQL("SELECT count(*) FROM {}.{}").format(sql.Identifier(schema), sql.Identifier(table))
        ).fetchone()[0]
        # Compare values (including NULL/JSON/state), not just counts. Stream a
        # deterministic ordering; never put raw rows in manifest or output.
        h = hashlib.sha256()
        with connection.cursor(name="backup_rows_" + uuid.uuid4().hex) as cursor:
            cursor.execute(sql.SQL(
                'SELECT to_jsonb(t)::text AS payload FROM {}.{} t '
                'ORDER BY to_jsonb(t)::text COLLATE "C"'
            ).format(sql.Identifier(schema), sql.Identifier(table)))
            for (payload,) in cursor:
                encoded = payload.encode("utf-8")
                h.update(len(encoded).to_bytes(8, "big"))
                h.update(encoded)
        row_sha256[key] = h.hexdigest()
    # All columns, including future rate_limit_state / nullable ledger fields.
    columns = connection.execute("""
        SELECT table_schema, table_name, column_name, data_type, is_nullable, ordinal_position
        FROM information_schema.columns WHERE table_schema !~ '^pg_'
        AND table_schema <> 'information_schema' ORDER BY 1,2,6
    """).fetchall()
    revisions = sorted(r[0] for r in connection.execute("SELECT version_num FROM public.alembic_version"))
    return {"counts": counts, "row_sha256": row_sha256,
            "columns": [list(row) for row in columns], "revisions": revisions}

def validate_versions(args, connection):
    major = connection.info.server_version // 10000
    for name in ("pg_dump", "pg_restore"):
        version = run([tool(args, name), "--version"], timeout=30).decode()
        match = re.search(r"PostgreSQL\)\s+(\d+)", version)
        require(match is not None and int(match[1]) == major, "client_server_major_mismatch")
    return major

def retention(root, args, now):
    # Only successful, script-owned bundles; never recursive deletion.
    bundles = []
    for path in root.iterdir():
        if not re.fullmatch(r"\d{8}T\d{6}Z-[0-9a-f]{12}", path.name):
            continue
        safe_path(path)
        if not path.is_dir():
            continue
        names = {p.name for p in path.iterdir()}
        fixed = {"database.dump", "manifest.json", "SUCCESS"}
        if not fixed <= names or any(
                name not in fixed and not re.fullmatch(r"drill-[0-9a-f]{12}\.json", name)
                for name in names):
            continue
        if any(not p.is_file() or p.is_symlink() for p in path.iterdir()):
            continue
        try:
            manifest = load_manifest(path / "manifest.json")
        except (SafeError, OSError):
            # Unknown/older bundles are not ours to prune.
            continue
        if manifest.get("format") != "mentor-pg-backup-v2":
            continue
        # Never prune another database's backup.
        if manifest.get("source_database") != args.database:
            continue
        timestamp = dt.datetime.fromisoformat(manifest["created_at"])
        bundles.append((timestamp, path))
    bundles.sort(reverse=True)
    keep, days, weeks, months = set(), set(), set(), set()
    for stamp, path in bundles:
        day, week, month = stamp.date(), stamp.isocalendar()[:2], (stamp.year, stamp.month)
        if day not in days and len(days) < args.daily:
            keep.add(path); days.add(day)
        if week not in weeks and len(weeks) < args.weekly:
            keep.add(path); weeks.add(week)
        if month not in months and len(months) < args.monthly:
            keep.add(path); months.add(month)
    for _, path in bundles:
        if path not in keep:
            for file in list(path.iterdir()):
                safe_path(file).unlink()
            path.rmdir()

def backup(args):
    root = safe_path(args.backup_dir)
    repo = safe_path(os.environ["BACKUP_REPO_ROOT"])
    require(root != repo and root not in repo.parents and root != Path(root.anchor),
            "backup_directory_must_be_dedicated")
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    secure_directory(root)
    # A root is bound to one endpoint/database; same-name DBs on other hosts
    # cannot silently prune one another's backups.
    source = hashlib.sha256(json.dumps(
        [os.environ["PGHOST"], os.environ["PGPORT"], args.database]
    ).encode()).hexdigest()
    marker = safe_path(root / ".source")
    if marker.exists():
        require(marker.read_text(encoding="ascii").strip() == source,
                "backup_root_source_mismatch")
    else:
        require(not any(root.iterdir()), "unbound_backup_root_not_empty")
        with marker.open("x", encoding="ascii") as stream:
            stream.write(source + "\n")
    lock = root / ".backup.lock"
    try:
        lock.mkdir()
    except FileExistsError:
        raise SafeError("backup_lock_exists:inspect_stale_lock_manually") from None
    try:
        now = dt.datetime.now(dt.timezone.utc)
        bundle = root / (now.strftime("%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:12])
        bundle.mkdir(mode=0o700)
        archive = bundle / "database.dump.partial"
        with connect(args.database) as connection:
            connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            major = validate_versions(args, connection)
            snapshot = connection.execute("SELECT pg_export_snapshot()").fetchone()[0]
            data = inventory(connection)
            run([tool(args, "pg_dump"), "--no-password", "-Fc", "--snapshot=" + snapshot,
                 "--lock-wait-timeout=30s", "--dbname=" + args.database, "--file=" + str(archive)],
                env=child_env(), timeout=args.timeout)
        require(archive.stat().st_size > 0, "empty_archive")
        run([tool(args, "pg_restore"), "-l", str(archive)], env=child_env(), timeout=args.timeout)
        archive.rename(bundle / "database.dump")
        data.update(format="mentor-pg-backup-v2", created_at=now.isoformat(),
                    source_database=args.database, server_major=major,
                    sha256=digest(bundle / "database.dump"))
        (bundle / "manifest.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        secure_bundle_files(bundle)
        (bundle / "SUCCESS").write_text(now.isoformat() + "\n", encoding="utf-8")
        retention(root, args, now)
        print("backup_ok bundle=" + str(bundle))
    finally:
        lock.rmdir()

def alembic_report(args, connection, expected):
    # Execute real `current` and `heads` read-only, against the restored database.
    # Use libpq env/pgpass rather than putting a password in argv or a saved URL.
    from sqlalchemy import URL
    info = connection.info
    url = URL.create("postgresql+psycopg", username=info.user, host=info.host,
                     port=info.port, database=info.dbname).render_as_string(hide_password=False)
    env = child_env()
    env["DATABASE_URL"] = url
    env["PGOPTIONS"] = "-c default_transaction_read_only=on"
    current = run([sys.executable, "-m", "alembic", "current"], env=env,
                  cwd=args.api_dir, timeout=args.timeout).decode()
    heads = run([sys.executable, "-m", "alembic", "heads"], env=env,
                cwd=args.api_dir, timeout=args.timeout).decode()
    current_revisions = sorted(line.split()[0] for line in current.splitlines() if line.strip())
    head_revisions = sorted(line.split()[0] for line in heads.splitlines() if line.strip())
    require(current_revisions == expected, "alembic_current_differs_from_manifest")
    at_head = current_revisions == head_revisions
    print("alembic_current=" + ",".join(current_revisions))
    print("alembic_heads=" + ",".join(head_revisions))
    print("schema_at_head=" + str(at_head).lower())
    require(at_head or args.allow_older_revision, "older_backup:use_matching_code_or_explicit_allow_older_revision")
    return at_head

def smoke(args, connection, report):
    # Own short-lived API process; never probe an unrelated/production API.
    import socket
    import urllib.error
    import urllib.request
    from sqlalchemy import URL
    info = connection.info
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = child_env()
    env["DATABASE_URL"] = URL.create("postgresql+psycopg", username=info.user, host=info.host,
                                    port=info.port, database=info.dbname).render_as_string(hide_password=False)
    env["PGOPTIONS"] = "-c default_transaction_read_only=on"
    with subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app",
                           "--host", "127.0.0.1", "--port", str(port), "--no-access-log"],
                          env=env, cwd=args.api_dir, stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL) as process:
        try:
            class NoRedirect(urllib.request.HTTPRedirectHandler):
                def redirect_request(self, *unused):
                    return None
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
            healthy = False
            for _ in range(100):
                require(process.poll() is None, "smoke_api_start_failed")
                try:
                    with opener.open(f"http://127.0.0.1:{port}/health", timeout=2) as response:
                        healthy = response.status == 200 and json.load(response).get("database") == "ok"
                    if healthy:
                        break
                except (OSError, ValueError):
                    pass
                time.sleep(0.1)
            require(healthy, "health_smoke_failed")
            report["health"] = "passed"
            print("health=passed")
            try:
                with opener.open(f"http://127.0.0.1:{port}/ready", timeout=5) as response:
                    require(response.status == 200, "ready_smoke_failed")
                report["ready"] = "passed"
            except urllib.error.HTTPError as error:
                require(error.code == 404, "ready_smoke_failed")
                report["ready"] = "not_implemented"
                print("ready=not_implemented (HTTP 404)")
                require(not args.require_ready, "required_ready_endpoint_missing")
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait()

def restore(args):
    from psycopg import sql
    bundle = safe_path(args.bundle)
    archive, manifest_path = safe_path(bundle / "database.dump"), safe_path(bundle / "manifest.json")
    require((bundle / "SUCCESS").is_file(), "incomplete_backup")
    manifest = load_manifest(manifest_path)
    secure_directory(bundle)
    secure_bundle_files(bundle)
    require(digest(archive) == manifest["sha256"], "archive_checksum_mismatch")
    run([tool(args, "pg_restore"), "-l", str(archive)], env=child_env(), timeout=args.timeout)
    target = plain_name(args.target or ("mentor_restore_" + dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:8]))
    require(target.startswith("mentor_restore_") and target != manifest["source_database"],
            "target_must_be_new_mentor_restore_database")
    report = {"target": target, "database_created": False,
              "started_at": dt.datetime.now(dt.timezone.utc).isoformat(),
              "status": "failed", "health": "not_run", "ready": "not_run"}
    print("restore_target=" + target)
    try:
        with connect(args.admin_database) as preflight:
            preflight.execute("SET TRANSACTION READ ONLY")
            privileges = preflight.execute("""
                SELECT rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls
                FROM pg_roles WHERE rolname=current_user
            """).fetchone()
            require(privileges is not None and not any(privileges), "restore_login_must_be_unprivileged")
            require(preflight.execute("""
                SELECT count(*) FROM pg_roles
                WHERE (rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls)
                AND pg_has_role(current_user, oid, 'MEMBER')
            """).fetchone()[0] == 0, "restore_login_has_privileged_membership")
            require(preflight.execute("""
                SELECT count(*) FROM pg_roles WHERE rolname IN (
                  'pg_execute_server_program', 'pg_read_server_files',
                  'pg_write_server_files', 'pg_read_all_data', 'pg_write_all_data'
                ) AND pg_has_role(current_user, oid, 'MEMBER')
            """).fetchone()[0] == 0, "restore_login_has_dangerous_role")
            restore_user = preflight.info.user
        with connect(args.admin_database, autocommit=True, admin=True) as admin:
            major = validate_versions(args, admin)
            require(major == manifest["server_major"], "drill_requires_same_server_major")
            require(admin.execute("SELECT 1 FROM pg_database WHERE datname=%s", (target,)).fetchone() is None,
                    "target_already_exists:never_overwrite")
            # Fail if CREATE DATABASE races with another process; no IF NOT EXISTS.
            admin.execute(sql.SQL("CREATE DATABASE {} OWNER {} TEMPLATE template0").format(
                sql.Identifier(target), sql.Identifier(restore_user)))
            report["database_created"] = True
            admin.execute(sql.SQL("REVOKE CONNECT ON DATABASE {} FROM PUBLIC").format(sql.Identifier(target)))
        with connect(target) as identity:
            require(identity.info.dbname == target and identity.info.user == restore_user,
                    "target_identity_mismatch")
        run([tool(args, "pg_restore"), "--no-password", "--exit-on-error", "--single-transaction",
             "--no-owner", "--no-privileges", "--dbname=" + target, str(archive)],
            env=child_env(), timeout=args.timeout)
        with connect(target) as connection:
            connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            restored = inventory(connection)
            for key in ("counts", "row_sha256", "columns", "revisions"):
                require(restored[key] == manifest[key], "restored_" + key + "_mismatch")
            report["data_checks"] = "all_table_counts_row_digests_columns_revisions_match_snapshot"
            print("data_checks=passed tables=" + str(len(restored["counts"])))
            at_head = alembic_report(args, connection, manifest["revisions"])
            if args.smoke:
                require(at_head, "smoke_requires_backup_at_code_head")
                smoke(args, connection, report)
        report["status"] = "passed" if not args.smoke or report["ready"] == "passed" else "passed_with_ready_gap"
    finally:
        report["finished_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
        # Report is aggregate only; no rows/keys/URLs. Restrictive bundle permissions.
        destination = bundle / ("drill-" + uuid.uuid4().hex[:12] + ".json")
        destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print("drill_report=" + str(destination))
        if report["database_created"]:
            print("temporary_database_retained=" + target)
    print("restore_drill=" + report["status"])

def main():
    os.umask(0o077)
    parser = SafeArgumentParser(description="Local PostgreSQL custom backup / non-destructive restore drill")
    parser.add_argument("mode", choices=("backup", "restore"))
    parser.add_argument("--pg-bin", default=os.environ.get("PG_BIN"))
    parser.add_argument("--timeout", type=int, default=3600)
    parser.add_argument("--database", default=os.environ.get("PGDATABASE"))
    parser.add_argument("--backup-dir", default=str(Path(os.environ["BACKUP_REPO_ROOT"]) / "backups"))
    parser.add_argument("--daily", type=int, default=7)
    parser.add_argument("--weekly", type=int, default=4)
    parser.add_argument("--monthly", type=int, default=6)
    parser.add_argument("--bundle")
    parser.add_argument("--target")
    parser.add_argument("--admin-database", default="postgres")
    parser.add_argument("--api-dir", default=str(Path(os.environ["BACKUP_REPO_ROOT"]) / "apps" / "api"))
    parser.add_argument("--allow-older-revision", action="store_true")
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--require-ready", action="store_true")
    args = parser.parse_args()
    require(not any(os.environ.get(key) for key in ("PGSERVICE", "PGSERVICEFILE", "PGHOSTADDR")),
            "PGSERVICE_not_supported:use_explicit_PGHOST_PGPORT_PGUSER")
    require(bool(re.fullmatch(r"[A-Za-z0-9.:-]+", os.environ.get("PGHOST", ""))) and
            bool(re.fullmatch(r"\d{1,5}", os.environ.get("PGPORT", ""))) and
            1 <= int(os.environ["PGPORT"]) <= 65535 and bool(os.environ.get("PGUSER")),
            "explicit_PGHOST_PGPORT_PGUSER_required")
    require(os.environ.get("BACKUP_ENCRYPTED_STORAGE") == "1",
            "encrypted_storage_ack_required:BACKUP_ENCRYPTED_STORAGE=1")
    require(args.timeout > 0 and all(n >= 1 for n in (args.daily, args.weekly, args.monthly)), "invalid_limits")
    if args.mode == "backup":
        args.database = plain_name(args.database)
        backup(args)
    else:
        require(bool(args.bundle), "bundle_required")
        require(not os.environ.get("PGPASSWORD"),
                "restore_requires_passfile:no_inherited_PGPASSWORD")
        require(not args.require_ready or args.smoke, "require_ready_needs_smoke")
        # Serialize against backup retention and other drills on this bundle root.
        lock = safe_path(Path(args.bundle).parent / ".backup.lock")
        try:
            lock.mkdir()
        except FileExistsError:
            raise SafeError("backup_lock_exists:inspect_stale_lock_manually") from None
        try:
            restore(args)
        finally:
            lock.rmdir()

if __name__ == "__main__":
    try:
        main()
    except (Exception, KeyboardInterrupt) as error:
        # No traceback, exception payload, stderr or DATABASE_URL in output.
        print("operation_failed:" + (str(error) if isinstance(error, SafeError) else type(error).__name__),
              file=sys.stderr)
        sys.exit(1)
PYTHON_ENGINE
