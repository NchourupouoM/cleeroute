import os
from dotenv import load_dotenv

load_dotenv()  

broker_url = os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0')  
result_backend = os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0')
