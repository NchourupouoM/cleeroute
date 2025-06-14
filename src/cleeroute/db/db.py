import os
import psycopg2
from dotenv import load_dotenv
load_dotenv()

def get_db_connection():
    conn = psycopg2.connect(
        host= "cleeroute-videos.postgres.database.azure.com", #os.getenv("DB_HOST"),
        dbname= "postgres",  #os.getenv("DB_NAME"),
        user= "postgres",#   os.getenv("DB_USER"),
        password= "ladder-99", # os.getenv("DB_PASSWORD"),
        port=os.getenv("DB_PORT", 5432)
    )
    return conn