#!/usr/bin/python3

import logging
import os

from notion.client import NotionClient
from notion.collection import CollectionRowBlock

from mmdiary.utils import log


def get_trash(client):
    query = {
        "type": "BlocksInSpace",
        "query": "",
        "filters": {
            "isDeletedOnly": True,
            "excludeTemplates": False,
            "navigableBlockContentOnly": True,
            "requireEditPermissions": False,
            "includePublicPagesWithoutExplicitAccess": False,
            "ancestors": [],
            "createdBy": [],
            "editedBy": [],
            "lastEditedTime": {},
            "createdTime": {},
            "inTeams": [],
        },
        "sort": {"field": "lastEdited", "direction": "desc"},
        "limit": 1000,
        "spaceId": client.current_space.id,
        "source": "trash",
    }
    results = client.post("/api/v3/search", query)
    return [block_id["id"] for block_id in results.json()["results"]]


def delete_block(client, block_ids):
    logging.info("Found %i trash blocks.", len(block_ids))
    cnt = 0
    for bid in block_ids:
        try:
            block = client.get_block(bid)
            if isinstance(block, CollectionRowBlock):
                block.remove()
            else:
                block.remove(permanently=True)

            logging.info("Done: %s", bid)
            cnt += 1
        except Exception as err:
            logging.error("Error deleting block batch: %s, Batch: %s", err, bid)
    logging.info("Successfully cleared %i trash blocks.", cnt)


def main():
    log.init_logger()
    try:
        token = os.getenv("MMDIARY_NOTION_TOKEN")
        if not token:
            logging.error("No auth token provided. Please set MMDIARY_NOTION_TOKEN env variable.")
            return 1

        client = NotionClient(token_v2=token)

        block_ids = get_trash(client)
        if block_ids:
            delete_block(client, block_ids)
        else:
            logging.info("No trash blocks found.")

    except Exception as e:
        logging.error("An unexpected error occurred: %s", e)
        return 1
    return 0


if __name__ == "__main__":
    main()
