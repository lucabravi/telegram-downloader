from conftest import load_download_modules


def test_refresh_animeunity_download_url_reloads_episode_from_series_metadata(monkeypatch):
    animeunity = load_download_modules()["animeunity"]

    monkeypatch.setattr(
        animeunity,
        "_fetch_json",
        lambda session, url, params=None: {"episodes_count": 24},
    )
    monkeypatch.setattr(
        animeunity,
        "_fetch_episode_infos",
        lambda session, info_api_url, episodes_count: [
            {"id": 9876, "number": "10", "link": "https://fresh.example/embed"},
        ],
    )

    captured = {}

    def fake_resolve_episode_download_url(session, host, episode_id, fallback_link):
        captured["host"] = host
        captured["episode_id"] = episode_id
        captured["fallback_link"] = fallback_link
        return "https://cdn.example/video.mp4?filename=Episode10.mp4"

    monkeypatch.setattr(animeunity, "_resolve_episode_download_url", fake_resolve_episode_download_url)

    source_url, refreshed_episode_id = animeunity.refresh_animeunity_download_url(
        "https://www.animeunity.so/anime/1234-sample-anime",
        episode_id=1111,
        episode_number="10",
    )

    assert source_url == "https://cdn.example/video.mp4?filename=Episode10.mp4"
    assert refreshed_episode_id == 9876
    assert captured == {
        "host": "www.animeunity.so",
        "episode_id": 9876,
        "fallback_link": "https://fresh.example/embed",
    }


def test_refresh_animeunity_download_url_falls_back_to_episode_number_when_id_is_stale(monkeypatch):
    animeunity = load_download_modules()["animeunity"]

    monkeypatch.setattr(
        animeunity,
        "_fetch_json",
        lambda session, url, params=None: {"episodes_count": 12},
    )
    monkeypatch.setattr(
        animeunity,
        "_fetch_episode_infos",
        lambda session, info_api_url, episodes_count: [
            {"id": 2222, "number": "9.5", "link": "https://fresh.example/95"},
        ],
    )
    monkeypatch.setattr(
        animeunity,
        "_resolve_episode_download_url",
        lambda session, host, episode_id, fallback_link: f"https://cdn.example/{episode_id}.mp4",
    )

    source_url, refreshed_episode_id = animeunity.refresh_animeunity_download_url(
        "https://www.animeunity.so/anime/9999-sample-anime",
        episode_id=4444,
        episode_number="9.5",
    )

    assert source_url == "https://cdn.example/2222.mp4"
    assert refreshed_episode_id == 2222
