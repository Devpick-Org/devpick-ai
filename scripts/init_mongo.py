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

        ai_summaries = db["ai_summaries"]
        ai_summaries.create_index(
            [("content_id", 1), ("level", 1)],
            unique=True,
            name="ux_summaries_content_level",
        )
        ai_summaries.create_index(
            [("content_id", 1)],
            name="ix_summaries_content_id",
        )
        ai_summaries.create_index(
            [("updated_at", DESCENDING)],
            name="ix_summaries_updated_at_desc",
        )

        rag_documents = db["rag_documents"]
        rag_documents.create_index(
            [("content_id", 1), ("chunk_index", 1)],
            unique=True,
            name="ux_rag_content_chunk",
        )
        rag_documents.create_index(
            [("content_id", 1)],
            name="ix_rag_content_id",
        )

        ai_answers = db["ai_answers"]
        ai_answers.create_index(
            [("question_id", 1)],
            unique=True,
            sparse=True,
            name="ux_answers_question_id",
        )
        ai_answers.create_index(
            [("content_id", 1)],
            name="ix_answers_content_id",
        )
        ai_answers.create_index(
            [("updated_at", DESCENDING)],
            name="ix_answers_updated_at_desc",
        )

        rag_questions = db["rag_questions"]
        rag_questions.create_index(
            [("question_id", 1)],
            unique=True,
            name="ux_questions_question_id",
        )
        rag_questions.create_index(
            [("content_id", 1)],
            name="ix_questions_content_id",
        )
        rag_questions.create_index(
            [("updated_at", DESCENDING)],
            name="ix_questions_updated_at_desc",
        )

        event_logs = db["event_logs"]
        event_logs.create_index(
            [("user_id", 1), ("event_type", 1), ("content_id", 1), ("question_id", 1)],
            name="ix_events_dedup",
        )
        event_logs.create_index(
            [("user_id", 1), ("timestamp", DESCENDING)],
            name="ix_events_user_timestamp_desc",
        )
        event_logs.create_index(
            [("created_at", 1)],
            name="ix_events_created_at_ttl",
            expireAfterSeconds=7776000,  # 90일
        )

        weekly_report_insights = db["weekly_report_insights"]
        weekly_report_insights.create_index(
            [("report_id", 1)],
            unique=True,
            name="ux_insights_report_id",
        )
        weekly_report_insights.create_index(
            [("user_id", 1)],
            name="ix_insights_user_id",
        )

        now = utc_now()

        configs.update_one(
            {"key": "schema_version"},
            {
                "$set": {
                    "value": 4,
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
