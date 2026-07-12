import os
import shutil
import tempfile
import zipfile

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from spleeter.separator import Separator

ALLOWED_STEMS = {"2stems", "4stems", "5stems"}

app = FastAPI(title="Spleeter Worker")

_separators: dict[str, Separator] = {}


def get_separator(stems: str) -> Separator:
    if stems not in _separators:
        _separators[stems] = Separator(f"spleeter:{stems}")
    return _separators[stems]


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/separate")
async def separate(file: UploadFile = File(...), stems: str = Form("4stems")):
    if stems not in ALLOWED_STEMS:
        raise HTTPException(status_code=400, detail="stems tidak valid")

    work_dir = tempfile.mkdtemp(prefix="spleeter_")
    try:
        src_path = os.path.join(work_dir, "audio.wav")
        with open(src_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        out_dir = os.path.join(work_dir, "output")
        separator = get_separator(stems)
        separator.separate_to_file(src_path, out_dir, codec="wav")

        track_dir = os.path.join(out_dir, "audio")
        if not os.path.isdir(track_dir):
            raise HTTPException(status_code=500, detail="Spleeter tidak menghasilkan output")

        zip_path = os.path.join(work_dir, "stems.zip")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for fname in os.listdir(track_dir):
                zf.write(os.path.join(track_dir, fname), arcname=fname)

        return FileResponse(
            zip_path,
            media_type="application/zip",
            filename="stems.zip",
            background=BackgroundTask(shutil.rmtree, work_dir, ignore_errors=True),
        )
    except HTTPException:
        shutil.rmtree(work_dir, ignore_errors=True)
        raise
    except Exception as exc:
        shutil.rmtree(work_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"Spleeter gagal: {exc}")
