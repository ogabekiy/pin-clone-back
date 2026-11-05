import uuid
from typing import Dict
import boto3
from botocore.config import Config
from app.core.config import settings


def get_s3_client():
    return boto3.client(
        "s3",
        endpoint_url=settings.r2_endpoint_url,
        aws_access_key_id=settings.R2_ACCESS_KEY_ID,
        aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
        region_name="auto",
        config=Config(signature_version="s3v4"),
    )


def create_presigned_upload_url(
    content_type: str = "image/jpeg",
    file_extension: str = "jpg",
) -> Dict[str, str]:
    """Generates a presigned PUT URL for client-side direct upload to Cloudflare R2."""
    clean_ext = file_extension.lstrip(".")
    image_key = f"pins/{uuid.uuid4().hex}.{clean_ext}"
    
    s3 = get_s3_client()
    presigned_url = s3.generate_presigned_url(
        ClientMethod="put_object",
        Params={
            "Bucket": settings.R2_BUCKET_NAME,
            "Key": image_key,
            "ContentType": content_type,
        },
        ExpiresIn=3600,  # 1 hour
    )

    if settings.R2_PUBLIC_URL:
        public_url = f"{settings.R2_PUBLIC_URL.rstrip('/')}/{image_key}"
    else:
        public_url = f"{settings.r2_endpoint_url}/{settings.R2_BUCKET_NAME}/{image_key}"

    return {
        "upload_url": presigned_url,
        "image_key": image_key,
        "image_url": public_url,
    }


def delete_r2_object(image_key: str) -> None:
    """Deletes an object from Cloudflare R2 bucket."""
    try:
        s3 = get_s3_client()
        s3.delete_object(Bucket=settings.R2_BUCKET_NAME, Key=image_key)
    except Exception as e:
        # Log error or suppress in dev
        pass

