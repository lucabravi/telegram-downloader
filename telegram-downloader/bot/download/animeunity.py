import logging
import re
from dataclasses import dataclass
from html import unescape
from urllib.parse import parse_qs, unquote, urlparse

import requests


ANIMEUNITY_URL_PATTERN = re.compile(
    r"https?://(?:www\.)?animeunity\.[^/\s]+/anime/\d+-[^\s/?#]+(?:[^\s]*)?",
    re.IGNORECASE,
)
DOWNLOAD_URL_PATTERN = re.compile(
    r"window\.downloadUrl\s*=\s*['\"](?P<url>https?://[^'\"]+)['\"]",
    re.IGNORECASE,
)
TITLE_TAG_PATTERN = re.compile(r"<title[^>]*>(?P<title>.*?)</title>", re.IGNORECASE | re.DOTALL)
OG_TITLE_PATTERN = re.compile(
    r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\'](?P<title>[^"\']+)["\']',
    re.IGNORECASE,
)
FILE_SEASON_PATTERN = re.compile(r"\bS0*(\d{1,2})E\d{1,4}\b", re.IGNORECASE)
TITLE_SEASON_PATTERN = re.compile(r"(?:season|stagione)\s*0*(\d{1,2})", re.IGNORECASE)
TRAILING_TITLE_SEASON_PATTERN = re.compile(
    r"^(?P<base>.*?)(?:\s+|[-:|~]\s*)(?:season|stagione)\s*0*(?P<season>\d{1,2})\s*$",
    re.IGNORECASE,
)
BATCH_SIZE = 120
REQUEST_TIMEOUT = 20

DEFAULT_HEADERS = {
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9,it;q=0.8",
    "Connection": "keep-alive",
    "DNT": "1",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
}


class AnimeUnityError(RuntimeError):
    pass


@dataclass(frozen=True)
class EpisodeDownload:
    episode_id: int
    episode_number: str
    filename: str
    download_url: str
    season_number: int | None = None


def extract_animeunity_url(text: str | None) -> str | None:
    if not text:
        return None
    match = ANIMEUNITY_URL_PATTERN.search(text)
    if not match:
        return None
    return match.group(0).rstrip(").,;")


def resolve_animeunity_downloads(url: str) -> tuple[str, list[EpisodeDownload]]:
    host, anime_slug, canonical_url = _parse_anime_url(url)
    info_api_url = f"https://{host}/info_api/{anime_slug}"

    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)

    anime_page_html = None
    try:
        anime_page_html = _fetch_text(session, canonical_url)
    except AnimeUnityError as exc:
        logging.warning(f"Could not fetch anime page title from {canonical_url}: {exc}")

    anime_info = _fetch_json(session, info_api_url)
    title_from_page = _extract_anime_name_from_html(anime_page_html)
    anime_name = (
        title_from_page
        or anime_info.get("title")
        or anime_info.get("title_eng")
        or anime_slug.split("-", 1)[-1].replace("-", " ").title()
    )
    default_season = _extract_season_number(anime_name)
    episodes_count = int(anime_info.get("episodes_count") or 0)
    if episodes_count <= 0:
        raise AnimeUnityError("No episodes found for this AnimeUnity URL.")

    episode_infos = _fetch_episode_infos(session, info_api_url, episodes_count)
    if not episode_infos:
        raise AnimeUnityError("Unable to collect episode metadata from AnimeUnity.")

    downloads = []
    for episode in episode_infos:
        episode_id = episode.get("id")
        if not episode_id:
            continue
        episode_number = str(episode.get("number", "?"))
        candidate_filename = (
            episode.get("file_name")
            or episode.get("link")
            or f"episode-{episode_number}.mp4"
        )
        download_url = _resolve_episode_download_url(
            session=session,
            host=host,
            episode_id=int(episode_id),
            fallback_link=str(episode.get("link") or ""),
        )
        if not download_url:
            logging.warning(f"Skipping episode {episode_id}: unable to resolve download URL")
            continue
        filename = _derive_filename(download_url, str(candidate_filename), episode_number)
        season_number = _extract_season_number(str(candidate_filename)) or default_season
        downloads.append(EpisodeDownload(
            episode_id=int(episode_id),
            episode_number=episode_number,
            filename=filename,
            download_url=download_url,
            season_number=season_number,
        ))

    if not downloads:
        raise AnimeUnityError("Could not resolve direct download links for any episode.")

    return anime_name, downloads


def refresh_animeunity_download_url(host: str, episode_id: int, fallback_link: str = "") -> str:
    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)
    download_url = _resolve_episode_download_url(
        session=session,
        host=host,
        episode_id=episode_id,
        fallback_link=fallback_link,
    )
    if not download_url:
        raise AnimeUnityError(f"Could not refresh direct download URL for episode {episode_id}.")
    return download_url


def split_series_and_trailing_season(title: str | None) -> tuple[str | None, int | None]:
    """Split titles like 'Kamisama Kiss Season 2' into ('Kamisama Kiss', 2)."""
    if title is None:
        return None, None

    cleaned = re.sub(r"\s+", " ", title).strip(" -|~")
    if not cleaned:
        return None, None

    match = TRAILING_TITLE_SEASON_PATTERN.match(cleaned)
    if not match:
        return cleaned, None

    base = match.group("base").strip(" -|~")
    season = int(match.group("season"))
    if not base:
        return cleaned, season
    return base, season


def _fetch_episode_infos(session: requests.Session, info_api_url: str, episodes_count: int) -> list[dict]:
    episode_api_url = f"{info_api_url}/0"
    all_episodes: list[dict] = []
    end_range = episodes_count + 1

    for batch_start in range(0, end_range, BATCH_SIZE):
        batch_end = min(batch_start + BATCH_SIZE - 1, end_range)
        payload = _fetch_json(
            session,
            episode_api_url,
            params={"start_range": batch_start, "end_range": batch_end},
        )
        all_episodes.extend(payload.get("episodes", []))

    return sorted(all_episodes, key=lambda ep: _safe_episode_number(ep.get("number")))


def _resolve_episode_download_url(
    session: requests.Session,
    host: str,
    episode_id: int,
    fallback_link: str,
) -> str | None:
    embed_url_endpoint = f"https://{host}/embed-url/{episode_id}"
    embed_url = _fetch_text(session, embed_url_endpoint).strip()
    if embed_url.startswith("//"):
        embed_url = f"https:{embed_url}"

    if embed_url.lower().startswith("http"):
        try:
            html = _fetch_text(session, embed_url)
            match = DOWNLOAD_URL_PATTERN.search(html)
            if match:
                return match.group("url")
        except AnimeUnityError:
            pass

    if fallback_link.lower().startswith("http"):
        return fallback_link

    return None


def _derive_filename(download_url: str, fallback_name: str, episode_number: str) -> str:
    parsed = urlparse(download_url)
    query = parse_qs(parsed.query or "")
    filename = query.get("filename", [None])[0]
    if filename:
        return _add_animeunity_suffix(_sanitize_filename(unquote(filename)))
    if fallback_name and "." in fallback_name:
        return _add_animeunity_suffix(_sanitize_filename(fallback_name))
    return _add_animeunity_suffix(_sanitize_filename(f"episode-{episode_number}.mp4"))


def _parse_anime_url(url: str) -> tuple[str, str, str]:
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https"):
        raise AnimeUnityError("Only http/https AnimeUnity URLs are supported.")
    if "animeunity" not in parsed.netloc.lower():
        raise AnimeUnityError("The URL is not an AnimeUnity URL.")

    match = re.match(r"^/anime/(\d+-[^/?#]+)", parsed.path)
    if not match:
        raise AnimeUnityError("Invalid AnimeUnity URL. Expected /anime/<id>-<slug>.")

    anime_slug = match.group(1)
    canonical = f"https://{parsed.netloc}/anime/{anime_slug}"
    return parsed.netloc, anime_slug, canonical


def _extract_anime_name_from_html(html: str | None) -> str | None:
    if not html:
        return None

    title_match = TITLE_TAG_PATTERN.search(html)
    if title_match:
        title_text = unescape(re.sub(r"\s+", " ", title_match.group("title"))).strip()
        if title_text:
            if "AnimeUnity ~" in title_text:
                cleaned = title_text.split("AnimeUnity ~", 1)[1]
                if "Streaming" in cleaned:
                    cleaned = cleaned.split("Streaming", 1)[0]
                cleaned = cleaned.strip(" ~-|")
            else:
                cleaned = title_text.replace("AnimeUnity", "").replace("~", "").strip(" -|")
            if cleaned:
                return cleaned

    og_match = OG_TITLE_PATTERN.search(html)
    if og_match:
        title_text = unescape(og_match.group("title")).strip()
        if title_text:
            return title_text

    return None


def _extract_season_number(text: str | None) -> int | None:
    if not text:
        return None
    file_match = FILE_SEASON_PATTERN.search(text)
    if file_match:
        return int(file_match.group(1))
    title_match = TITLE_SEASON_PATTERN.search(text)
    if title_match:
        return int(title_match.group(1))
    return None


def _fetch_json(session: requests.Session, url: str, params: dict | None = None) -> dict:
    try:
        response = session.get(url, params=params, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        raise AnimeUnityError(f"Request failed for {url}: {exc}") from exc


def _fetch_text(session: requests.Session, url: str) -> str:
    try:
        response = session.get(url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        return response.text
    except Exception as exc:
        raise AnimeUnityError(f"Request failed for {url}: {exc}") from exc


def _safe_episode_number(value: str | int | float | None) -> tuple[int, float]:
    if value is None:
        return 1, 0.0
    try:
        return 0, float(value)
    except Exception:
        return 1, 0.0


def _sanitize_filename(name: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*]', '', name or '')
    cleaned = re.sub(r' +', ' ', cleaned).strip()
    return cleaned or "episode.mp4"


def _add_animeunity_suffix(filename: str) -> str:
    tag = "[AnimeUnity]"
    if tag in filename:
        return filename
    if "." not in filename:
        return f"{filename} {tag}"

    base, extension = filename.rsplit(".", 1)
    if not base:
        return filename
    return f"{base} {tag}.{extension}"
