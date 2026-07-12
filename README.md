# YT Downloader

Website untuk download video/audio YouTube menggunakan [yt-dlp](https://github.com/yt-dlp/yt-dlp), dengan pilihan resolusi (tinggi/sedang/rendah), format, dan informasi bitrate untuk tiap opsi.

## Fitur
- Tempel link YouTube, lihat daftar format video (MP4/WebM, resolusi, fps, bitrate, ukuran file).
- Lihat daftar format audio-only (bitrate, ukuran file), download hasil diekstrak sebagai MP3.
- Kualitas dikelompokkan otomatis: **Tinggi** (≥1080p video / ≥192kbps audio), **Sedang**, **Rendah**.
- Video kualitas tinggi otomatis digabung (mux) dengan audio terbaik via ffmpeg saat proses download.
- **Pisah Instrumen (stem splitter)**: pisahkan audio menggunakan pilihan engine [Demucs](https://github.com/facebookresearch/demucs) (`htdemucs_6s`, 6 track — Vocal, Drum, Bass, Guitar, Piano, Others — kualitas terbaik, jalan di container utama) atau [Spleeter](https://github.com/deezer/spleeter) (Deezer `4stems`, 4 track — Vocal, Drum, Bass, Others — lebih cepat, jalan di container terpisah `spleeter-worker` karena dependensinya — TensorFlow + Python lama — bentrok dengan Demucs/PyTorch; Spleeter tidak punya model pemisah gitar/piano). Kualitas output MP3 bisa dipilih: 128/192/320kbps. Proses berjalan sebagai job di background (server men-download audio → engine terpilih memisahkan → hasil MP3 per stem + opsi download semua sebagai ZIP).

## Menjalankan dengan Docker Compose

```bash
docker compose up -d --build
```

Buka `http://localhost:8899` di browser (ubah port di `docker-compose.yml` jika perlu).

File yang sedang diproses disimpan sementara di folder `downloads/` (host) lalu dihapus otomatis setelah terkirim ke browser. Hasil pemisahan instrumen disimpan di `splits/` dan otomatis dibersihkan setelah 1 jam.

Build pertama akan lebih lama (±beberapa menit, dua image: `ytdlp-web` dan `spleeter-worker`) karena mengunduh PyTorch/TensorFlow (CPU) dan bobot model Demucs (~80MB) serta Spleeter yang di-*bake* ke masing-masing image. Proses pemisahan instrumen berjalan di CPU (tidak pakai GPU) sehingga untuk lagu 3-4 menit bisa memakan waktu beberapa menit tergantung spesifikasi mesin dan engine yang dipilih.

## Update yt-dlp

YouTube sering mengubah mekanisme internalnya sehingga yt-dlp perlu diperbarui secara berkala. Untuk update:

```bash
docker compose build --no-cache
docker compose up -d
```

Atau pin versi terbaru di `backend/requirements.txt`.

## Struktur Proyek

```
backend/
  Dockerfile
  requirements.txt
  app/
    main.py          # FastAPI: /api/info, /api/download, /api/split
    static/           # frontend (HTML/CSS/JS vanilla)
spleeter-worker/
  Dockerfile
  requirements.txt
  app.py             # FastAPI internal: POST /separate (dipanggil backend saat engine=spleeter)
docker-compose.yml
downloads/             # volume sementara hasil download video/audio
splits/                # volume sementara hasil pisah instrumen
```

## Catatan
- Pastikan penggunaan sesuai hak cipta dan Ketentuan Layanan YouTube.
- Untuk video panjang/kualitas tinggi, proses download di server bisa memakan waktu karena melalui tahap merge video+audio dengan ffmpeg sebelum dikirim ke browser.
