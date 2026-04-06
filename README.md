# NiceCount MVP

MVP aplikasi analisa kendaraan berbasis `FastAPI + PostgreSQL + local storage + YOLO`.

Alur minimum yang sudah dibuat:

1. User login
2. Admin kelola user
3. User upload video
4. User pilih video
5. Sistem jalankan analisa kendaraan
6. Hasil event dan total golongan masuk ke database dan tampil di halaman analisa

## Modul

- `Login User`
- `Kelola User`
- `Kelola Video`
- `Analisa Video`

## Halaman Web

- `/login`
- `/users`
- `/videos`
- `/analysis`

Semua halaman memakai asset theme Metronic dari folder `templates/metronic`.

## Struktur Data Utama

- `users`
- `sites`
- `count_lines`
- `video_uploads`
- `analysis_jobs`
- `vehicle_events`
- `analysis_golongan_totals`

## Klasifikasi Golongan

Yang disimpan saat ini:

- `Golongan I`
- `Golongan II`
- `Golongan III`
- `Golongan IV`
- `Golongan V`

Catatan:

- Untuk `car`, `motorcycle`, dan `bus`, MVP ini memetakan ke `Golongan I`.
- Untuk `truck`, `Golongan II` sampai `Golongan V` saat ini dihitung dengan heuristik ukuran bounding box dari kamera tunggal.
- Jadi hasil golongan berat belum bisa dianggap sama dengan hitung sumbu aktual. Itu perlu model/dataset yang lebih spesifik di tahap berikut.

## Setup

1. Buat virtualenv dan install dependency

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

2. Copy env

```bash
cp .env.example .env
```

3. Buat database

```bash
psql -d postgres -f sql/00_create_database.sql
psql -d vehicle_count -f sql/01_schema.sql
```

Kalau database sudah terbuat dari schema lama, jalankan migrasi:

```bash
psql -d vehicle_count -f sql/03_mvp_minimal_app.sql
```

4. Jalankan server

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## Windows Auto Install

Saya juga menyiapkan script Windows di [scripts/windows/install_windows.ps1](/Users/gianovembrian/gitlab-project/vehicle_count/scripts/windows/install_windows.ps1) dan wrapper [install_windows.bat](/Users/gianovembrian/gitlab-project/vehicle_count/scripts/windows/install_windows.bat).

## Windows One-Command Bootstrap

Kalau ingin PC Windows baru langsung siap tanpa install manual `Git`, `Python`, dan `PostgreSQL`, gunakan bootstrap script:

- [bootstrap_full_windows.ps1](/Users/gianovembrian/gitlab-project/vehicle_count/scripts/windows/bootstrap_full_windows.ps1)
- [bootstrap_full_windows.bat](/Users/gianovembrian/gitlab-project/vehicle_count/scripts/windows/bootstrap_full_windows.bat)
- [NiceCount_Install_Launcher.bat](/Users/gianovembrian/gitlab-project/vehicle_count/scripts/windows/NiceCount_Install_Launcher.bat)

Yang dilakukan bootstrap:

1. install `Git` bila belum ada
2. install `Python 3.11` bila belum ada
3. install `PostgreSQL` bila belum ada
4. pastikan `git`, `python`, dan `psql` bisa dipakai
5. download installer NiceCount
6. clone repo
7. buat `.venv`
8. install package Python
9. buat `.env`
10. create database dan apply schema
11. jalankan NiceCount di `http://127.0.0.1:8000`

Catatan:

- Bootstrap ini butuh `winget` yang biasanya sudah ada di Windows 10/11 modern.
- Jalankan PowerShell sebagai Administrator, atau script akan meminta elevasi otomatis.
- Untuk install PostgreSQL secara silent, password superuser **harus diisi**. Default bootstrap memakai `postgres`.

Contoh one-liner paling praktis:

```powershell
powershell -ExecutionPolicy Bypass -Command "Invoke-WebRequest -Uri 'https://raw.githubusercontent.com/gianovembrian/nicecount/main/scripts/windows/bootstrap_full_windows.ps1' -OutFile $env:TEMP\bootstrap_nicecount.ps1; & $env:TEMP\bootstrap_nicecount.ps1 -RepoUrl 'https://github.com/gianovembrian/nicecount.git' -TargetDir 'C:\NiceCount' -PgUser 'postgres' -PgPassword 'postgres' -DatabaseName 'vehicle_count' -OpenBrowser"
```

Kalau user tidak ingin buka PowerShell, kamu juga bisa berikan file:

```text
scripts\windows\NiceCount_Install_Launcher.bat
```

File itu bisa langsung di-double-click untuk bootstrap penuh.

## Windows One-Command Update

Untuk server Windows yang **sudah terinstall**, gunakan update script ini:

- [update_windows.ps1](/Users/gianovembrian/gitlab-project/vehicle_count/scripts/windows/update_windows.ps1)
- [update_windows.bat](/Users/gianovembrian/gitlab-project/vehicle_count/scripts/windows/update_windows.bat)
- [NiceCount_Update_Launcher.bat](/Users/gianovembrian/gitlab-project/vehicle_count/scripts/windows/NiceCount_Update_Launcher.bat)

Yang dilakukan script update:

1. stop server NiceCount yang sedang berjalan
2. `git pull` update terbaru
3. install/update dependency Python
4. apply schema dan migration SQL
5. start server lagi

Catatan:

- script update **tidak menimpa** `.env` yang sudah ada
- kalau `.env` belum ada, script akan membuatnya dari `.env.example`

One-liner update yang bisa langsung dijalankan di PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -Command "Invoke-WebRequest -Uri 'https://raw.githubusercontent.com/gianovembrian/nicecount/main/scripts/windows/update_windows.ps1' -OutFile $env:TEMP\update_nicecount.ps1; & $env:TEMP\update_nicecount.ps1 -RepoUrl 'https://github.com/gianovembrian/nicecount.git' -TargetDir 'C:\NiceCount' -PgUser 'postgres' -PgPassword 'postgres' -DatabaseName 'vehicle_count' -OpenBrowser"
```

### Windows Double-Click Update

Kalau user tidak ingin buka PowerShell atau mengetik command panjang, ada 2 cara:

1. Kalau repo sudah terinstall di `C:\NiceCount`, cukup double click:

```text
C:\NiceCount\scripts\windows\update_windows.bat
```

Wrapper ini sekarang otomatis:
- memakai repo/folder saat ini (`-UseCurrentDirectory`)
- menjalankan update
- membuka browser setelah selesai

2. Kalau ingin file launcher terpisah yang bisa disimpan di desktop, pakai:

```text
scripts\windows\NiceCount_Update_Launcher.bat
```

Launcher ini akan:
- download `update_windows.ps1` terbaru dari GitHub
- menjalankan update ke `C:\NiceCount`
- memakai default PostgreSQL `postgres/postgres`

Kalau password PostgreSQL atau folder install berbeda, edit file BAT itu dulu sebelum dipakai.

Kalau mau password PostgreSQL yang berbeda:

```powershell
powershell -ExecutionPolicy Bypass -Command "Invoke-WebRequest -Uri 'https://raw.githubusercontent.com/gianovembrian/nicecount/main/scripts/windows/bootstrap_full_windows.ps1' -OutFile $env:TEMP\bootstrap_nicecount.ps1; & $env:TEMP\bootstrap_nicecount.ps1 -RepoUrl 'https://github.com/gianovembrian/nicecount.git' -TargetDir 'C:\NiceCount' -PgUser 'postgres' -PgPassword 'MyStrongPassword123!' -DatabaseName 'vehicle_count' -OpenBrowser"
```

Yang dilakukan script:

1. clone atau update repo
2. buat `.venv`
3. install package Python
4. buat `.env`
5. create database PostgreSQL bila belum ada
6. apply schema SQL
7. jalankan NiceCount di `http://127.0.0.1:8000`

Prerequisite Windows:

- `Git`
- `Python 3.9+`
- `PostgreSQL` yang sudah terpasang dan `psql.exe` ada di `PATH`

Contoh pakai dari PowerShell setelah repo ada di GitHub:

```powershell
powershell -ExecutionPolicy Bypass -Command "Invoke-WebRequest -Uri 'https://raw.githubusercontent.com/<owner>/<repo>/main/scripts/windows/install_windows.ps1' -OutFile $env:TEMP\install_nicecount.ps1; & $env:TEMP\install_nicecount.ps1 -RepoUrl 'https://github.com/<owner>/<repo>.git' -TargetDir 'C:\NiceCount' -PgUser 'postgres' -PgPassword '' -DatabaseName 'vehicle_count' -OpenBrowser"
```

Kalau script dijalankan dari folder repo yang sudah ada di Windows:

```powershell
.\scripts\windows\install_windows.ps1 -UseCurrentDirectory -PgUser postgres -PgPassword ""
```

Opsi penting:

- `-RepoUrl` : URL repo GitHub
- `-TargetDir` : folder instalasi di Windows
- `-PgHost` : default `localhost`
- `-PgPort` : default `5432`
- `-PgUser` : default `postgres`
- `-PgPassword` : password PostgreSQL
- `-DatabaseName` : default `vehicle_count`
- `-NoRun` : setup saja, server tidak langsung dijalankan
- `-UseReload` : jalankan `uvicorn --reload`
- `-OpenBrowser` : buka browser otomatis ke halaman login

## Bootstrap Default

Saat startup, aplikasi akan memastikan:

- ada user admin default
- ada site default
- ada count line aktif default

Default login lokal:

- username: `admin`
- password: `admin123`

Bisa diubah lewat `.env`.

## Endpoint Utama

- `GET /health`
- `POST /api/auth/login`
- `POST /api/auth/logout`
- `GET /api/auth/me`
- `GET /api/users`
- `POST /api/users`
- `PUT /api/users/{user_id}`
- `PUT /api/users/{user_id}/password`
- `DELETE /api/users/{user_id}`
- `GET /api/videos`
- `POST /api/videos`
- `GET /api/videos/{video_id}`
- `PUT /api/videos/{video_id}`
- `DELETE /api/videos/{video_id}`
- `POST /api/videos/{video_id}/analysis/start`
- `GET /api/videos/{video_id}/analysis`
- `GET /api/videos/{video_id}/analysis/events`
- `GET /api/videos/{video_id}/analysis/totals`

## Contoh Upload Video

```bash
curl -X POST http://127.0.0.1:8000/api/videos \
  -b cookie.txt \
  -F "description=Video ruas pagi hari" \
  -F "recorded_at=2026-04-02T07:00:00+07:00" \
  -F "file=@/path/to/video.mp4"
```

## Contoh Start Analisa

```bash
curl -X POST http://127.0.0.1:8000/api/videos/<VIDEO_ID>/analysis/start \
  -H "Content-Type: application/json" \
  -b cookie.txt \
  -d '{}'
```
