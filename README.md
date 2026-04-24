# Pub-Sub Log Aggregator dengan Idempotent Consumer dan Deduplication

Project ini adalah layanan Pub-Sub log aggregator lokal berbasis Python FastAPI. Sistem menerima event/log dari publisher melalui endpoint HTTP, memasukkan event ke internal queue, lalu consumer worker memproses event secara idempotent dengan deduplication berdasarkan pasangan `(topic, event_id)`.

Deduplication disimpan di SQLite sehingga tetap bertahan setelah container restart.

## Fitur

- `POST /publish` menerima single event atau batch event.
- `GET /events?topic=...` menampilkan event unik yang sudah diproses.
- `GET /stats` menampilkan statistik sistem.
- Idempotent consumer: event dengan `(topic, event_id)` sama hanya diproses satu kali.
- Dedup store persisten menggunakan SQLite.
- Logging untuk event unik dan duplikat.
- Dockerfile dengan non-root user.
- Unit tests menggunakan pytest.

## Arsitektur

```text
Publisher
   |
   | POST /publish
   v
FastAPI Aggregator
   |
   | Validasi schema event
   v
asyncio.Queue
   |
   v
Consumer Worker
   |
   | Dedup check: (topic, event_id)
   v
SQLite Dedup Store
   |
   | Unique event disimpan
   | Duplicate event di-drop
   v
GET /events dan GET /stats
```

## Model Event

```json
{
  "topic": "app.login",
  "event_id": "evt-001",
  "timestamp": "2026-04-24T10:00:00Z",
  "source": "auth-service",
  "payload": {
    "user_id": "u123",
    "status": "success"
  }
}
```

## Cara Menjalankan Lokal

Buat virtual environment:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

Install dependency:

```powershell
pip install -r requirements.txt
```

Jalankan aplikasi:

```powershell
python -m src.main
```

Aplikasi berjalan di:

```text
http://localhost:8080
```

Dokumentasi Swagger tersedia di:

```text
http://localhost:8080/docs
```

## Cara Menjalankan dengan Docker

Build image:

```powershell
docker build -t uts-aggregator .
```

Run container:

```powershell
docker run -p 8080:8080 uts-aggregator
```

Run dengan persistent volume:

```powershell
docker run -p 8080:8080 -v aggregator-data:/app/data uts-aggregator
```

Persistent volume menyimpan file SQLite di `/app/data/events.db`, sehingga deduplication tetap efektif setelah container restart.

## Cara Menjalankan dengan Docker Compose

```powershell
docker compose up --build
```

## Menjalankan Tests

```powershell
python -m pytest -v
```

Expected result:

```text
9 passed
```

## Bukti Idempotency dan Deduplication

Jika event yang sama dikirim dua kali:

```json
{
  "topic": "app.login",
  "event_id": "evt-001",
  "timestamp": "2026-04-24T10:00:00Z",
  "source": "auth-service",
  "payload": {
    "user_id": "u123"
  }
}
```

Maka hasil `/stats` menjadi:

```json
{
  "received": 2,
  "unique_processed": 1,
  "duplicate_dropped": 1,
  "topics": {
    "app.login": 1
  }
}
```

Artinya event diterima dua kali, tetapi hanya diproses satu kali karena consumer bersifat idempotent.

## Asumsi Desain

- Delivery semantics yang disimulasikan adalah at-least-once delivery.
- Deduplication key adalah `(topic, event_id)`.
- SQLite digunakan sebagai local durable dedup store.
- Total ordering tidak diwajibkan karena aggregator hanya menyimpan log unik, bukan menjalankan transaksi yang bergantung pada urutan global.
- `received` dan `duplicate_dropped` adalah runtime stats.
- `unique_processed` dan daftar event unik dihitung dari SQLite sehingga tetap tersedia setelah restart.
- Semua komponen berjalan lokal dan tidak menggunakan layanan eksternal.

## Video Demo

Link video demo YouTube:

```text
TODO: masukkan link video demo di sini
```
