import base64
import io
import sys
import time
from pathlib import Path

from PIL import Image, ImageOps
from openai import OpenAI

path = Path(sys.argv[1])
with Image.open(path) as original:
    image = ImageOps.exif_transpose(original).convert("RGB")
    image.thumbnail((512, 512))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")

encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
client = OpenAI(
    base_url="http://127.0.0.1:8000/v1",
    api_key="local",
    timeout=180,
    max_retries=0,
)

prompt = (
    "Catalog the main garment in this image. Return only a JSON object "
    "with keys category, type, color, formality, season, brand. "
    "Use strings for known attributes and null for uncertain attributes. "
    "Formality and season are estimates: use null if unclear. "
    "Set brand to null because no user-supplied brand note is provided. "
    "Do not include Markdown or invent details."
)

start = time.perf_counter()
response = client.chat.completions.create(
    model="ai-closet-local",
    messages=[{"role": "user", "content": [
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": {
            "url": f"data:image/jpeg;base64,{encoded}"
        }},
    ]}],
    temperature=0,
    max_tokens=256,
)

print(response.choices[0].message.content)
print(f"\nRequest time: {time.perf_counter() - start:.2f} seconds")
print("Finish reason:", response.choices[0].finish_reason)
