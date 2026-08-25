import sys
from loguru import logger
from api import EmbyAPIError
from functions import (
    config_bool, content_kind, determine_match, determine_rule_type, load_config,
    map_content_data,
)
from planner import plan_query
from variables import DEBUG, EMBY_ADDRESS, EMBY_TOKEN, SCAN_INTERVAL, emby_api
from watcher import register_config_watcher

__version__ = "0.6.0"

FIELD_MAP = {
    "datecreated": "DateCreated", "overview": "Overview", "parentid": "ParentId",
    "genres": "Genres", "genresany": "Genres", "genresall": "Genres",
    "excludegenres": "Genres", "people": "People", "studios": "Studios",
    "path": "Path",
}


def fields_for_rules(filters):
    """Id, Name and Type are standard BaseItem fields; request optional fields only."""
    return {FIELD_MAP[key] for key in filters if key in FIELD_MAP}


def main(config):
    if not config.sections():
        logger.warning("No rule sets found")
        return
    try:
        libraries = [item for item in emby_api.Libraries() if item.get("Name") != "Collections"]
        logger.info("Authenticated; found {} media libraries", len(libraries))
    except EmbyAPIError as exc:
        logger.error("Cannot enumerate Emby libraries: {}", exc)
        return

    for rule_set in config.sections():
        rules = determine_rule_type(config.items(rule_set))
        plan = plan_query(rules)
        try:
            include_video = config_bool(rules["behaviour"].get("includevideo"), True)
            include_folders = config_bool(rules["behaviour"].get("includefolders"), False)
            include_photos = config_bool(rules["behaviour"].get("includephotos"), False)
        except ValueError as exc:
            logger.error("Rule set '{}' has invalid inclusion setting: {}", rule_set, exc)
            continue
        if not any((include_video, include_folders, include_photos)):
            logger.error(
                "Rule set '{}' is invalid: IncludeVideo, IncludeFolders, and IncludePhotos cannot all be false",
                rule_set,
            )
            continue
        library_name = rules["behaviour"].get("library")
        selected = [
            item for item in libraries
            if not library_name or item.get("Name", "").casefold() == library_name.casefold()
        ]
        if library_name and not selected:
            logger.error("Library '{}' configured for '{}' was not found", library_name, rule_set)
            continue

        logger.info("Rule set '{}' execution strategy: {}", rule_set, plan.strategy)
        logger.info(
            "Planner: {} server-side filters, {} local verifiers",
            plan.server_filter_count, plan.local_verifier_count,
        )

        matching_ids = set()
        excluded = {"video": 0, "folder": 0, "photo": 0, "other": 0}
        included_kinds = {
            "video": include_video, "folder": include_folders, "photo": include_photos,
        }
        scan_complete = True
        for library in selected:
            display_name = library.get("Name", "unknown library")
            try:
                saw_page = False
                seen_candidates = set()
                for query_number, query in enumerate(plan.queries, 1):
                    for page, retrieved, total in emby_api.iter_library_content(
                        library["Id"], params=query,
                        fields=fields_for_rules(rules["filters"]),
                    ):
                        saw_page = True
                        for raw_item in page:
                            item_id = raw_item.get("Id")
                            if item_id in seen_candidates:
                                continue
                            seen_candidates.add(item_id)
                            item = map_content_data(raw_item)
                            if not determine_match(item, rule_set, rules["filters"]):
                                continue
                            kind = content_kind(raw_item)
                            if not included_kinds.get(kind, False):
                                excluded[kind] += 1
                                continue
                            matching_ids.add(item["id"])
                        logger.info(
                            "Scanning {} query {}/{}: {} / {}",
                            display_name, query_number, len(plan.queries),
                            retrieved, total,
                        )
                if not saw_page:
                    logger.info("Scanning {}: 0 / 0", display_name)
            except EmbyAPIError as exc:
                scan_complete = False
                logger.error(
                    "Scan failed for library '{}' in rule set '{}'; collection left unchanged: {}",
                    display_name, rule_set, exc,
                )
                break

        if not scan_complete:
            continue
        logger.success(
            "Rule set '{}' matched {} items, excluded {} videos, {} folders, {} photos, {} other items",
            rule_set, len(matching_ids), excluded["video"], excluded["folder"],
            excluded["photo"], excluded["other"],
        )
        if rules["behaviour"].get("dryrun", "false").lower() == "true":
            logger.warning("Dry run enabled for '{}'; no changes made", rule_set)
            continue
        try:
            result = emby_api.update_collection(rule_set, matching_ids)
            logger.success(
                "Synchronized '{}': {} matched, {} added, {} removed",
                rule_set, result.matched, result.added, result.removed,
            )
        except EmbyAPIError as exc:
            logger.error("Failed to synchronize '{}': {}", rule_set, exc)


if __name__ == "__main__":
    logger.remove()
    logger.add(sys.stderr, level="DEBUG" if DEBUG else "INFO")
    if not EMBY_ADDRESS or not EMBY_TOKEN:
        logger.error("EMBY_ADDRESS and EMBY_TOKEN are required")
        sys.exit(1)
    logger.info("Starting EDCM {} for Emby Server 4.10", __version__)
    event = register_config_watcher()
    while True:
        event.clear()
        main(load_config())
        logger.info("Next scan in {} seconds", SCAN_INTERVAL)
        if event.wait(SCAN_INTERVAL):
            logger.info("Configuration change detected; rescanning")
