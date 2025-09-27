from agenticle.prompt import OptimizerAgent
from agenticle import Endpoint
import os
from dotenv import load_dotenv


load_dotenv()

# --- Load configuration from .env file ---
api_key = os.getenv("API_KEY")
base_url = os.getenv("BASE_URL")
model_id = os.getenv("MODEL_ID")

endpoint = Endpoint(
    api_key=api_key,
    base_url=base_url
)

opt = OptimizerAgent(endpoint, model_id)

print(
    opt.optimize('根据材料出题')
)