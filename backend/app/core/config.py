import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./smart_delivery.db")
DEFAULT_SEED = int(os.getenv("SEED", "20261022"))

