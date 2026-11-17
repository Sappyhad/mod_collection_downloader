"""Fetching collection mod lists from the public Nexus Mods GraphQL API."""

import json
import re
import urllib.request
from dataclasses import dataclass

GRAPHQL_URL = "https://api-router.nexusmods.com/graphql"

COLLECTION_QUERY = """
query CollectionRevisionMods($revision: Int, $slug: String!, $viewAdultContent: Boolean) {
  collectionRevision(revision: $revision, slug: $slug, viewAdultContent: $viewAdultContent) {
    revisionNumber
    collection { name }
    modFiles {
      fileId
      optional
      file { fileId name size version mod { modId name game { domainName id } } }
    }
  }
}
"""

COLLECTION_URL_PATTERN = re.compile(r"/collections/([A-Za-z0-9]+)(?:/revisions/(\d+))?")
BARE_SLUG_PATTERN = re.compile(r"^[A-Za-z0-9]+$")


@dataclass
class ModFile:
    file_id: int
    file_name: str
    mod_id: int
    mod_name: str
    version: str
    size_kb: int
    optional: bool
    game_domain: str
    game_id: int

    @property
    def page_url(self) -> str:
        return (
            f"https://www.nexusmods.com/{self.game_domain}/mods/{self.mod_id}"
            f"?tab=files&file_id={self.file_id}"
        )


@dataclass
class Collection:
    name: str
    revision: int
    mods: list[ModFile]


def parse_collection_url(text: str) -> tuple[str, int | None]:
    """Return (slug, revision) from a collection URL or a bare slug."""
    text = text.strip()
    match = COLLECTION_URL_PATTERN.search(text)
    if match:
        revision = int(match.group(2)) if match.group(2) else None
        return match.group(1), revision
    if BARE_SLUG_PATTERN.match(text):
        return text, None
    raise ValueError(f"Not a recognized collection link: {text!r}")


def fetch_collection(slug: str, revision: int | None = None) -> Collection:
    body = json.dumps({
        "query": COLLECTION_QUERY,
        "variables": {"slug": slug, "revision": revision, "viewAdultContent": True},
        "operationName": "CollectionRevisionMods",
    }).encode()
    request = urllib.request.Request(
        GRAPHQL_URL,
        data=body,
        headers={"content-type": "application/json", "User-Agent": "Mozilla/5.0"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.load(response)

    if payload.get("errors"):
        raise RuntimeError(payload["errors"][0].get("message", "GraphQL error"))
    revision_data = (payload.get("data") or {}).get("collectionRevision")
    if not revision_data:
        raise RuntimeError("Collection not found (wrong link or private collection).")

    mods = [_to_mod_file(entry) for entry in revision_data["modFiles"]]
    mods.sort(key=lambda mod: (mod.optional, mod.mod_name.lower()))
    return Collection(
        name=revision_data["collection"]["name"],
        revision=revision_data["revisionNumber"],
        mods=mods,
    )


def _to_mod_file(entry: dict) -> ModFile:
    file = entry["file"]
    mod = file["mod"]
    return ModFile(
        file_id=entry["fileId"],
        file_name=file["name"],
        mod_id=mod["modId"],
        mod_name=mod["name"],
        version=file.get("version") or "",
        size_kb=file.get("size") or 0,
        optional=entry["optional"],
        game_domain=mod["game"]["domainName"],
        game_id=mod["game"]["id"],
    )
