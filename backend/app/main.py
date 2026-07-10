import os
import shutil
import subprocess
import time
import uuid
import zipfile

import yt_dlp
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

DOWNLOAD_DIR = os.environ.get("DOWNLOAD_DIR", "/app/downloads")
SPLIT_DIR = os.environ.get("SPLIT_DIR", "/app/splits")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
os.makedirs(SPLIT_DIR, exist_ok=True)

SPLIT_JOB_TTL_SECONDS = 60 * 60  # 1 jam
split_jobs: dict[str, dict] = {}

STEM_LABELS = {
    "vocals": "Vocal",
    "drums": "Drum",
    "bass": "Bass",
    "other": "Instrumen Lain",
}

app = FastAPI(title="YT Downloader")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class InfoRequest(BaseModel):
    url: str


class DownloadRequest(BaseModel):
    url: str
    format_id: str
    mode: str  # "video" | "audio"
    ext: str | None = None  # target extension for audio (mp3, m4a, opus, wav)


class SplitRequest(BaseModel):
    url: str


def classify_video_tier(height: int | None) -> str:
    if not height:
        return "unknown"
    if height >= 1080:
        return "high"
    if height >= 480:
        return "medium"
    return "low"


def classify_audio_tier(abr: float | None) -> str:
    if not abr:
        return "unknown"
    if abr >= 192:
        return "high"
    if abr >= 96:
        return "medium"
    return "low"


def human_size(num_bytes) -> str | None:
    if not num_bytes:
        return None
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/info")
def get_info(req: InfoRequest):
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(req.url, download=False)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Gagal mengambil info video: {exc}")

    formats = info.get("formats", []) or []
    video_formats = []
    audio_formats = []
    seen_video = set()
    seen_audio = set()

    for f in formats:
        vcodec = f.get("vcodec")
        acodec = f.get("acodec")
        is_video = vcodec and vcodec != "none"
        is_audio_only = (not vcodec or vcodec == "none") and acodec and acodec != "none"

        if is_video:
            height = f.get("height")
            if not height:
                continue
            vbr = f.get("vbr") or f.get("tbr") or 0
            key = (height, f.get("ext"), f.get("fps"), round(vbr))
            if key in seen_video:
                continue
            seen_video.add(key)
            size = f.get("filesize") or f.get("filesize_approx")
            video_formats.append(
                {
                    "format_id": f.get("format_id"),
                    "ext": f.get("ext"),
                    "resolution": f"{f.get('width') or '?'}x{height}",
                    "height": height,
                    "fps": f.get("fps"),
                    "bitrate_kbps": round(vbr, 1) if vbr else None,
                    "filesize": size,
                    "filesize_human": human_size(size),
                    "quality_tier": classify_video_tier(height),
                    "has_audio": bool(acodec and acodec != "none"),
                }
            )
        elif is_audio_only:
            abr = f.get("abr") or f.get("tbr") or 0
            key = (round(abr), f.get("ext"))
            if key in seen_audio:
                continue
            seen_audio.add(key)
            size = f.get("filesize") or f.get("filesize_approx")
            audio_formats.append(
                {
                    "format_id": f.get("format_id"),
                    "ext": f.get("ext"),
                    "bitrate_kbps": round(abr, 1) if abr else None,
                    "filesize": size,
                    "filesize_human": human_size(size),
                    "quality_tier": classify_audio_tier(abr),
                }
            )

    video_formats.sort(key=lambda x: (-(x["height"] or 0), -(x["bitrate_kbps"] or 0)))
    audio_formats.sort(key=lambda x: -(x["bitrate_kbps"] or 0))

    return {
        "title": info.get("title"),
        "thumbnail": info.get("thumbnail"),
        "duration": info.get("duration"),
        "uploader": info.get("uploader"),
        "webpage_url": info.get("webpage_url"),
        "video_formats": video_formats,
        "audio_formats": audio_formats,
    }


@app.post("/api/download")
def download(req: DownloadRequest, background_tasks: BackgroundTasks):
    if req.mode not in ("video", "audio"):
        raise HTTPException(status_code=400, detail="mode harus 'video' atau 'audio'")

    job_id = str(uuid.uuid4())
    job_dir = os.path.join(DOWNLOAD_DIR, job_id)
    os.makedirs(job_dir, exist_ok=True)
    outtmpl = os.path.join(job_dir, "%(title).100s.%(ext)s")

    ydl_opts = {
        "outtmpl": outtmpl,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "restrictfilenames": True,
    }

    if req.mode == "video":
        ydl_opts["format"] = f"{req.format_id}+bestaudio/best"
        ydl_opts["merge_output_format"] = "mp4"
    else:
        target_ext = req.ext or "mp3"
        ydl_opts["format"] = req.format_id
        ydl_opts["postprocessors"] = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": target_ext,
                "preferredquality": "0",
            }
        ]

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([req.url])
    except Exception as exc:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail=f"Gagal mendownload: {exc}")

    files = [f for f in os.listdir(job_dir) if os.path.isfile(os.path.join(job_dir, f))]
    if not files:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail="File hasil download tidak ditemukan")

    file_path = os.path.join(job_dir, files[0])
    background_tasks.add_task(shutil.rmtree, job_dir, ignore_errors=True)

    return FileResponse(
        file_path,
        filename=files[0],
        media_type="application/octet-stream",
        background=background_tasks,
    )


def cleanup_stale_split_jobs():
    now = time.time()
    stale_ids = [
        job_id
        for job_id, job in split_jobs.items()
        if now - job["created_at"] > SPLIT_JOB_TTL_SECONDS
    ]
    for job_id in stale_ids:
        shutil.rmtree(os.path.join(SPLIT_DIR, job_id), ignore_errors=True)
        split_jobs.pop(job_id, None)


def run_split_job(job_id: str, url: str):
    job = split_jobs[job_id]
    job_dir = os.path.join(SPLIT_DIR, job_id)
    src_dir = os.path.join(job_dir, "source")
    out_dir = os.path.join(job_dir, "output")
    os.makedirs(src_dir, exist_ok=True)

    try:
        job["status"] = "downloading"
        job["message"] = "Mengunduh audio dari YouTube..."

        ydl_opts = {
            "outtmpl": os.path.join(src_dir, "audio.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "format": "bestaudio/best",
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "wav",
                    "preferredquality": "0",
                }
            ],
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
        job["title"] = info.get("title")

        src_files = [f for f in os.listdir(src_dir) if f.lower().endswith(".wav")]
        if not src_files:
            raise RuntimeError("Gagal mengunduh audio sumber")
        src_path = os.path.join(src_dir, src_files[0])

        job["status"] = "processing"
        job["message"] = (
            "Memisahkan instrumen (vocal, drum, bass, lainnya) dengan Demucs... "
            "proses ini bisa memakan waktu beberapa menit."
        )

        cmd = [
            "demucs",
            "-n",
            "htdemucs",
            "--mp3",
            "--mp3-bitrate",
            "320",
            "-o",
            out_dir,
            src_path,
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(f"Demucs gagal: {proc.stderr[-2000:]}")

        track_name = os.path.splitext(os.path.basename(src_path))[0]
        stems_dir = os.path.join(out_dir, "htdemucs", track_name)
        stems = []
        for stem_key, label in STEM_LABELS.items():
            file_path = os.path.join(stems_dir, f"{stem_key}.mp3")
            if os.path.exists(file_path):
                stems.append(
                    {
                        "key": stem_key,
                        "label": label,
                        "filename": f"{stem_key}.mp3",
                        "size_human": human_size(os.path.getsize(file_path)),
                    }
                )

        if not stems:
            raise RuntimeError("Tidak ada file stem yang dihasilkan")

        job["stems_dir"] = stems_dir
        job["stems"] = stems
        job["status"] = "done"
        job["message"] = "Selesai"
    except Exception as exc:
        job["status"] = "error"
        job["message"] = str(exc)
    finally:
        shutil.rmtree(src_dir, ignore_errors=True)


@app.post("/api/split")
def start_split(req: SplitRequest, background_tasks: BackgroundTasks):
    cleanup_stale_split_jobs()
    job_id = str(uuid.uuid4())
    split_jobs[job_id] = {
        "status": "queued",
        "message": "Menunggu diproses...",
        "created_at": time.time(),
        "title": None,
        "stems": [],
    }
    background_tasks.add_task(run_split_job, job_id, req.url)
    return {"job_id": job_id}


@app.get("/api/split/{job_id}")
def get_split_status(job_id: str):
    job = split_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job tidak ditemukan")
    return {
        "status": job["status"],
        "message": job["message"],
        "title": job.get("title"),
        "stems": job.get("stems", []),
    }


@app.get("/api/split/{job_id}/download/{stem_key}")
def download_stem(job_id: str, stem_key: str):
    job = split_jobs.get(job_id)
    if not job or job["status"] != "done":
        raise HTTPException(status_code=404, detail="Hasil belum tersedia")
    stems_dir = job.get("stems_dir", "")
    file_path = os.path.join(stems_dir, f"{stem_key}.mp3")
    if stem_key not in STEM_LABELS or not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Stem tidak ditemukan")
    safe_title = (job.get("title") or "audio")[:60]
    filename = f"{safe_title} - {STEM_LABELS[stem_key]}.mp3"
    return FileResponse(file_path, filename=filename, media_type="audio/mpeg")


@app.get("/api/split/{job_id}/download-all")
def download_all_stems(job_id: str):
    job = split_jobs.get(job_id)
    if not job or job["status"] != "done":
        raise HTTPException(status_code=404, detail="Hasil belum tersedia")
    stems_dir = job.get("stems_dir", "")
    zip_path = os.path.join(os.path.dirname(stems_dir), "stems.zip")
    if not os.path.exists(zip_path):
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for stem in job.get("stems", []):
                zf.write(os.path.join(stems_dir, stem["filename"]), arcname=stem["filename"])
    safe_title = (job.get("title") or "audio")[:60]
    return FileResponse(zip_path, filename=f"{safe_title} - stems.zip", media_type="application/zip")


app.mount("/", StaticFiles(directory="app/static", html=True), name="static")
