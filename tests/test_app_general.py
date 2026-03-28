from conftest import load_bot_modules


def test_virtual_filesystem_blocks_escape_and_sorts_case_insensitively(tmp_path):
    manage_path = load_bot_modules("manage_path")["manage_path"]

    (tmp_path / "Zoo").mkdir()
    (tmp_path / "alpha").mkdir()
    (tmp_path / "Beta.txt").write_text("b", encoding="utf-8")
    (tmp_path / "aardvark.txt").write_text("a", encoding="utf-8")

    vfs = manage_path.VirtualFileSystem(root=str(tmp_path))
    directories, files = vfs.ls()

    assert directories == ["alpha", "Zoo"]
    assert files == ["aardvark.txt", "Beta.txt"]

    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir(exist_ok=True)
    ok, info = vfs.cd(f"../{outside.name}")
    assert ok is False
    assert info == "Cannot go beyond the virtual root directory"


def test_cleanup_path_name_removes_invalid_chars_and_extra_spaces():
    manage_path = load_bot_modules("manage_path")["manage_path"]

    cleaned = manage_path.VirtualFileSystem.cleanup_path_name('  My<>:"/\\\\|?*   Folder   Name  ')

    assert cleaned == "My Folder Name"


def test_split_message_preserves_line_boundaries():
    commands = load_bot_modules("commands")["commands"]

    chunks = commands._split_message("12345\n67890\nabcde", max_len=13)

    assert chunks == ["12345\n67890", "abcde"]


def test_handler_filename_helpers_cover_standard_and_ova_cases():
    handler = load_bot_modules("download.handler")["download.handler"]

    assert handler.find_correct_filename("video.mkv", "S2 Ep03", "chat") == "S02E003.mkv"
    assert handler.find_correct_filename("video.mkv", "S1 OVA2", "chat") == "S01OVA002.mkv"
    assert handler.find_correct_filename("plain-video.mkv", "no numbering here", "chat") == "plain-video.mkv"
    assert handler._season_folder_name(None) == "Season 01"
    assert handler._season_folder_name(2) == "Season 02"


def test_build_unique_filename_appends_incrementing_suffix():
    handler = load_bot_modules("download.handler")["download.handler"]

    seen = set()
    first = handler._build_unique_filename("Episode 01.mkv", seen)
    second = handler._build_unique_filename("Episode 01.mkv", seen)
    third = handler._build_unique_filename("Episode 01.mkv", seen)

    assert first == "Episode 01.mkv"
    assert second == "Episode 01_2.mkv"
    assert third == "Episode 01_3.mkv"
