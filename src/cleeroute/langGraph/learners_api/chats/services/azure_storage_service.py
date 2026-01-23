import os
import uuid
from datetime import datetime, timedelta
from azure.storage.blob.aio import BlobServiceClient
from azure.storage.blob import generate_blob_sas, BlobSasPermissions

class AzureStorageService:
    def __init__(self):
        self.connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
        self.container_name = os.getenv("AZURE_CONTAINER_NAME")
        
        if not self.connection_string or not self.container_name:
            raise ValueError("Azure Storage configuration missing.")

    async def upload_file(self, file_bytes: bytes, filename: str, session_id: str) -> str:
        """
            Upload the file and return its internal path (blob_name).
            Structure: session_id/uuid_filename.
        """
        # On crée un nom unique pour éviter les collisions
        unique_name = f"{session_id}/{uuid.uuid4()}_{filename}"
        
        # Initialisation du client (Async)
        blob_service_client = BlobServiceClient.from_connection_string(self.connection_string)
        
        async with blob_service_client:
            container_client = blob_service_client.get_container_client(self.container_name)
            
            # Créer le container s'il n'existe pas
            if not await container_client.exists():
                await container_client.create_container()
            
            blob_client = container_client.get_blob_client(unique_name)
            
            # Upload
            await blob_client.upload_blob(file_bytes, overwrite=True)
            
        return unique_name

    def generate_sas_url(self, blob_name: str, expiry_hours: int = 2) -> str:
        """
            genrate a public temporary URL (SAS) so that the frontend can display the file.
            args:
                blob_name: internal path of the blob in Azure Storage.
                expiry_hours: validity duration of the SAS token.
            returns: full SAS URL or None if blob_name is invalid.
        """
        if not blob_name: 
            return None
        
        # Méthode plus simple : Utiliser les parties de la connection string
        conn_str_parts = {k: v for k, v in [p.split('=', 1) for p in self.connection_string.split(';') if '=' in p]}
        account_name = conn_str_parts.get('AccountName')
        account_key = conn_str_parts.get('AccountKey')

        sas_token = generate_blob_sas(
            account_name=account_name,
            container_name=self.container_name,
            blob_name=blob_name,
            account_key=account_key,
            permission=BlobSasPermissions(read=True),
            expiry=datetime.now() + timedelta(hours=expiry_hours)
        )
        
        return f"https://{account_name}.blob.core.windows.net/{self.container_name}/{blob_name}?{sas_token}"