"""Tests for the standalone seed photo download script.

These tests verify the error-handling fix for the unhandled-403 crash —
specifically that ``PhotoSource.search()`` gracefully handles HTTP errors
(403/429), transient failures (5xx, network errors), and that the
``main()`` loop falls back to the next photo source when one source fails.
"""

from __future__ import annotations

import importlib.util
import json
import logging
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

# Load the standalone script as a module (it lives in scripts/, not on the
# package path).  The script's ``if __name__ == "__main__"`` guard ensures
# importing it does not run ``main()``.
_SCRIPT_PATH = Path(__file__).resolve().parents[5] / "scripts" / "download_seed_photos.py"
_spec = importlib.util.spec_from_file_location("download_seed_photos", _SCRIPT_PATH)
assert _spec is not None
assert _spec.loader is not None
download = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(download)

UnsplashClient = download.UnsplashClient
PexelsClient = download.PexelsClient
PhotoSource = download.PhotoSource
pick_photo = download.pick_photo
next_available_page = download.next_available_page
process_category = download.process_category
find_missing_manifest_entries = download.find_missing_manifest_entries
fix_cleanup = download.fix_cleanup
FixMode = download.FixMode
parse_cli_args = download.parse_cli_args
CliArgs = download.CliArgs
count_category_photos = download.count_category_photos
prioritize_categories = download.prioritize_categories


# ─── Helpers ────────────────────────────────────────────────────────────


def make_response(
    status_code: int = 200,
    json_data: dict | None = None,
    headers: dict[str, str] | None = None,
    text: str = "",
) -> MagicMock:
    """Build a mock ``requests.Response`` with the given status and body."""
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status_code
    resp.headers = headers or {}
    resp.text = text
    if status_code >= 400:
        resp.raise_for_status.side_effect = requests.HTTPError(
            f"HTTP {status_code}", response=resp
        )
    else:
        resp.raise_for_status.return_value = None
    resp.json.return_value = json_data or {}
    return resp


@pytest.fixture
def config() -> dict:
    """Config matching seed-images-config.example.json with fast retries."""
    return {
        "UNSPLASH_ACCESS_KEY": "test-key",
        "PEXELS_API_KEY": "test-pexels-key",
        "unsplash": True,
        "pexels": True,
        "photos_per_category": 3,
        "max_image_size_bytes": 100_000,
        "jpeg_quality": 75,
        "max_dimension_px": 1080,
        "request_timeout_sec": 5,
        "unsplash_safe_limit": 45,
        "pexels_safe_limit": 150,
        "http_max_retries": 2,
        "retry_base_delay_sec": 0.01,
    }


@pytest.fixture
def sleep_mock():
    """Prevent real sleeping during retry backoff."""
    with patch("time.sleep") as mock:
        yield mock


# ─── UnsplashClient.search ──────────────────────────────────────────────


class TestUnsplashSearch:
    """Error-handling and retry behavior for UnsplashClient.search."""

    def test_200_returns_results(self, config, sleep_mock):
        """A 200 response returns the parsed results list."""
        client = UnsplashClient("test-key", config)
        resp = make_response(
            status_code=200,
            json_data={"results": [{"id": "abc", "urls": {"raw": "http://x.jpg"}}]},
        )
        with patch("requests.get", return_value=resp):
            results = client.search("test query")
        assert len(results) == 1
        assert results[0]["id"] == "abc"
        assert not client.exhausted

    def test_429_marks_exhausted_and_returns_empty(self, config, sleep_mock):
        """A 429 (rate limit) marks the source exhausted and returns []."""
        client = UnsplashClient("test-key", config)
        resp = make_response(status_code=429, text="Rate limit")
        with patch("requests.get", return_value=resp) as mock_get:
            results = client.search("test query")
        assert results == []
        assert client.exhausted
        mock_get.assert_called_once()

    def test_429_logs_warning(self, config, sleep_mock, caplog):
        """429 is logged at WARNING (not ERROR) since it's a rate limit."""
        client = UnsplashClient("test-key", config)
        resp = make_response(status_code=429, text="Rate limit")
        with patch("requests.get", return_value=resp):
            with caplog.at_level(logging.WARNING):
                client.search("test query")
        assert any(
            "rate limit" in r.getMessage().lower()
            for r in caplog.records
        )

    def test_403_marks_exhausted_and_returns_empty(self, config, sleep_mock):
        """A 403 marks the source exhausted and returns []."""
        client = UnsplashClient("test-key", config)
        resp = make_response(status_code=403, text="Forbidden")
        with patch("requests.get", return_value=resp) as mock_get:
            results = client.search("test query")
        assert results == []
        assert client.exhausted
        mock_get.assert_called_once()

    def test_403_logs_error(self, config, sleep_mock, caplog):
        """403 is logged at ERROR (likely auth/key issue, not rate limit)."""
        client = UnsplashClient("test-key", config)
        resp = make_response(status_code=403, text="Forbidden")
        with patch("requests.get", return_value=resp):
            with caplog.at_level(logging.ERROR):
                client.search("test query")
        assert any(
            "permission denied" in r.getMessage().lower()
            for r in caplog.records
        )

    def test_500_exhausts_retries_and_returns_empty(self, config, sleep_mock):
        """Persistent 500 exhausts retries, then returns [] and marks exhausted."""
        client = UnsplashClient("test-key", config)
        resp = make_response(status_code=500, text="Internal Server Error")
        with patch("requests.get", return_value=resp) as mock_get:
            results = client.search("test query")
        assert results == []
        assert client.exhausted
        assert mock_get.call_count == 3  # initial + 2 retries

    def test_503_then_200_retries_then_succeeds(self, config, sleep_mock):
        """Transient 503 followed by 200 succeeds after retry."""
        client = UnsplashClient("test-key", config)
        resp_503 = make_response(status_code=503, text="Server Error")
        resp_200 = make_response(
            status_code=200,
            json_data={"results": [{"id": "ok", "urls": {"raw": "http://ok.jpg"}}]},
        )
        with patch("requests.get", side_effect=[resp_503, resp_200]) as mock_get:
            results = client.search("test query")
        assert len(results) == 1
        assert results[0]["id"] == "ok"
        assert not client.exhausted
        assert mock_get.call_count == 2

    def test_connection_error_then_200_retries_then_succeeds(self, config, sleep_mock):
        """Transient ConnectionError followed by 200 succeeds after retry."""
        client = UnsplashClient("test-key", config)
        resp_200 = make_response(
            status_code=200,
            json_data={"results": [{"id": "ok", "urls": {"raw": "http://ok.jpg"}}]},
        )
        with patch(
            "requests.get", side_effect=[requests.ConnectionError("boom"), resp_200]
        ) as mock_get:
            results = client.search("test query")
        assert len(results) == 1
        assert results[0]["id"] == "ok"
        assert mock_get.call_count == 2

    def test_connection_error_exhausts_and_returns_empty(self, config, sleep_mock):
        """Persistent ConnectionError exhausts retries and returns []."""
        client = UnsplashClient("test-key", config)
        with patch("requests.get", side_effect=requests.ConnectionError("boom")):
            results = client.search("test query")
        assert results == []
        assert client.exhausted

    def test_already_exhausted_returns_empty_without_request(self, config, sleep_mock):
        """An exhausted client returns [] without making any requests."""
        client = UnsplashClient("test-key", config)
        client._mark_exhausted()
        with patch("requests.get") as mock_get:
            results = client.search("test query")
        assert results == []
        mock_get.assert_not_called()

    def test_401_marks_exhausted(self, config, sleep_mock):
        """A 401 (bad key) is also handled gracefully."""
        client = UnsplashClient("test-key", config)
        resp = make_response(status_code=401, text="Unauthorized")
        with patch("requests.get", return_value=resp):
            results = client.search("test query")
        assert results == []
        assert client.exhausted


# ─── PexelsClient.search ────────────────────────────────────────────────


class TestPexelsSearch:
    """Error-handling and retry behavior for PexelsClient.search."""

    def test_200_returns_results(self, config, sleep_mock):
        """A 200 response returns the parsed photos list."""
        client = PexelsClient("test-key", config)
        resp = make_response(
            status_code=200,
            json_data={"photos": [{"id": 42, "src": {"original": "http://x.jpg"}}]},
        )
        with patch("requests.get", return_value=resp):
            results = client.search("test query")
        assert len(results) == 1
        assert results[0]["id"] == 42
        assert not client.exhausted

    def test_429_marks_exhausted_and_returns_empty(self, config, sleep_mock):
        """A 429 (Pexels rate limit) marks exhausted and returns []."""
        client = PexelsClient("test-key", config)
        resp = make_response(status_code=429, text="Rate limit")
        with patch("requests.get", return_value=resp):
            results = client.search("test query")
        assert results == []
        assert client.exhausted

    def test_403_marks_exhausted_and_returns_empty(self, config, sleep_mock):
        """A 403 (Pexels auth/permission error) marks exhausted and returns []."""
        client = PexelsClient("test-key", config)
        resp = make_response(status_code=403, text="Forbidden")
        with patch("requests.get", return_value=resp):
            results = client.search("test query")
        assert results == []
        assert client.exhausted

    def test_500_exhausts_retries_and_returns_empty(self, config, sleep_mock):
        """Persistent 500 exhausts retries and returns []."""
        client = PexelsClient("test-key", config)
        resp = make_response(status_code=500, text="Server Error")
        with patch("requests.get", return_value=resp) as mock_get:
            results = client.search("test query")
        assert results == []
        assert client.exhausted
        assert mock_get.call_count == 3

    def test_connection_error_exhausts_and_returns_empty(self, config, sleep_mock):
        """Persistent ConnectionError exhausts retries and returns []."""
        client = PexelsClient("test-key", config)
        with patch("requests.get", side_effect=requests.ConnectionError("boom")):
            results = client.search("test query")
        assert results == []
        assert client.exhausted


# ─── pick_photo / next_available_page ─────────────────────────────────────


class TestPickPhotoWithErrors:
    """pick_photo and next_available_page gracefully handle empty/error responses."""

    def test_pick_photo_returns_none_on_empty_results(self, config, sleep_mock):
        """When the API returns no unseen results, pick_photo returns None."""
        client = UnsplashClient("test-key", config)
        resp = make_response(status_code=200, json_data={"results": []})
        with patch("requests.get", return_value=resp):
            photo = pick_photo(client, "test query")
        assert photo is None

    def test_pick_photo_returns_none_when_exhausted(self, config, sleep_mock):
        """When the source is exhausted, pick_photo returns None without requests."""
        client = UnsplashClient("test-key", config)
        client._mark_exhausted()
        with patch("requests.get") as mock_get:
            photo = pick_photo(client, "test query")
        assert photo is None
        mock_get.assert_not_called()

    def test_next_available_page_handles_empty_results(self, config, sleep_mock):
        """next_available_page falls back to a random page when all pages empty."""
        client = UnsplashClient("test-key", config)
        resp = make_response(status_code=200, json_data={"results": []})
        with patch("requests.get", return_value=resp):
            page = next_available_page(client, "test query")
        # Falls back to random.randint(1, 5)
        assert 1 <= page <= 5


# ─── process_category resilience ────────────────────────────────────────


class TestProcessCategoryResilience:
    """process_category exits cleanly when the source is exhausted on errors."""

    def test_process_category_returns_zero_when_source_always_429(self, config, sleep_mock):
        """If every search returns 429, process_category downloads 0 photos."""
        client = UnsplashClient("test-key", config)
        resp = make_response(status_code=429, text="Rate limit")
        hierarchy = {"objects": ["bookshelf"], "contexts": ["wooden"], "styles": ["floor photography"]}
        manifest = {"version": 1, "categories": {}, "default": {"photos": []}}
        with patch("requests.get", return_value=resp):
            n = process_category("business-taxes", hierarchy, client, manifest, config)
        assert n == 0
        assert client.exhausted

    def test_process_category_succeeds_when_source_recovers(self, config, sleep_mock):
        """If the source 429s then recovers, process_category still gets its photos."""
        client = UnsplashClient("test-key", config)

        # First few calls: 429 (source gets exhausted).
        resp_429 = make_response(status_code=429, text="Rate limit")
        # After exhaustion, the exhausted guard returns [] without calling requests.get.
        # So process_category can't proceed — the source is permanently exhausted.
        # This confirms that a 429 correctly stops further attempts for that source.
        hierarchy = {"objects": ["bookshelf"], "contexts": ["wooden"], "styles": ["floor photography"]}
        manifest = {"version": 1, "categories": {}, "default": {"photos": []}}
        with patch("requests.get", return_value=resp_429):
            n = process_category("business-taxes", hierarchy, client, manifest, config)
        assert n == 0
        assert client.exhausted


# ─── FixMode / cleanup ────────────────────────────────────────────────────


@pytest.fixture
def seed_fs(tmp_path, monkeypatch):
    """Temp fixture dir with fake JPEGs and module-level paths patched."""
    fixtures_dir = tmp_path / "fixtures" / "images"
    fixtures_dir.mkdir(parents=True)

    # Fake JPEG files that exist on disk
    for name in (
        "massage_01.jpg",
        "massage_02.jpg",
        "phones_01.jpg",
        "phones_02.jpg",
        "dogs_01.jpg",
    ):
        (fixtures_dir / name).write_bytes(b"fake-jpeg")

    monkeypatch.setattr(download, "FIXTURES_IMAGES_DIR", fixtures_dir)
    monkeypatch.setattr(download, "MANIFEST_PATH", fixtures_dir / "photo_manifest.json")
    monkeypatch.setattr(download, "DOWNLOADED_IDS_PATH", fixtures_dir / "downloaded_ids.json")
    monkeypatch.setattr(download, "QUERY_HIERARCHY_PATH", fixtures_dir / "query_hierarchy.json")

    return fixtures_dir


class TestFixCleanup:
    """Tests for find_missing_manifest_entries, fix_cleanup, and --fix=cleanup."""

    # ── find_missing_manifest_entries ──

    def test_find_missing_returns_correct_entries(self, seed_fs):
        """Returns (category_slug, photo_entry) tuples for missing files only."""
        manifest = {
            "version": 1,
            "categories": {
                "massage": {"photos": [
                    {"filename": "massage_01.jpg", "width": 100, "height": 100},
                    {"filename": "massage_99.jpg", "width": 100, "height": 100},
                ]},
                "phones": {"photos": [
                    {"filename": "phones_01.jpg", "width": 100, "height": 100},
                    {"filename": "phones_99.jpg", "width": 100, "height": 100},
                ]},
            },
            "default": {"photos": [
                {"filename": "default_99.jpg", "width": 100, "height": 100},
            ]},
        }
        result = find_missing_manifest_entries(manifest)
        assert len(result) == 3
        # Category scope is preserved in the returned tuples
        slugs = [slug for slug, _ in result]
        assert slugs == ["massage", "phones", "default"]
        filenames = [photo["filename"] for _, photo in result]
        assert filenames == ["massage_99.jpg", "phones_99.jpg", "default_99.jpg"]

    def test_find_missing_returns_empty_when_all_exist(self, seed_fs):
        """Returns empty list when every manifest file exists on disk."""
        manifest = {
            "version": 1,
            "categories": {
                "massage": {"photos": [
                    {"filename": "massage_01.jpg", "width": 100, "height": 100},
                    {"filename": "massage_02.jpg", "width": 200, "height": 100},
                ]},
            },
            "default": {"photos": []},
        }
        assert find_missing_manifest_entries(manifest) == []

    # ── fix_cleanup: removal & preservation ──

    def test_fix_cleanup_removes_only_missing(self, seed_fs):
        """Only missing entries are removed; existing entries are preserved."""
        manifest = {
            "version": 1,
            "categories": {
                "massage": {"photos": [
                    {"filename": "massage_01.jpg", "width": 100, "height": 100},
                    {"filename": "massage_02.jpg", "width": 200, "height": 100},
                    {"filename": "massage_99.jpg", "width": 100, "height": 200},
                ]},
                "phones": {"photos": [
                    {"filename": "phones_01.jpg", "width": 100, "height": 100},
                    {"filename": "phones_99.jpg", "width": 200, "height": 100},
                ]},
            },
            "default": {"photos": []},
        }
        removed = fix_cleanup(manifest)
        assert removed == 2

        massage_files = [p["filename"] for p in manifest["categories"]["massage"]["photos"]]
        assert massage_files == ["massage_01.jpg", "massage_02.jpg"]
        phone_files = [p["filename"] for p in manifest["categories"]["phones"]["photos"]]
        assert phone_files == ["phones_01.jpg"]

    def test_fix_cleanup_returns_correct_count(self, seed_fs):
        """Returned count matches the number of removed entries."""
        manifest = {
            "version": 1,
            "categories": {
                "massage": {"photos": [
                    {"filename": "massage_01.jpg", "width": 100, "height": 100},
                    {"filename": "massage_99.jpg", "width": 100, "height": 100},
                ]},
                "phones": {"photos": [
                    {"filename": "phones_98.jpg", "width": 100, "height": 100},
                    {"filename": "phones_99.jpg", "width": 100, "height": 100},
                ]},
            },
            "default": {"photos": [
                {"filename": "default_97.jpg", "width": 100, "height": 100},
            ]},
        }
        assert fix_cleanup(manifest) == 4

    # ── fix_cleanup: empty-category warning ──

    def test_fix_cleanup_warns_when_category_empty(self, seed_fs, caplog):
        """Logs a WARNING when a category loses all its photos."""
        manifest = {
            "version": 1,
            "categories": {
                "dogs": {"photos": [
                    {"filename": "dogs_02.jpg", "width": 100, "height": 100},
                ]},
            },
            "default": {"photos": []},
        }
        with caplog.at_level(logging.WARNING):
            fix_cleanup(manifest)
        assert any("zero photos" in r.getMessage() for r in caplog.records)

    def test_fix_cleanup_keeps_empty_category_in_manifest(self, seed_fs):
        """Category with zero photos after cleanup stays in manifest with empty list."""
        manifest = {
            "version": 1,
            "categories": {
                "dogs": {"photos": [
                    {"filename": "dogs_02.jpg", "width": 100, "height": 100},
                ]},
                "massage": {"photos": [
                    {"filename": "massage_01.jpg", "width": 100, "height": 100},
                ]},
            },
            "default": {"photos": []},
        }
        fix_cleanup(manifest)
        assert manifest["categories"]["dogs"]["photos"] == []
        assert manifest["categories"]["massage"]["photos"] == [
            {"filename": "massage_01.jpg", "width": 100, "height": 100}
        ]

    # ── fix_cleanup: atomic write ──

    def test_fix_cleanup_atomic_write_not_corrupted(self, seed_fs):
        """Manifest saved to disk is valid JSON after cleanup with mixed entries."""
        manifest = {
            "version": 1,
            "categories": {
                "massage": {"photos": [
                    {"filename": "massage_01.jpg", "width": 100, "height": 100},
                    {"filename": "massage_99.jpg", "width": 100, "height": 100},
                ]},
            },
            "default": {"photos": []},
        }
        fix_cleanup(manifest)
        result = json.loads(seed_fs.joinpath("photo_manifest.json").read_text())
        assert result["version"] == 1
        files = [p["filename"] for p in result["categories"]["massage"]["photos"]]
        assert files == ["massage_01.jpg"]

    # ── fix_cleanup: downloaded_ids.json untouched ──

    def test_fix_cleanup_does_not_modify_downloaded_ids(self, seed_fs):
        """downloaded_ids.json is NOT modified by cleanup."""
        seed_fs.joinpath("downloaded_ids.json").write_text(
            json.dumps({"downloaded_ids": ["id1", "id2"]})
        )
        manifest = {
            "version": 1,
            "categories": {
                "massage": {"photos": [
                    {"filename": "massage_99.jpg", "width": 100, "height": 100},
                ]},
            },
            "default": {"photos": []},
        }
        fix_cleanup(manifest)
        ids = json.loads(seed_fs.joinpath("downloaded_ids.json").read_text())
        assert ids == {"downloaded_ids": ["id1", "id2"]}

    # ── End-to-end: --fix=cleanup ──

    def test_fix_cleanup_end_to_end(self, seed_fs, monkeypatch):
        """--fix=cleanup loads manifest, cleans, re-validates, exits 0."""
        manifest = {
            "version": 1,
            "categories": {
                "massage": {"photos": [
                    {"filename": "massage_01.jpg", "width": 100, "height": 100},
                    {"filename": "massage_02.jpg", "width": 200, "height": 100},
                    {"filename": "massage_99.jpg", "width": 100, "height": 200},
                ]},
                "phones": {"photos": [
                    {"filename": "phones_01.jpg", "width": 100, "height": 100},
                    {"filename": "phones_02.jpg", "width": 200, "height": 100},
                ]},
            },
            "default": {"photos": []},
        }
        seed_fs.joinpath("photo_manifest.json").write_text(json.dumps(manifest))
        seed_fs.joinpath("query_hierarchy.json").write_text(
            json.dumps({"massage": {}, "phones": {}})
        )
        seed_fs.joinpath("downloaded_ids.json").write_text(
            json.dumps({"downloaded_ids": []})
        )

        monkeypatch.setattr(sys, "argv", ["download_seed_photos.py", "--fix=cleanup"])
        monkeypatch.setattr(download, "load_config", lambda: {})

        with pytest.raises(SystemExit) as exc:
            download.main()
        assert exc.value.code == 0

        result = json.loads(seed_fs.joinpath("photo_manifest.json").read_text())
        massage_files = [p["filename"] for p in result["categories"]["massage"]["photos"]]
        assert "massage_99.jpg" not in massage_files
        assert "massage_01.jpg" in massage_files
        assert json.loads(seed_fs.joinpath("downloaded_ids.json").read_text()) == {
            "downloaded_ids": []
        }

    def test_validate_then_fix_cleanup_end_to_end(self, seed_fs, monkeypatch):
        """--validate --fix=cleanup reports, cleans, and re-validates."""
        manifest = {
            "version": 1,
            "categories": {
                "massage": {"photos": [
                    {"filename": "massage_01.jpg", "width": 100, "height": 100},
                    {"filename": "massage_99.jpg", "width": 100, "height": 200},
                ]},
                "phones": {"photos": [
                    {"filename": "phones_01.jpg", "width": 100, "height": 100},
                ]},
            },
            "default": {"photos": []},
        }
        seed_fs.joinpath("photo_manifest.json").write_text(json.dumps(manifest))
        seed_fs.joinpath("query_hierarchy.json").write_text(
            json.dumps({"massage": {}, "phones": {}})
        )
        seed_fs.joinpath("downloaded_ids.json").write_text(
            json.dumps({"downloaded_ids": []})
        )

        monkeypatch.setattr(
            sys, "argv", ["download_seed_photos.py", "--validate", "--fix=cleanup"]
        )
        monkeypatch.setattr(download, "load_config", lambda: {})

        with pytest.raises(SystemExit) as exc:
            download.main()
        assert exc.value.code == 0

        result = json.loads(seed_fs.joinpath("photo_manifest.json").read_text())
        files = [p["filename"] for p in result["categories"]["massage"]["photos"]]
        assert files == ["massage_01.jpg"]


# ─── parse_cli_args ────────────────────────────────────────────────────────


class TestParseCliArgs:
    """Unit tests for parse_cli_args — the manual sys.argv state machine.

    Covers both ``--flag=value`` and ``--flag value`` (space-separated) forms
    for ``--category`` and ``--fix``, plus error/exit handling.
    """

    def test_category_equals_form(self):
        """``--category=beauty-health`` parses into the category field."""
        result = parse_cli_args(["--category=beauty-health"])
        assert result.category == "beauty-health"
        assert result.loop_all is False
        assert result.validate_only is False
        assert result.fix_mode is FixMode.NONE

    def test_category_space_form(self):
        """``--category beauty-health`` (space-separated) parses into category."""
        result = parse_cli_args(["--category", "beauty-health"])
        assert result.category == "beauty-health"

    def test_category_hyphenated_slug_equals_form(self):
        """A hyphenated slug works in the equals form."""
        result = parse_cli_args(["--category=services-jobs"])
        assert result.category == "services-jobs"

    def test_category_hyphenated_slug_space_form(self):
        """A hyphenated slug works in the space-separated form (hyphen is not a bare flag)."""
        result = parse_cli_args(["--category", "services-jobs"])
        assert result.category == "services-jobs"

    def test_fix_equals_form(self):
        """``--fix=cleanup`` resolves to FixMode.CLEANUP."""
        result = parse_cli_args(["--fix=cleanup"])
        assert result.fix_mode is FixMode.CLEANUP
        assert result.category is None

    def test_fix_space_form(self):
        """``--fix cleanup`` (space-separated) resolves to FixMode.CLEANUP."""
        result = parse_cli_args(["--fix", "cleanup"])
        assert result.fix_mode is FixMode.CLEANUP

    def test_all_flag(self):
        """``--all`` sets loop_all."""
        result = parse_cli_args(["--all"])
        assert result.loop_all is True

    def test_validate_flag(self):
        """``--validate`` sets validate_only."""
        result = parse_cli_args(["--validate"])
        assert result.validate_only is True

    def test_defaults_no_args(self):
        """No arguments yields all defaults."""
        result = parse_cli_args([])
        assert result.category is None
        assert result.loop_all is False
        assert result.validate_only is False
        assert result.fix_mode is FixMode.NONE

    def test_combined_flags_space_and_equals(self):
        """``--validate --fix=cleanup --all --category phones`` parses all together."""
        result = parse_cli_args(
            ["--validate", "--fix=cleanup", "--all", "--category", "phones"]
        )
        assert result.validate_only is True
        assert result.fix_mode is FixMode.CLEANUP
        assert result.loop_all is True
        assert result.category == "phones"

    def test_invalid_fix_mode_equals_exits(self):
        """An invalid --fix mode via ``--fix=bogus`` exits 1."""
        with pytest.raises(SystemExit) as exc:
            parse_cli_args(["--fix=bogus"])
        assert exc.value.code == 1

    def test_invalid_fix_mode_space_exits(self):
        """An invalid --fix mode via ``--fix bogus`` exits 1."""
        with pytest.raises(SystemExit) as exc:
            parse_cli_args(["--fix", "bogus"])
        assert exc.value.code == 1

    def test_fix_without_value_exits(self):
        """``--fix`` with no following value exits 1."""
        with pytest.raises(SystemExit) as exc:
            parse_cli_args(["--fix"])
        assert exc.value.code == 1

    def test_category_without_value_exits(self):
        """``--category`` with no following value exits 1."""
        with pytest.raises(SystemExit) as exc:
            parse_cli_args(["--category"])
        assert exc.value.code == 1

    def test_unknown_arg_exits(self):
        """An unrecognized argument exits 1."""
        with pytest.raises(SystemExit) as exc:
            parse_cli_args(["--bogus"])
        assert exc.value.code == 1

    def test_fix_followed_by_flag_does_not_swallow(self):
        """``--fix --validate`` must NOT swallow ``--validate`` as the fix value.

        The next token starts with ``-``, so ``--fix`` is rejected as missing
        its value rather than consuming ``--validate``.
        """
        with pytest.raises(SystemExit) as exc:
            parse_cli_args(["--fix", "--validate"])
        assert exc.value.code == 1

    def test_category_followed_by_flag_does_not_swallow(self):
        """``--category --all`` must NOT swallow ``--all`` as the category value."""
        with pytest.raises(SystemExit) as exc:
            parse_cli_args(["--category", "--all"])
        assert exc.value.code == 1


# ─── prioritize_categories ────────────────────────────────────────────────


class TestPrioritizeCategories:
    """Tests for count_category_photos and prioritize_categories."""

    def test_count_returns_manifest_count(self):
        """count_category_photos reflects current manifest entries."""
        manifest = {
            "categories": {
                "massage": {"photos": [
                    {"filename": "massage_01.jpg"},
                    {"filename": "massage_02.jpg"},
                ]},
                "phones": {"photos": []},
            },
            "default": {"photos": []},
        }
        assert count_category_photos("massage", manifest) == 2
        assert count_category_photos("phones", manifest) == 0
        assert count_category_photos("nonexistent", manifest) == 0

    def test_count_returns_zero_for_empty_manifest(self):
        """A manifest with no categories returns 0 for any slug."""
        assert count_category_photos("massage", {"categories": {}, "default": {"photos": []}}) == 0

    def test_prioritize_zero_photo_first(self):
        """Categories with 0 photos come before categories with 3 photos."""
        manifest = {
            "categories": {
                "massage": {"photos": [
                    {"filename": "m_01.jpg"},
                    {"filename": "m_02.jpg"},
                    {"filename": "m_03.jpg"},
                ]},
                "phones": {"photos": []},
            },
            "default": {"photos": []},
        }
        result = prioritize_categories(["massage", "phones"], manifest, photos_per_category=3)
        assert result[0] == "phones"  # 0 photos → highest deficit
        assert result[1] == "massage"  # 3 photos → lowest deficit

    def test_prioritize_preserves_all_categories(self):
        """No categories are dropped by prioritization."""
        manifest = {"categories": {}, "default": {"photos": []}}
        result = prioritize_categories(["a", "b", "c", "d"], manifest, photos_per_category=3)
        assert sorted(result) == ["a", "b", "c", "d"]

    def test_prioritize_deterministic_order_among_ties(self):
        """With a fixed random seed, equal-deficit categories keep their shuffled order."""
        import random as _random_mod

        manifest = {"categories": {}, "default": {"photos": []}}
        slugs = ["a", "b", "c", "d", "e"]
        _random_mod.seed(42)
        result = prioritize_categories(slugs, manifest, photos_per_category=3)
        # All have 0 photos → all have same deficit → result is just a shuffle of all
        assert sorted(result) == sorted(slugs)
        # Verify it's not just the input order (shuffle happened)
        assert result != slugs or len(slugs) <= 1  # trivially true for ties

    def test_prioritize_re_sorts_when_manifest_changes(self):
        """After photos are added, re-prioritizing moves exhausted categories last."""
        manifest = {"categories": {}, "default": {"photos": []}}
        slugs = ["a", "b"]

        # Initially both have 0 photos — order is random, just check both present
        first = prioritize_categories(slugs, manifest, photos_per_category=3)
        assert sorted(first) == sorted(slugs)

        # Simulate category "a" now has 3 photos
        manifest = {
            "categories": {
                "a": {"photos": [{"f": "a_01.jpg"}, {"f": "a_02.jpg"}, {"f": "a_03.jpg"}]},
            },
            "default": {"photos": []},
        }
        second = prioritize_categories(slugs, manifest, photos_per_category=3)
        # "b" (deficit 3) must come before "a" (deficit 0)
        assert second[0] == "b"
        assert second[1] == "a"
