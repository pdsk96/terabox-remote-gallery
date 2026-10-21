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
│   ├── session.py        # Server-side session store (TTL, cleanup bg thread, persist disk)
│   ├── terabox.py        # TeraBox API client (auth, quota, list, ops, dlink, HLS)
│   ├── resource.py       # Channel feed: hot recommend, list, search, share resolve/transfer, favor
│   └── follows.py        # Daftar channel yang diikuti (lokal, persists disk)
├── routes/
│   ├── __init__.py       # Blueprint registration
│   ├── auth.py           # /api/login, /api/logout, /api/me
│   ├── files.py          # /api/list, /api/op, /api/mkdir
│   ├── proxy.py          # /proxy/u, /proxy/file, /proxy/hls
│   └── channels.py       # Channel: /api/channel/feed, /categories, /search, /follows,
│   │                     # /follow, /unfollow, /share/resolve, /share/mine,
│   │                     # /share/save, /share/status, /like, /likes
├── utils/
│   ├── __init__.py
│   ├── helpers.py        # fmt_size, norm_file, rewrite_m3u8, join_path
│   └── security.py       # SSRF guard, parse_ndus, normalize_path, validate_operation
└── templates/
    └── index.html        # Frontend (Vanilla JS + hls.js CDN, mobile-responsive, 3 tab)
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

## 📺 Tab Channel — Feed Konten & Simpan Share

Tab Channel menampilkan feed konten publik TeraBox dan memungkinkan menyimpan (transfer) file dari share orang lain ke drive Anda sendiri — semua melalui server-to-server, tidak perlu download ke perangkat.

| Method | Path | Deskripsi |
|--------|------|-----------|
| GET | `/api/channel/feed` | Feed konten (`kind`, `category`, `page`, `count`, `scope`) |
| GET | `/api/channel/categories` | Daftar kategori (per country) + channel bawaan |
| GET | `/api/channel/countries` | Negara yang punya konten feed |
| GET | `/api/channel/search` | Cari konten (`q`, `count`) |
| GET | `/api/channel/search/suggest` | Saran pencarian agregat (`q`) |
| GET | `/api/channel/search/history` | Riwayat pencarian |
| POST | `/api/channel/search/history/clear` | Hapus riwayat pencarian |
| GET | `/api/channel/follows` | Channel yang diikuti |
| POST | `/api/channel/follow` | Ikuti channel (`name`, `link`, `share_id`, `uk`) |
| POST | `/api/channel/unfollow` | Berhenti mengikuti (`name`) |
| GET | `/api/channel/share/resolve` | Resolve share link → daftar file (`url`) |
| GET | `/api/channel/share/mine` | Share link milik sendiri (`page`, `num`) |
| POST | `/api/channel/share/save` | Simpan file share ke drive (`share_id`, `uk`, `fs_ids`, `path`, `ondup`) |
| GET | `/api/channel/share/status` | Cek status transfer (`sid`, `suk`) |
| POST | `/api/channel/like` | Like/unlike resource (`fs_id`, `flag`) |
| GET | `/api/channel/likes` | Item yang sudah di-like |

### Sub-fungsi Channel

| Sub-tab | Fungsi |
|---------|--------|
| **Feed** | Konten publik TeraBox (film/series/video), filter kategori, filter channel, next-page pagination |
| **Diikuti** | Channel uploader yang Anda ikuti; feed difilter hanya milik mereka |
| **Cari** | Pencarian konten + riwayat pencarian |
| **Disukai** | Item yang sudah Anda like (`/api/favor/mark`) |
| **Share** | Tempel share link → lihat isi → pilih file → simpan ke drive Anda |

Tombol **⭐** pada setiap item untuk mengikuti/unfollow channel uploader. Tombol **💾 Simpan** memindahkan file dari share orang lain ke folder tujuan di drive Anda (server-to-server).

**Catatan penting**: TeraBox tidak menyediakan endpoint "subscribe channel" resmi, daftar channel diikuti disimpan secara lokal di server dashboard (`~/.terabox_dashboard/follows.json`). Transfer share mungkin ditolak server (errno 120 = share kadaluarsa, errno 4 = konflik path) tergantung kebijakan akun pemilik share.

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
| Transfer share gagal (errno 17) | Share kadaluarsa / konflik path | Lihat detail `info[]` (errno 120 = share tidak tersedia, errno 4 = konflik path) |
| Kategori kosong | Negara tidak punya konten resource | Pilih negara lain di dropdown negara (default otomatis pilih negara dengan konten) |

## ⚠️ Disclaimer

Ini menggunakan API web TeraBox yang **tidak resmi**. Endpoint, `app_id`, `jsToken`, atau `bdstoken` bisa berubah sewaktu-waktu tanpa pemberitahuan. Gunakan dengan risiko sendiri.

## Lisensi

MIT — gunakan dengan risiko sendiri.
