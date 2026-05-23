"""
scripts/seed.py

Seeds the database with sample exams, packages, questions, and an admin user.
Run: python scripts/seed.py
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings
from app.core.security import hash_password
from app.models.documents import new_user, new_exam, new_package, new_question, utcnow
from bson import ObjectId


SAMPLE_EXAMS = [
    {
        "title": "AWS Certified Solutions Architect – Associate (SAA-C03)",
        "slug": "aws-saa-c03",
        "description": "Master AWS architecture patterns, services, and best practices. Covers EC2, S3, VPC, RDS, Lambda, and more.",
        "category": "Cloud",
        "price_usd": 29.99,
        "tags": ["aws", "cloud", "architecture", "solutions-architect"],
    },
    {
        "title": "CompTIA Security+ SY0-701",
        "slug": "comptia-security-plus",
        "description": "Industry-standard cybersecurity certification covering threats, vulnerabilities, and mitigation strategies.",
        "category": "Security",
        "price_usd": 24.99,
        "tags": ["security", "cybersecurity", "comptia", "networking"],
    },
    {
        "title": "Python Professional Developer",
        "slug": "python-professional",
        "description": "Advanced Python covering OOP, async programming, DSA, testing, and system design.",
        "category": "Programming",
        "price_usd": 19.99,
        "tags": ["python", "programming", "oop", "async"],
    },
    {
        "title": "AWS Certified Cloud Practitioner (CLF-C02)",
        "slug": "aws-certified-cloud-practitioner-clf-c02",
        "description": "Entry-level AWS certification covering cloud concepts, security, technology, and billing.",
        "category": "Cloud",
        "price_usd": 14.99,
        "tags": ["aws", "cloud", "practitioner"],
    },
    {
        "title": "Professional Scrum Master I (PSM I)",
        "slug": "professional-scrum-master-i-psm-i",
        "description": "Fundamental knowledge of the Scrum framework and how to apply it in real-world situations.",
        "category": "Agile",
        "price_usd": 15.00,
        "tags": ["scrum", "agile", "psm"],
    },
]

SAMPLE_QUESTIONS = {
    "aws-saa-c03": [
        {
            "text": "A company needs to store 100TB of infrequently accessed data with the lowest cost. Which S3 storage class should they use?",
            "type": "single",
            "options": [
                {"key": "A", "text": "S3 Standard", "is_correct": False},
                {"key": "B", "text": "S3 Glacier Deep Archive", "is_correct": True},
                {"key": "C", "text": "S3 Intelligent-Tiering", "is_correct": False},
                {"key": "D", "text": "S3 One Zone-IA", "is_correct": False},
            ],
            "explanation": "S3 Glacier Deep Archive is the lowest-cost storage class for data that is rarely accessed and can tolerate retrieval times of 12+ hours. It's ideal for long-term archive data.",
            "tags": ["s3", "storage", "cost-optimization"],
            "difficulty": "medium",
        },
        {
            "text": "Which AWS services support VPC Endpoint Gateway? (Select TWO)",
            "type": "multiple",
            "options": [
                {"key": "A", "text": "Amazon S3", "is_correct": True},
                {"key": "B", "text": "Amazon DynamoDB", "is_correct": True},
                {"key": "C", "text": "Amazon EC2", "is_correct": False},
                {"key": "D", "text": "Amazon RDS", "is_correct": False},
            ],
            "explanation": "VPC Gateway Endpoints support only Amazon S3 and DynamoDB. They allow private connectivity without requiring internet gateway, NAT device, or VPN connection.",
            "tags": ["vpc", "networking", "s3", "dynamodb"],
            "difficulty": "hard",
        },
        {
            "text": "Amazon RDS Multi-AZ deployment automatically replicates data to a standby instance in the same Availability Zone.",
            "type": "true_false",
            "options": [
                {"key": "A", "text": "True", "is_correct": False},
                {"key": "B", "text": "False", "is_correct": True},
            ],
            "explanation": "Multi-AZ deploys a standby replica in a DIFFERENT Availability Zone, not the same one. This provides high availability during AZ failures.",
            "tags": ["rds", "high-availability", "multi-az"],
            "difficulty": "easy",
        },
    ],
    "aws-certified-cloud-practitioner-clf-c02": [
        {
            "text": "Which AWS service is used for automated security assessments?",
            "type": "single",
            "options": [
                {"key": "A", "text": "Amazon Inspector", "is_correct": True},
                {"key": "B", "text": "AWS Shield", "is_correct": False},
            ],
            "explanation": "Amazon Inspector is an automated security assessment service.",
            "tags": ["security", "inspector"],
            "difficulty": "easy",
        },
    ],
    "professional-scrum-master-i-psm-i": [
        {
            "text": "Who is responsible for managing the Product Backlog?",
            "type": "single",
            "options": [
                {"key": "A", "text": "The Product Owner", "is_correct": True},
                {"key": "B", "text": "The Scrum Master", "is_correct": False},
            ],
            "explanation": "The Product Owner is the sole person responsible for managing the Product Backlog.",
            "tags": ["scrum", "roles"],
            "difficulty": "easy",
        },
    ],
    "python-professional": [
        {
            "text": "Which data structure provides O(1) average time complexity for both insertion and lookup by key?",
            "type": "single",
            "options": [
                {"key": "A", "text": "Binary Search Tree", "is_correct": False},
                {"key": "B", "text": "Hash Map (dict)", "is_correct": True},
                {"key": "C", "text": "Sorted List", "is_correct": False},
                {"key": "D", "text": "Heap", "is_correct": False},
            ],
            "explanation": "Python's dict uses a hash table internally, providing O(1) average-case for get/set/delete. BSTs have O(log n), sorted lists have O(log n) search but O(n) insertion.",
            "tags": ["dsa", "hash-map", "time-complexity"],
            "difficulty": "medium",
        },
        {
            "text": "What does the `async def` keyword create in Python?",
            "type": "single",
            "options": [
                {"key": "A", "text": "A thread", "is_correct": False},
                {"key": "B", "text": "A coroutine function", "is_correct": True},
                {"key": "C", "text": "A subprocess", "is_correct": False},
                {"key": "D", "text": "A generator", "is_correct": False},
            ],
            "explanation": "async def defines a coroutine function. When called, it returns a coroutine object that must be awaited. It runs on a single thread using the event loop (asyncio), not OS threads.",
            "tags": ["async", "coroutines", "asyncio"],
            "difficulty": "easy",
        },
    ],
}


async def seed():
    client = AsyncIOMotorClient(settings.MONGODB_URL)
    db = client[settings.MONGODB_DB_NAME]

    print(f"Seeding database: {settings.MONGODB_DB_NAME}")

    # Clear existing data
    for collection in ["users", "exams", "packages", "questions", "attempts", "purchases", "tb_cert_metadata"]:
        await db[collection].delete_many({})
    print("  ✓ Cleared existing data")

    # Create admin user
    admin = new_user(
        email="admin@examprep.dev",
        username="admin",
        hashed_password=hash_password("Admin123!"),
        role="admin",
    )
    admin_result = await db.users.insert_one(admin)
    print(f"  ✓ Admin user: admin@examprep.dev / Admin123!")

    # Create test user
    test_user = new_user(
        email="student@examprep.dev",
        username="student1",
        hashed_password=hash_password("Student123!"),
    )
    student_result = await db.users.insert_one(test_user)
    student_id = str(student_result.inserted_id)
    print(f"  ✓ Student user: student@examprep.dev / Student123!")

    # Create exams + packages + questions
    for exam_data in SAMPLE_EXAMS:
        exam_doc = new_exam(**exam_data)
        exam_doc["is_published"] = True
        exam_result = await db.exams.insert_one(exam_doc)
        exam_id = str(exam_result.inserted_id)

        total_questions = 0
        for pkg_order in range(1, 7):   # 6 packages per exam
            pkg = new_package(
                exam_id=exam_id,
                order=pkg_order,
                title=f"Practice Test {pkg_order}",
                description=f"Package {pkg_order} of 6 — {exam_data['title']}",
                time_limit_minutes=90,
                pass_score_pct=72,
            )
            pkg_result = await db.packages.insert_one(pkg)
            pkg_id = str(pkg_result.inserted_id)

            # Add sample questions (first package of each exam gets real ones)
            sample_qs = SAMPLE_QUESTIONS.get(exam_data["slug"], [])
            q_count = 0
            if pkg_order == 1 and sample_qs:
                for q_data in sample_qs:
                    q_doc = new_question(
                        package_id=pkg_id,
                        exam_id=exam_id,
                        **q_data,
                    )
                    await db.questions.insert_one(q_doc)
                    q_count += 1

                await db.packages.update_one(
                    {"_id": pkg_result.inserted_id},
                    {"$set": {"question_count": q_count}},
                )
            else:
                # Placeholder questions for other packages
                q_count = 40
                await db.packages.update_one(
                    {"_id": pkg_result.inserted_id},
                    {"$set": {"question_count": q_count}},
                )

            total_questions += q_count

        await db.exams.update_one(
            {"_id": exam_result.inserted_id},
            {"$set": {"total_questions": total_questions}},
        )

        # Sync to metadata table for catalog browsing
        metadata = {
            "id": exam_id,
            "slug": exam_data["slug"],
            "name": exam_data["title"],
            "category": exam_data["category"],
            "short_brief": exam_data["description"],
            "price": exam_data["price_usd"],
            "students": 1200,
            "multi_choice_questions": total_questions
        }
        await db.tb_cert_metadata.insert_one(metadata)

        print(f"  ✓ Exam: {exam_data['title']} ({total_questions} questions)")

    # Grant student access to first exam
    first_exam = await db.exams.find_one({"slug": "aws-saa-c03"})
    if first_exam:
        from app.models.documents import new_purchase
        purchase = new_purchase(
            user_id=student_id,
            exam_id=str(first_exam["_id"]),
            amount_usd=29.99,
            stripe_payment_id=f"pi_demo_{ObjectId()}",
            status="completed",
        )
        await db.purchases.insert_one(purchase)
        print(f"  ✓ Granted student access to AWS SAA-C03")

    # Create indexes
    await db.users.create_index([("email", 1)], unique=True)
    await db.users.create_index([("username", 1)], unique=True)
    await db.exams.create_index([("slug", 1)], unique=True)
    await db.packages.create_index([("exam_id", 1), ("order", 1)])
    await db.questions.create_index([("package_id", 1)])
    await db.purchases.create_index([("user_id", 1), ("exam_id", 1)])
    print("  ✓ Created indexes")

    client.close()
    print("\nSeed complete!")
    print("─" * 40)
    print("Admin:   admin@examprep.dev / Admin123!")
    print("Student: student@examprep.dev / Student123!")
    print("API:     http://localhost:8000/docs")


if __name__ == "__main__":
    asyncio.run(seed())
