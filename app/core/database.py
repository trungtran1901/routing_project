from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings

client: AsyncIOMotorClient = None


async def connect_to_mongo():
    global client
    client = AsyncIOMotorClient(settings.MONGODB_URI)
    print("Connected to MongoDB")


async def close_mongo_connection():
    global client
    if client:
        client.close()
        print("Disconnected from MongoDB")


def get_database():
    return client[settings.DATABASE_NAME]


# Collection names
COLLECTION_POINTS = "instance_data_hatang_quanlytuyen_newversion_detail"
COLLECTION_CABLES = "instance_data_hatang_quan_ly_cable"
COLLECTION_CABLE_DETAIL = "instance_data_hatang_quan_ly_cable_detail"
COLLECTION_SID_CABLE = "instance_data_hatang_danhsach_sid_cable"