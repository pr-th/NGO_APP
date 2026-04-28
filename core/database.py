from motor.motor_asyncio import AsyncIOMotorClient
from core.config import get_settings

settings = get_settings()

class Database:
    client: AsyncIOMotorClient = None
    db = None

db_instance = Database()

async def connect_db():
    db_instance.client = AsyncIOMotorClient(settings.mongodb_url)
    db_instance.db = db_instance.client[settings.db_name]
    # Create indexes
    await create_indexes()
    print("Connected to MongoDB Atlas")

async def close_db():
    if db_instance.client:
        db_instance.client.close()
        print("Disconnected from MongoDB Atlas")

async def create_indexes():
    db = db_instance.db
    # Users
    await db.users.create_index("email", unique=True)
    await db.users.create_index("aadhaar_id", unique=True)
    # Volunteers
    await db.volunteers.create_index("email", unique=True)
    await db.volunteers.create_index("aadhaar_id", unique=True)
    await db.volunteers.create_index([("skills", 1)])
    # NGOs
    await db.ngos.create_index("pan_number", unique=True)
    await db.ngos.create_index("darpan_id", unique=True)
    # Problems
    await db.problems.create_index([("category", 1), ("importance", 1)])
    await db.problems.create_index([("created_at", -1)])
    # Posts
    await db.posts.create_index([("created_at", -1)])
    await db.posts.create_index([("category", 1)])
    print("Indexes created")

def get_db():
    return db_instance.db
