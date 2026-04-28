from fastapi import APIRouter, Depends, File, UploadFile

from core.security import get_current_user
from utils.gcs_storage import upload_image_and_get_url


router = APIRouter(prefix="/uploads", tags=["Uploads"])


@router.post("/images", summary="Upload an image to Google Cloud Storage")
async def upload_image(
    image: UploadFile = File(...),
    current=Depends(get_current_user),
):
    url = await upload_image_and_get_url(image, owner_id=current["_id"])
    return {"url": url}

