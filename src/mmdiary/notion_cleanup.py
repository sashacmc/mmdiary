#!/usr/bin/python3

import logging
import os

import log
from notion.client import NotionClient
from notion.collection import CollectionRowBlock


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
    logging.info(f"Found {len(block_ids)} trash blocks.")
    cnt = 0
    for bid in block_ids:
        try:
            block = client.get_block(bid)
            if type(block) is CollectionRowBlock:
                block.remove()
            else:
                block.remove(permanently=True)

            logging.info(f"Done: {bid}")
            cnt += 1
        except Exception as err:
            logging.error(f"Error deleting block batch: {err}, Batch: {bid}")
    logging.info(f"Successfully cleared {cnt} trash blocks.")


def main():
    log.init_logger()
    try:
        token = os.getenv("NOTION_TOKEN")
        if not token:
            logging.error("No auth token provided. Please set NOTION_TOKEN env variable.")
            return 1

        client = NotionClient(token_v2=token)

        block_ids = get_trash(client)
        if block_ids:
            delete_block(client, block_ids)
        else:
            logging.info("No trash blocks found.")

    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}")
        return 1


if __name__ == "__main__":
    main()
