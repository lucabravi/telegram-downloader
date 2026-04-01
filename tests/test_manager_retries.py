import asyncio
from types import SimpleNamespace

from conftest import load_download_modules


def _make_download(download_type, **overrides):
    data = {
        "id": 1,
        "filename": "episode.mp4",
        "filepath": "anime/Season 01/episode.mp4",
        "from_message": SimpleNamespace(chat=SimpleNamespace(id=123)),
        "added": 0.0,
        "source": "direct_url",
        "source_url": "https://expired.example/video.mp4",
        "animeunity_anime_url": "https://www.animeunity.so/anime/1234-sample-anime",
        "animeunity_episode_id": 555,
        "animeunity_episode_number": "10",
    }
    data.update(overrides)
    return download_type.Download(**data)


def test_refresh_animeunity_source_url_uses_series_metadata(monkeypatch):
    modules = load_download_modules()
    manager = modules["manager"]
    download_type = modules["type"]

    calls = []

    def fake_refresh(anime_url, episode_id, episode_number):
        calls.append((anime_url, episode_id, episode_number))
        return "https://fresh.example/video.mp4", 999

    monkeypatch.setattr(manager, "refresh_animeunity_download_url", fake_refresh)

    download = _make_download(download_type)
    refreshed = asyncio.run(manager._refresh_animeunity_source_url(download))

    assert refreshed is True
    assert calls == [("https://www.animeunity.so/anime/1234-sample-anime", 555, "10")]
    assert download.source_url == "https://fresh.example/video.mp4"
    assert download.animeunity_episode_id == 999


def test_run_direct_download_with_retries_refreshes_source_before_retry(monkeypatch):
    modules = load_download_modules()
    manager = modules["manager"]
    download_type = modules["type"]

    attempts = []

    def fake_direct_download_sync(download, file_path):
        attempts.append(download.source_url)
        if len(attempts) == 1:
            return manager.DirectDownloadResult(
                status="error",
                error="503 Server Error",
                retryable=True,
            )
        return manager.DirectDownloadResult(status="completed")

    async def fake_to_thread(function, *args, **kwargs):
        return function(*args, **kwargs)

    refreshed_urls = []

    async def fake_refresh(download):
        refreshed_urls.append(download.source_url)
        download.source_url = "https://fresh.example/video.mp4"
        return True

    async def fake_wait_for_retry_or_stop(download, delay):
        return True

    monkeypatch.setattr(manager, "_download_direct_url_sync", fake_direct_download_sync)
    monkeypatch.setattr(manager.asyncio, "to_thread", fake_to_thread)
    monkeypatch.setattr(manager, "_refresh_animeunity_source_url", fake_refresh)
    monkeypatch.setattr(manager, "_wait_for_retry_or_stop", fake_wait_for_retry_or_stop)
    monkeypatch.setattr(manager, "_direct_url_is_expiring_soon", lambda url: False)
    monkeypatch.setattr(manager.os, "remove", lambda path: None)

    download = _make_download(download_type)
    result = asyncio.run(manager._run_direct_download_with_retries(download, "/tmp/episode.mp4"))

    assert result.status == "completed"
    assert attempts == [
        "https://expired.example/video.mp4",
        "https://fresh.example/video.mp4",
    ]
    assert refreshed_urls == ["https://expired.example/video.mp4"]
    assert download.retry_attempts == 1


def test_wait_for_telegram_output_file_uses_returned_result_path(monkeypatch, tmp_path):
    modules = load_download_modules()
    manager = modules["manager"]
    download_type = modules["type"]

    download = _make_download(download_type, source="telegram", source_url=None)
    expected_path = tmp_path / "expected.mp4"
    actual_path = tmp_path / "actual.mp4"

    async def fake_sleep(_delay):
        if not actual_path.exists():
            actual_path.write_bytes(b"telegram-data")

    monkeypatch.setattr(manager.asyncio, "sleep", fake_sleep)

    resolved_path, final_size = asyncio.run(
        manager._wait_for_telegram_output_file(download, str(actual_path), str(expected_path))
    )

    assert resolved_path == str(actual_path)
    assert final_size == len(b"telegram-data")


def test_download_file_telegram_fallback_finalizes_when_result_path_is_readable(monkeypatch, tmp_path):
    modules = load_download_modules()
    manager = modules["manager"]
    download_type = modules["type"]

    manager.BASE_FOLDER = str(tmp_path)
    manager.running = 1
    manager.active_downloads.clear()

    captured = {}
    download_media_kwargs = {}
    output_path = tmp_path / "telegram-output.bin"
    output_path.write_bytes(b"payload")

    async def fake_enqueue_edit_when_ready(*_args, **_kwargs):
        return None

    async def fake_finalize(download, text, outcome="completed"):
        captured["outcome"] = outcome
        captured["text"] = text
        download.finalized = True

    async def fake_wait_for_output(download, download_result, requested_path):
        return str(output_path), output_path.stat().st_size

    def fake_download_media(**_kwargs):
        download_media_kwargs.update(_kwargs)
        async def runner():
            return str(output_path)
        return runner()

    monkeypatch.setattr(manager, "_enqueue_edit_when_ready", fake_enqueue_edit_when_ready)
    monkeypatch.setattr(manager, "_finalize_download", fake_finalize)
    monkeypatch.setattr(manager, "_wait_for_telegram_output_file", fake_wait_for_output)
    monkeypatch.setattr(manager.app, "download_media", fake_download_media, raising=False)

    download = _make_download(
        download_type,
        source="telegram",
        source_url=None,
        filepath="folder/episode.bin",
    )

    asyncio.run(manager.download_file(download))

    assert captured["outcome"] == "completed"
    assert "File downloaded" in captured["text"]
    assert download_media_kwargs["block"] is True
    assert manager.running == 0
