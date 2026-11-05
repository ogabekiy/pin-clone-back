from contextlib import asynccontextmanager
import io
from typing import Dict, List
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from PIL import Image
import torch
from transformers import CLIPModel, CLIPProcessor

model_name = "openai/clip-vit-base-patch32"
model: CLIPModel | None = None
processor: CLIPProcessor | None = None
device = "cuda" if torch.cuda.is_available() else "cpu"


@asynccontextmanager
async def lifespan(app: FastAPI):
    global model, processor
    # Rule 3: Load model once at startup, not per request
    print(f"Loading CLIP model '{model_name}' on {device}...")
    try:
        model = CLIPModel.from_pretrained(model_name, use_safetensors=False).to(device)
        processor = CLIPProcessor.from_pretrained(model_name)
    except Exception as e:
        print(f"Online model fetch fallback to local cache: {e}")
        model = CLIPModel.from_pretrained(model_name, use_safetensors=False, local_files_only=True).to(device)
        processor = CLIPProcessor.from_pretrained(model_name, local_files_only=True)
    model.eval()
    print("CLIP model loaded successfully.")
    yield


app = FastAPI(title="CLIP Embedder Service", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok", "model": model_name, "device": device}


@app.get("/embed/text")
def embed_text(q: str = Query(..., min_length=1)) -> Dict[str, List[float]]:
    """Encodes text query into 512-dim normalized vector."""
    if not model or not processor:
        raise HTTPException(status_code=503, detail="Model hali yuklanmagan")

    with torch.no_grad():
        inputs = processor(text=[q], return_tensors="pt", padding=True, truncation=True).to(device)
        text_output = model.get_text_features(**inputs)
        text_features = text_output.pooler_output if hasattr(text_output, "pooler_output") and text_output.pooler_output is not None else text_output
        # Rule 5: Normalize vector (cosine distance)
        text_features = text_features / text_features.norm(p=2, dim=-1, keepdim=True)
        embedding = text_features[0].cpu().numpy().tolist()

    return {"embedding": embedding}


@app.post("/embed/image")
async def embed_image(file: UploadFile = File(...)) -> Dict[str, List[float]]:
    """Encodes uploaded image into 512-dim normalized vector."""
    if not model or not processor:
        raise HTTPException(status_code=503, detail="Model hali yuklanmagan")

    content = await file.read()
    try:
        image = Image.open(io.BytesIO(content)).convert("RGB")
    except Exception:
        raise HTTPException(status_code=400, detail="Rasm faylini o'qib bo'lmadi")

    with torch.no_grad():
        inputs = processor(images=image, return_tensors="pt").to(device)
        image_output = model.get_image_features(**inputs)
        image_features = image_output.pooler_output if hasattr(image_output, "pooler_output") and image_output.pooler_output is not None else image_output
        # Rule 5: Normalize vector (cosine distance)
        image_features = image_features / image_features.norm(p=2, dim=-1, keepdim=True)
        embedding = image_features[0].cpu().numpy().tolist()

    return {"embedding": embedding}

