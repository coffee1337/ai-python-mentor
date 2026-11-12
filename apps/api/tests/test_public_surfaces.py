"""Public surfaces: SEO snapshot completeness, PWA shell and its cache rules.

These are files crawled or installed by a browser, so the checks read the artifacts
the build actually ships: the exported snapshot, the icons, the service worker and
the metadata routes.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
WEB = ROOT / "apps" / "web"
SEO = WEB / "content" / "seo.json"


def test_seo_snapshot_covers_the_whole_course():
    payload = json.loads(SEO.read_text(encoding="utf-8"))
    assert len(payload["concepts"]) == 90
    assert len(payload["skills"]) == 90
    assert len(payload["roadmaps"]) == 3
    assert payload["errors"], "страницы ошибок строятся из разборов заблуждений"
    total = sum(len(item["lessons"]) for item in payload["roadmaps"])
    assert total == 90, f"маршруты должны покрывать все уроки, покрыто {total}"


def test_seo_snapshot_never_carries_graded_content():
    payload = json.loads(SEO.read_text(encoding="utf-8"))
    forbidden = {"question", "choices", "answer", "explanation", "hints", "solution"}
    for concept in payload["concepts"]:
        assert not (forbidden & set(concept)), f"{concept['slug']} содержит оцениваемые поля"
    for error in payload["errors"]:
        assert not (forbidden & set(error)), error["slug"]


def test_concept_slugs_are_unique_and_url_safe():
    payload = json.loads(SEO.read_text(encoding="utf-8"))
    slugs = [item["slug"] for item in payload["concepts"]]
    assert len(slugs) == len(set(slugs)), "дубли slug ломают статические маршруты"
    assert all(slug.replace("-", "").isalnum() for slug in slugs), slugs[:3]


def test_pwa_icons_are_real_png_files():
    for name, size in (("icon-192.png", 192), ("icon-512.png", 512), ("apple-touch-icon.png", 180)):
        path = WEB / "public" / name
        raw = path.read_bytes()
        assert raw[:8] == b"\x89PNG\r\n\x1a\n", name
        width = int.from_bytes(raw[16:20], "big")
        height = int.from_bytes(raw[20:24], "big")
        assert (width, height) == (size, size), (name, width, height)


def test_service_worker_never_caches_the_api_and_has_an_offline_fallback():
    worker = (WEB / "public" / "sw.js").read_text(encoding="utf-8")
    assert 'url.pathname.startsWith("/api/")' in worker, "ответы API не кэшируются"
    assert '"/offline"' in worker, "есть офлайн-страница"
    assert "skipWaiting" in worker and "clients.claim" in worker, "обновление воркера не зависает"
    assert (WEB / "app" / "offline" / "page.tsx").is_file()


def test_manifest_declares_an_installable_app():
    manifest = (WEB / "app" / "manifest.ts").read_text(encoding="utf-8")
    for field in ("name:", "short_name:", "start_url:", "display:", "icons:", "theme_color:"):
        assert field in manifest, field
    assert '"standalone"' in manifest
    assert "192x192" in manifest and "512x512" in manifest


def test_public_routes_and_metadata_files_exist():
    for route in ("concepts", "roadmaps", "errors", "interviews", "skills/[slug]"):
        assert (WEB / "app" / route).exists(), route
    assert (WEB / "app" / "sitemap.ts").is_file()
    assert (WEB / "app" / "robots.ts").is_file()
    robots = (WEB / "app" / "robots.ts").read_text(encoding="utf-8")
    assert '"/admin"' in robots, "админка закрыта от индексации"


def test_seo_snapshot_matches_the_authored_course():
    """A stale snapshot would publish a lesson list the product no longer teaches."""
    import importlib.util
    import sys

    script = ROOT / "scripts" / "export-seo-content.py"
    spec = importlib.util.spec_from_file_location("export_seo_content", script)
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(ROOT / "apps" / "api"))
    try:
        spec.loader.exec_module(module)
        expected = module.build()
    finally:
        sys.path.pop(0)
    committed = json.loads(SEO.read_text(encoding="utf-8"))
    assert json.loads(json.dumps(expected, sort_keys=True)) == committed, (
        "seo.json устарел: запустите python scripts/export-seo-content.py"
    )
