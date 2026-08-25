import pytest
from api import api, EmbyAPIError

def test_recursive_library_query(requests_mock):
    requests_mock.get("http://emby:8096/emby/Items", json={"Items": []})
    api("http://emby:8096", "token").LibraryContent("library")
    assert requests_mock.last_request.qs["recursive"] == ["true"]
    assert requests_mock.last_request.qs["parentid"] == ["library"]

def test_401_is_meaningful(requests_mock):
    requests_mock.get("http://emby:8096/emby/Library/MediaFolders", status_code=401, text="Unauthorized")
    with pytest.raises(EmbyAPIError, match="HTTP 401"):
        api("http://emby:8096", "bad").Libraries()

def test_sync_adds_and_removes(requests_mock):
    base = "http://emby:8096/emby"
    requests_mock.get(f"{base}/Items", [{"json":{"Items":[{"Id":"c","Name":"Dynamic"}]}}, {"json":{"Items":[{"Id":"keep"},{"Id":"old"}]}}])
    requests_mock.post(f"{base}/Collections/c/Items", status_code=204)
    requests_mock.post(f"{base}/Collections/c/Items/Delete", status_code=204)
    result = api("http://emby:8096", "token").update_collection("Dynamic", ["keep", "new"])
    assert (result.added, result.removed, result.created) == (1, 1, False)
    assert requests_mock.request_history[-2].qs["ids"] == ["new"]
    assert requests_mock.request_history[-1].qs["ids"] == ["old"]

def test_create_collection(requests_mock):
    base = "http://emby:8096/emby"
    requests_mock.get(f"{base}/Items", json={"Items":[]})
    requests_mock.post(f"{base}/Collections", json={"Id":"created"})
    result = api("http://emby:8096", "token").update_collection("New", ["one"])
    assert result.created and result.collection_id == "created"
