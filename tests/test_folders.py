import configparser
from loguru import logger

from api import CollectionUpdateResult
import app
from functions import determine_rule_type
from planner import plan_query


class FolderCandidateAPI:
    def __init__(self):
        self.query = None
        self.updated_ids = None

    def Libraries(self):
        return [{"Id": "home", "Name": "Home Videos & Photos"}]

    def iter_library_content(self, library_id, params=None, fields=None):
        self.query = dict(params or {})
        yield [
            {"Id": "folder", "Name": "Harbor Folder", "IsFolder": True},
            {"Id": "photo", "Name": "Harbor Photo", "IsFolder": False, "Type": "Photo", "MediaType": "Photo"},
            {"Id": "video", "Name": "Harbor Home Video", "IsFolder": False, "Type": "Video", "MediaType": "Video"},
            {"Id": "other", "Name": "Unrelated Folder", "IsFolder": True},
        ], 4, 4

    def update_collection(self, name, ids):
        self.updated_ids = set(ids)
        return CollectionUpdateResult(name, "collection", False, len(ids), len(ids), 0)


def run_rule(monkeypatch, include_video=None, include_folders=None, include_photos=None):
    fake = FolderCandidateAPI()
    monkeypatch.setattr(app, "emby_api", fake)
    values = {"Name": "*harbor*", "DryRun": "false"}
    if include_video is not None:
        values["IncludeVideo"] = include_video
    if include_folders is not None:
        values["IncludeFolders"] = include_folders
    if include_photos is not None:
        values["IncludePhotos"] = include_photos
    config = configparser.ConfigParser()
    config.read_dict({"Test Home Videos": values})
    app.main(config)
    return fake


def test_folder_and_photo_options_omitted_default_to_false(monkeypatch):
    fake = run_rule(monkeypatch)
    assert fake.updated_ids == {"video"}


def test_include_folders_false_excludes_matching_folder(monkeypatch):
    fake = run_rule(monkeypatch, include_folders="false")
    assert fake.updated_ids == {"video"}


def test_include_folders_true_allows_matching_folder(monkeypatch):
    fake = run_rule(monkeypatch, include_folders="true")
    assert fake.updated_ids == {"folder", "video"}


def test_include_photos_false_excludes_matching_photo(monkeypatch):
    fake = run_rule(monkeypatch, include_photos="false")
    assert fake.updated_ids == {"video"}


def test_include_photos_true_allows_matching_photo(monkeypatch):
    fake = run_rule(monkeypatch, include_photos="true")
    assert fake.updated_ids == {"photo", "video"}


def test_home_video_remains_included_and_search_term_is_preserved(monkeypatch):
    fake = run_rule(monkeypatch, include_folders="false")
    assert "video" in fake.updated_ids
    assert fake.query["SearchTerm"] == "harbor"
    assert not any(key.casefold() == "includefolders" for key in fake.query)


def test_photo_only_rule(monkeypatch):
    fake = run_rule(
        monkeypatch, include_video="false", include_folders="false", include_photos="true"
    )
    assert fake.updated_ids == {"photo"}


def test_folder_only_rule(monkeypatch):
    fake = run_rule(
        monkeypatch, include_video="false", include_folders="true", include_photos="false"
    )
    assert fake.updated_ids == {"folder"}


def test_mixed_rule(monkeypatch):
    fake = run_rule(
        monkeypatch, include_video="true", include_folders="true", include_photos="true"
    )
    assert fake.updated_ids == {"video", "folder", "photo"}


def test_video_can_be_excluded(monkeypatch):
    fake = run_rule(
        monkeypatch, include_video="false", include_folders="false", include_photos="true"
    )
    assert "video" not in fake.updated_ids


def test_all_content_options_false_logs_error_and_prevents_synchronization(monkeypatch):
    messages = []
    sink = logger.add(lambda message: messages.append(str(message)), format="{message}")
    try:
        fake = run_rule(
            monkeypatch, include_video="false", include_folders="false", include_photos="false"
        )
    finally:
        logger.remove(sink)
    assert fake.query is None
    assert fake.updated_ids is None
    assert "cannot all be false" in "".join(messages)


def test_content_switches_are_behavior_not_emby_parameters():
    rules = determine_rule_type([
        ("Name", "*harbor*"), ("IncludeVideo", "true"),
        ("IncludeFolders", "true"), ("IncludePhotos", "true")
    ])
    plan = plan_query(rules)
    assert rules["behaviour"]["includefolders"] == "true"
    assert rules["behaviour"]["includephotos"] == "true"
    assert "IncludeFolders" not in plan.params
    assert "IncludePhotos" not in plan.params
    assert rules["behaviour"]["includevideo"] == "true"
    assert "IncludeVideo" not in plan.params
