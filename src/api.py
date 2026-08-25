from dataclasses import dataclass
import requests
from loguru import logger


class EmbyAPIError(RuntimeError):
    def __init__(self, method, endpoint, message, status_code=None):
        self.status_code = status_code
        status = f" (HTTP {status_code})" if status_code else ""
        super().__init__(f"Emby API {method} {endpoint} failed{status}: {message}")


@dataclass(frozen=True)
class CollectionUpdateResult:
    name: str
    collection_id: str
    created: bool
    matched: int
    added: int
    removed: int


class api:
    def __init__(self, base_url, api_token, timeout=30, page_size=2000, session=None):
        if timeout <= 0 or page_size <= 0:
            raise ValueError("timeout and page_size must be positive")
        self.base_url = f"{base_url.rstrip('/')}/emby"
        self.api_token = api_token
        self.timeout = timeout
        self.page_size = page_size
        self.session = session or requests.Session()

    def _send_request(self, endpoint, method="GET", params=None, stripItems=True):
        method, endpoint = method.upper(), endpoint.lstrip("/")
        query = dict(params or {})
        query["api_key"] = self.api_token
        try:
            response = self.session.request(
                method, f"{self.base_url}/{endpoint}", params=query, timeout=self.timeout
            )
        except requests.RequestException as exc:
            logger.error("Emby API {} {} connection error: {}", method, endpoint, exc)
            raise EmbyAPIError(method, endpoint, str(exc)) from exc
        if not 200 <= response.status_code < 300:
            detail = response.text.strip()[:500] or response.reason or "unknown error"
            logger.error(
                "Emby API {} {} returned HTTP {}: {}",
                method, endpoint, response.status_code, detail,
            )
            raise EmbyAPIError(method, endpoint, detail, response.status_code)
        if response.status_code == 204 or not response.content:
            payload = {}
        else:
            try:
                payload = response.json()
            except ValueError as exc:
                raise EmbyAPIError(method, endpoint, "invalid JSON response") from exc
        if stripItems:
            if not isinstance(payload, dict) or not isinstance(payload.get("Items"), list):
                raise EmbyAPIError(method, endpoint, "response did not contain an Items list")
            return payload["Items"]
        return payload

    def Items(self, method="GET", params=None):
        return self._send_request("Items", method, params)

    def Libraries(self, method="GET", params=None):
        return self._send_request("Library/MediaFolders", method, params)

    def iter_library_content(self, library_id, params=None, fields=None):
        """Yield (page items, retrieved count, total count) without retaining pages."""
        base_query = dict(params or {})
        base_query.update({"ParentId": library_id, "Recursive": "true"})
        requested_fields = {value for value in (fields or ()) if value}
        requested_fields.update(
            value.strip() for value in base_query.get("Fields", "").split(",") if value.strip()
        )
        if requested_fields:
            base_query["Fields"] = ",".join(sorted(requested_fields))
        else:
            base_query.pop("Fields", None)

        start_index = 0
        total = None
        while total is None or start_index < total:
            query = dict(base_query)
            query.update({"StartIndex": start_index, "Limit": self.page_size})
            payload = self._send_request("Items", params=query, stripItems=False)
            items = payload.get("Items") if isinstance(payload, dict) else None
            if not isinstance(items, list):
                raise EmbyAPIError("GET", "Items", "response did not contain an Items list")
            reported_total = payload.get("TotalRecordCount", len(items) if total is None else total)
            try:
                total = int(reported_total)
            except (TypeError, ValueError) as exc:
                raise EmbyAPIError("GET", "Items", "invalid TotalRecordCount") from exc
            if not items:
                if start_index < total:
                    raise EmbyAPIError("GET", "Items", "empty page before TotalRecordCount was reached")
                break
            start_index += len(items)
            yield items, start_index, total
            if len(items) < self.page_size and start_index >= total:
                break

    def LibraryContent(self, library_id, method="GET", params=None):
        """Compatibility helper. New scans should use iter_library_content."""
        if method.upper() != "GET":
            raise ValueError("LibraryContent only supports GET")
        return [item for page, _, _ in self.iter_library_content(library_id, params) for item in page]

    def find_collection(self, name):
        items = self.Items(params={"IncludeItemTypes": "BoxSet", "Recursive": "true"})
        return next((item for item in items if item.get("Name") == name), None)

    def collection_items(self, collection_id):
        return self.Items(params={"ParentId": collection_id, "Recursive": "false"})

    def _change(self, collection_id, ids, remove=False):
        ids = list(ids)
        endpoint = f"Collections/{collection_id}/Items" + ("/Delete" if remove else "")
        for offset in range(0, len(ids), 100):
            self._send_request(
                endpoint, "POST", {"Ids": ",".join(ids[offset:offset + 100])}, False
            )

    def update_collection(self, name, ids):
        desired = list(dict.fromkeys(str(value) for value in ids if value))
        collection = self.find_collection(name)
        if collection is None:
            response = self._send_request(
                "Collections", "POST", {"Name": name, "Ids": ",".join(desired[:100])}, False
            )
            collection_id = response.get("Id")
            if not collection_id:
                raise EmbyAPIError("POST", "Collections", "response did not contain Id")
            self._change(collection_id, desired[100:])
            result = CollectionUpdateResult(name, collection_id, True, len(desired), len(desired), 0)
        else:
            collection_id = collection["Id"]
            current = {
                str(item["Id"]) for item in self.collection_items(collection_id) if item.get("Id")
            }
            additions = [value for value in desired if value not in current]
            removals = sorted(current - set(desired))
            self._change(collection_id, additions)
            self._change(collection_id, removals, True)
            result = CollectionUpdateResult(
                name, collection_id, False, len(desired), len(additions), len(removals)
            )
        logger.info(
            "Collection '{}' synchronized: matched={}, added={}, removed={}, created={}",
            name, result.matched, result.added, result.removed, result.created,
        )
        return result


EmbyAPI = api
