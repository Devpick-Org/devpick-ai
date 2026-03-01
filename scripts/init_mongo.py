#!/usr/bin/env python3
"""Initialize minimal MongoDB collections and indexes for devpick-ai.

Idempotent: safe to run multiple times.
Exits with code 1 on failure.
"""
import os
import sys
import traceback
from datetime import datetime

from dotenv import load_dotenv
import pymongo
from pymongo import ASCENDING, DESCENDING


def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


def main() -> int:
    load_dotenv()

    MONGO_URI = os.getenv("MONGO_URI")
    MONGO_DB = os.getenv("MONGO_DB", "devpick")

    if not MONGO_URI:
        eprint("ERROR: MONGO_URI is not set. Please set it in your environment or .env file.")
        return 1

    try:
        client = pymongo.MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        # verify connection
        client.admin.command("ping")
    except Exception:
        eprint("ERROR: Could not connect to MongoDB with provided MONGO_URI")
        traceback.print_exc(file=sys.stderr)
        return 1

    db = client[MONGO_DB]

    try:
        # contents collection indexes
        contents = db["contents"]
        contents.create_index([("url", ASCENDING)], name="ux_contents_url", unique=True, sparse=True)
        contents.create_index(
            [("source", ASCENDING), ("external_id", ASCENDING)],
            name="ux_contents_source_external",
            unique=True,
            sparse=True,
        )
        contents.create_index([("created_at", DESCENDING)], name="ix_contents_created_at_desc")

        # configs collection indexes
        configs = db["configs"]
        configs.create_index([("key", ASCENDING)], name="ux_configs_key", unique=True)

        # seed / upsert default config values
        now = datetime.utcnow()

        # schema_version -> always set to 1 (upsert)
        configs.update_one(
            {"key": "schema_version"},
            {
                "$set": {"value": 1, "updated_at": now},
                "$setOnInsert": {"created_at": now},
            },
            upsert=True,
        )

        # initialized_at -> set only on first insert
        configs.update_one(
            {"key": "initialized_at"},
            {
                "$setOnInsert": {"value": now, "created_at": now},
            },
            upsert=True,
        )

        print("MongoDB initialization completed successfully.")
        return 0

    except Exception:
        eprint("ERROR: Failed during initialization steps")
        traceback.print_exc(file=sys.stderr)
        return 1


if __name__ == "__main__":
    rc = main()
    sys.exit(rc)
