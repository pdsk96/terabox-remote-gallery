# TeraBox Remote Gallery

Dashboard web Flask untuk mengelola file TeraBox melalui API web (unofficial).  
Fitur: list folder, rename/move/copy/delete/mkdir, streaming video HLS, thumbnail, live refresh, serta proxy media dengan SSRF protection.

## 🔧 Instalasi

```bash
pip install -r requirements.txt
```

## 🚀 Menjalankan

```bash
# Via module
python -m terabox_dashboard

# Atau langsung
python terabox_dashboard/app.py --host 127.0.0.1 --port 8080
```

Buka http://127.0.0.1:8080 → tempel cookie `ndus` dari browser TeraBox Anda.

### Cara ambil cookie `ndus`

1. Buka https://1024terabox.com di browser (Chrome/Edge/Firefox)
2. Login dengan akun TeraBox Anda
3. Buka DevTools (F12) → Tab **Application** → **Cookies** → https://1024terabox.com
4. Cari cookie bernama `ndus`, salin nilainya
5. Tempel ke halaman login dashboard

> ⚠️ Cookie `ndus` biasanya expired setelah beberapa hari. Jika login gagal, ambil cookie baru dari browser.

### Environment Variables

| Variable | Default | Deskripsi |
|----------|---------|-----------|
| `TERABOX_HOST` | `https://dm.1024terabox.com` | Base URL API TeraBox |
| `SECRET_KEY` | random 32-byte hex | Flask session secret |
| `TERABOX_FORCE_HTTPS` | `0` | Set `1` untuk `SESSION_COOKIE_SECURE=1` |
| `TERABOX_DEBUG` | `0` | Set `1` untuk Flask debug mode |

## 🛡️ Keamanan

| Fituran | Deskripsi |
|---------|-----------|
| **SSRF Protection** | Proxy hanya mengizinkan host TeraBox/CDN resmi (whitelist). Bukan IP private/loopback. |
| **Server-side Session** | Session disimpan di memori server dengan TTL 24 jam + background cleanup otomatis. |
| **Cookie** | `HttpOnly`, `SameSite=Lax`, `Secure` (jika HTTPS). |
| **CSP** | Header Content-Security-Policy ketat. |
| **Path Traversal** | Normalisasi path pada operasi file (mkdir, op). |
| **CORS + Range** | Header `Access-Control-Allow-Origin` dan `Range` untuk HLS.js dan video seeking. |

⚠️ **Peringatan**: Jalankan hanya di jaringan tepercaya. Dashboard ini tidak punya autentikasi sendiri — siapa pun yang dapat mengakses host dapat login dengan cookie Anda.

## 📁 Arsitektur

```
terabox_dashboard/
├── __init__.py           # Package export + versi
├── __main__.py           # Entry point `python -m terabox_dashboard`
├── app.py                # Flask factory, middleware, security headers, error handlers
├── config.py             # Settings, konstanta, env parsing
├── requirements.txt      # Dependensi Python
├── README.md             # Dokumentasi
├── services/
│   ├── __init__.py
│   ├── session.py        # Server-side session store (TTL, cleanup bg thread)
│   └── terabox.py        # TeraBox API client (auth, quota, list, ops, dlink, HLS)
├── routes/
│   ├── __init__.py       # Blueprint registration
│   ├── auth.py           # /api/login, /api/logout, /api/me
│   ├── files.py          # /api/list, /api/op, /api/mkdir
│   └── proxy.py          # /proxy/u, /proxy/file, /proxy/hls
├── utils/
│   ├── __init__.py
│   ├── helpers.py        # fmt_size, norm_file, rewrite_m3u8, join_path
│   └── security.py       # SSRF guard, parse_ndus, normalize_path, validate_operation
└── templates/
    └── index.html        # Frontend (Vanilla JS + hls.js CDN, mobile-responsive)
```

## 🌐 API Endpoints

| Method | Path | Deskripsi |
|--------|------|-----------|
| POST | `/api/login` | Login dengan cookie `ndus` |
| POST | `/api/logout` | Logout & hapus session |
| GET | `/api/me` | Cek status login & quota |
| GET | `/api/list` | List file (`dir`, `order`, `page`, `num`) |
| POST | `/api/op` | Operasi file: `rename`, `move`, `copy`, `delete` |
| POST | `/api/mkdir` | Buat folder baru |
| GET | `/proxy/u` | Proxy URL generik (thumbnail, segment HLS) |
| GET | `/proxy/file` | Proxy direct download link (`dlink`) |
| GET | `/proxy/hls` | Proxy manifest HLS (`path`, `q=480\|720\|1080`) |
| GET | `/healthz` | Health check |

## ⚡ Optimasi Streaming Video

- **HLS manifest cache** 2 menit per kualitas (480p/720p/1080)
- **dlink cache** 10 menit per path file
- **hls.js buffer** dikonfigurasi untuk VOD (30–60 detik)
- **Range request** didukung untuk seeking video
- **Thumbnail** di-load lazy melalui `/proxy/u`
- Mulai dari kualitas 480p, naik otomatis berdasarkan bandwidth

## ❓ Troubleshooting

| Masalah | Penyebab kemungkinan | Solusi |
|---------|---------------------|--------|
| "Login gagal: cookie kedaluwarsa/salah" | Cookie `ndus` expired atau salah domain | Ambil cookie `ndus` baru setelah login di browser |
| "Gagal ambil token: ..." | API domain berubah | Periksa `TERABOX_HOST`, default sudah `dm.1024terabox.com` |
| Video tidak putar / buffer lama | HLS segment diblokir CORS | Pastikan proxy berjalan, periksa konsol browser (F12) |
| Thumbnail tidak muncul | Gambar thumbnail tidak tersedia | TeraBox mungkin tidak menyediakan thumbnail untuk file tersebut |

## ⚠️ Disclaimer

Ini menggunakan API web TeraBox yang **tidak resmi**. Endpoint, `app_id`, `jsToken`, atau `bdstoken` bisa berubah sewaktu-waktu tanpa pemberitahuan. Gunakan dengan risiko sendiri.

## Lisensi

MIT — gunakan dengan risiko sendiri.
