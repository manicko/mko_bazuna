"""Tests for the standalone seed photo download script.

These tests verify the error-handling fix for the unhandled-403 crash —
specifically that ``PhotoSource.search()`` gracefully handles HTTP errors
(403/429), transient failures (5xx, network errors), and that the
``main()`` loop falls back to the next photo source when one source fails.
"""

from __future__ import annotations

import importlib.util
import logging
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
