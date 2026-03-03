import os
import sys
from datetime import datetime, timezone

from dotenv import load_dotenv
from pymongo import DESCENDING, MongoClient
from pymongo.errors import PyMongoError


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def fail(message: str) -> None:
    print(f"[init_mongo] ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    load_dotenv()

    mongo_uri = os.getenv("MONGO_URI")
    if not mongo_uri:
        fail("MONGO_URI is required. Please set it in your environment or .env.")

    mongo_db = os.getenv("MONGO_DB", "devpick")

    client = None
    try:
        client = MongoClient(mongo_uri)
        client.admin.command("ping")
        print("[init_mongo] MongoDB ping successful")

        db = client[mongo_db]

        contents = db["contents"]
        contents.create_index(
            [("url", 1)],
            unique=True,
            sparse=True,
            name="ux_contents_url",
        )
        contents.create_index(
            [("source", 1), ("external_id", 1)],
            unique=True,
            sparse=True,
            name="ux_contents_source_external",
        )
        contents.create_index(
            [("created_at", DESCENDING)],
            name="ix_contents_created_at_desc",
        )

        configs = db["configs"]
        configs.create_index(
            [("key", 1)],
            unique=True,
            name="ux_configs_key",
        )

        now = utc_now()

        configs.update_one(
            {"key": "schema_version"},
            {
                "$set": {
                    "value": 1,
                    "updated_at": now,
                },
                "$setOnInsert": {
                    "key": "schema_version",
                    "created_at": now,
                },
            },
            upsert=True,
        )

        configs.update_one(
            {"key": "initialized_at"},
            {
                "$setOnInsert": {
                    "key": "initialized_at",
                    "value": now,
                    "created_at": now,
                    "updated_at": now,
                }
            },
            upsert=True,
        )

        print(f"[init_mongo] Initialization complete for database: {mongo_db}")

    except PyMongoError as error:
        fail(str(error))
    except Exception as error:  # noqa: BLE001
        fail(str(error))
    finally:
        if client is not None:
            client.close()


if __name__ == "__main__":
    main()
