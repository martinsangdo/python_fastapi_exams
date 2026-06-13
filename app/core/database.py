"""
app/core/database.py

Async MongoDB connection using Motor.
Indexes are created on startup for O(log n) query performance (Module 1: DSA).
"""
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ASCENDING, DESCENDING, TEXT
import structlog

from app.core.config import settings

log = structlog.get_logger()

client: AsyncIOMotorClient = None


async def connect_db():
    global client
    client = AsyncIOMotorClient(settings.MONGODB_URL)
    db = client[settings.MONGODB_DB_NAME]

    # Create indexes (DSA: B-tree indexes → O(log n) lookup)
    await db.users.create_index([("email", ASCENDING)], unique=True)
    await db.users.create_index([("username", ASCENDING)], unique=True)

    await db.exams.create_index([("slug", ASCENDING)], unique=True)
    await db.exams.create_index([("category", ASCENDING)])
    await db.exams.create_index([("title", TEXT)])  # full-text search

    await db.tb_cert_metadata.create_index([("slug", ASCENDING)], unique=True)
    await db.tb_cert_metadata.create_index([("symbol", ASCENDING)], unique=True)
    await db.tb_cert_metadata.create_index([("collection_name", ASCENDING)], unique=True)

    await db.packages.create_index([("exam_id", ASCENDING)])
    await db.packages.create_index([("exam_id", ASCENDING), ("order", ASCENDING)])

    await db.questions.create_index([("package_id", ASCENDING)])
    await db.questions.create_index([("tags", ASCENDING)])

    await db.attempts.create_index([("user_id", ASCENDING), ("package_id", ASCENDING)])
    await db.attempts.create_index([("user_id", ASCENDING), ("completed_at", DESCENDING)])

    await db.purchases.create_index([("user_id", ASCENDING), ("exam_id", ASCENDING)])
    await db.purchases.create_index([("stripe_payment_id", ASCENDING)], unique=True, sparse=True)

    await db.leaderboard.create_index([("exam_id", ASCENDING), ("score", DESCENDING)])

    log.info("database.connected", db=settings.MONGODB_DB_NAME)
    return db


async def close_db():
    global client
    if client:
        client.close()
        log.info("database.disconnected")


def get_db():
    return client[settings.MONGODB_DB_NAME]
