from celery import Celery
import os
from dotenv import load_dotenv

load_dotenv()

# Configuration de Celery
app = Celery(
    'worker',
    broker= os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0"),
    backend=os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0"),
    include=['src.cleeroute.langGraph.learners_api.course_gen.tasks']
)

if __name__ == '__main__':
    app.start()
