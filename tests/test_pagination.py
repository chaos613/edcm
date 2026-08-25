import configparser
import requests
import pytest
from loguru import logger
from api import api, EmbyAPIError
import app

BASE = "http://emby:8096/emby"


def test_multi_page_with_final_partial_page(requests_mock):
    requests_mock.get(f"{BASE}/Items", [
        {"json": {"Items": [{"Id":"1"},{"Id":"2"}], "TotalRecordCount": 5}},
        {"json": {"Items": [{"Id":"3"},{"Id":"4"}], "TotalRecordCount": 5}},
        {"json": {"Items": [{"Id":"5"}], "TotalRecordCount": 5}},
    ])
    pages = list(api("http://emby:8096", "token", page_size=2).iter_library_content("lib", fields={"Genres"}))
    assert [(len(items), done, total) for items, done, total in pages] == [(2,2,5),(2,4,5),(1,5,5)]
    assert [request.qs["startindex"] for request in requests_mock.request_history] == [["0"],["2"],["4"]]
    assert all(request.qs["limit"] == ["2"] for request in requests_mock.request_history)
    assert all(request.qs["recursive"] == ["true"] for request in requests_mock.request_history)
    assert requests_mock.last_request.qs["fields"][0].casefold() == "genres"


def test_filtered_results_remain_filtered_across_pages(requests_mock):
    requests_mock.get(f"{BASE}/Items", [
        {"json": {"Items": [{"Id": "1"}], "TotalRecordCount": 2}},
        {"json": {"Items": [{"Id": "2"}], "TotalRecordCount": 2}},
    ])
    pages = list(api("http://emby:8096", "token", page_size=1).iter_library_content(
        "lib", params={"SearchTerm": "harbor", "Genres": "Documentary"}
    ))
    assert len(pages) == 2
    for request in requests_mock.request_history:
        assert request.qs["searchterm"] == ["harbor"]
        assert request.qs["genres"] == ["Documentary".casefold()]


def test_zero_item_library(requests_mock):
    requests_mock.get(f"{BASE}/Items", json={"Items": [], "TotalRecordCount": 0})
    assert list(api("http://emby:8096", "token").iter_library_content("empty")) == []
    assert len(requests_mock.request_history) == 1


def test_timeout_midway_raises_and_stops(requests_mock):
    requests_mock.get(f"{BASE}/Items", [
        {"json": {"Items": [{"Id":"1"},{"Id":"2"}], "TotalRecordCount": 4}},
        {"exc": requests.exceptions.ReadTimeout("timed out")},
    ])
    iterator = api("http://emby:8096", "token", page_size=2).iter_library_content("lib")
    assert next(iterator)[1:] == (2, 4)
    with pytest.raises(EmbyAPIError, match="timed out"):
        next(iterator)


class TimeoutAPI:
    def __init__(self): self.updated = False; self.params = None
    def Libraries(self): return [{"Id":"lib", "Name":"Storage"}]
    def iter_library_content(self, *args, **kwargs):
        self.params = kwargs.get("params")
        yield [{"Id":"1", "Name":"secret harbor title", "Path":"/secret/media"}], 1, 2
        raise EmbyAPIError("GET", "Items", "timed out")
    def update_collection(self, *args): self.updated = True


def test_mid_scan_timeout_never_synchronizes_or_logs_item_data(monkeypatch):
    fake = TimeoutAPI()
    monkeypatch.setattr(app, "emby_api", fake)
    config = configparser.ConfigParser()
    config.read_dict({"Harbors": {"Name": "*harbor*"}})
    messages = []
    sink = logger.add(lambda message: messages.append(str(message)), format="{message}")
    try: app.main(config)
    finally: logger.remove(sink)
    assert fake.updated is False
    assert fake.params["SearchTerm"] == "harbor"
    output = "".join(messages)
    assert "secret harbor title" not in output
    assert "/secret/media" not in output
    assert "collection left unchanged" in output
