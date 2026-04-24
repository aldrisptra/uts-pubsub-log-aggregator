# Laporan Pub-Sub Log Aggregator dengan Idempotent Consumer dan Deduplication

## 1. Ringkasan Sistem

Project ini membangun layanan Pub-Sub log aggregator lokal berbasis Python FastAPI. Sistem menerima event dari publisher melalui endpoint `POST /publish`, memvalidasi schema event, lalu memasukkan event ke `asyncio.Queue`. Consumer worker mengambil event dari queue dan melakukan deduplication berdasarkan pasangan `(topic, event_id)`.

Event yang unik disimpan ke SQLite sebagai durable dedup store. Jika event dengan pasangan `(topic, event_id)` yang sama diterima ulang, event tersebut tidak diproses ulang dan dicatat sebagai duplikasi. Dengan desain ini, consumer bersifat idempotent karena pemrosesan event yang sama berkali-kali tetap menghasilkan state akhir yang sama.

Sistem menyediakan endpoint `GET /events?topic=...` untuk melihat event unik yang sudah diproses dan `GET /stats` untuk melihat statistik seperti jumlah event diterima, event unik, duplikasi yang dibuang, daftar topic, dan uptime.

## 2. Arsitektur Sistem

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

Arsitektur ini memakai pola publish-subscribe secara sederhana di dalam satu layanan lokal. Publisher tidak langsung memproses event, tetapi hanya mengirim event ke aggregator. Di sisi internal, queue memisahkan proses penerimaan event dan pemrosesan event. Pemisahan ini membuat sistem lebih mudah dikembangkan untuk skenario asynchronous processing.

## 3. Keputusan Desain

### 3.1 Idempotency

Consumer dibuat idempotent dengan memastikan satu event hanya diproses satu kali berdasarkan pasangan `(topic, event_id)`. Jika event yang sama diterima ulang, SQLite akan menolak insert karena terdapat primary key pada `(topic, event_id)`. Dengan demikian, pemrosesan ulang tidak mengubah state akhir sistem.

### 3.2 Deduplication Store

SQLite dipilih karena ringan, embedded, lokal, dan tidak membutuhkan layanan eksternal. Tabel `processed_events` memakai primary key gabungan:

```sql
PRIMARY KEY (topic, event_id)
```

Dengan desain ini, deduplication tetap bertahan setelah aplikasi atau container restart selama file database tetap tersimpan. Pada Docker, persistensi dilakukan dengan volume:

```powershell
docker run -p 8080:8080 -v aggregator-data:/app/data uts-aggregator
```

### 3.3 Ordering

Total ordering tidak diwajibkan dalam sistem ini karena aggregator hanya menyimpan log unik, bukan menjalankan transaksi global yang bergantung pada urutan semua event. Event tetap memiliki `timestamp` ISO8601 untuk membantu observasi dan analisis. Namun, timestamp tidak dijadikan satu-satunya dasar ordering karena clock antar source dapat berbeda.

### 3.4 Reliability

Sistem mensimulasikan at-least-once delivery dengan mengirim event yang sama lebih dari satu kali. Duplikasi ditangani oleh idempotent consumer dan durable dedup store. Crash/restart ditangani dengan SQLite yang disimpan pada persistent volume.

## 4. API dan Model Event

Model event minimal:

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

Endpoint yang disediakan:

- `POST /publish`: menerima single event atau batch event.
- `GET /events?topic=...`: menampilkan event unik yang telah diproses.
- `GET /stats`: menampilkan statistik sistem.

## 5. Evaluasi Implementasi

Unit test dijalankan menggunakan pytest dengan hasil:

```text
9 passed
```

Cakupan test meliputi:

- Deduplication event duplikat.
- Batch event dengan duplikasi.
- Persistensi dedup store setelah reopen.
- Validasi schema event.
- Validasi timestamp.
- Konsistensi `GET /events` dan `GET /stats`.
- Stress test 5.000 event dengan 20% duplikasi.

Pada stress test, sistem menerima 5.000 event dengan 4.000 event unik dan 1.000 duplikasi. Hasil yang diharapkan adalah `received = 5000`, `unique_processed = 4000`, dan `duplicate_dropped = 1000`.

Pada pengujian Docker Compose, service `publisher` mengirim 5.000 event ke service `aggregator` melalui jaringan internal Compose. Event terdiri dari 4.000 event unik dan 1.000 event duplikat. Setelah proses selesai dan container aggregator dijalankan ulang, endpoint `/stats` menunjukkan `unique_processed = 4000`, sedangkan `GET /events?topic=app.compose` mengembalikan 4.000 event. Hal ini menunjukkan bahwa SQLite dedup store tetap persisten setelah restart container.

## 6. Jawaban Teori T1–T8

### T1 — Karakteristik Sistem Terdistribusi dan Trade-off Pub-Sub Log Aggregator

Sistem terdistribusi adalah kumpulan komponen yang berjalan pada komputer atau proses berbeda, tetapi terlihat sebagai satu sistem yang terkoordinasi. Karakteristik utamanya meliputi concurrency, tidak adanya global clock yang sempurna, komunikasi melalui jaringan, serta kemungkinan partial failure, yaitu sebagian komponen gagal sementara komponen lain tetap berjalan. Pada Pub-Sub log aggregator, karakteristik ini terlihat dari pemisahan peran publisher, aggregator, queue, dan consumer. Publisher hanya mengirim event, sedangkan consumer memproses event secara asynchronous. Trade-off utamanya adalah antara loose coupling dan kompleksitas reliability. Dengan Pub-Sub, publisher tidak perlu mengetahui detail consumer sehingga sistem lebih mudah diskalakan dan dikembangkan. Namun, desain ini menimbulkan tantangan seperti duplicate delivery, out-of-order event, dan kebutuhan deduplication. Karena jaringan dan proses dapat gagal, sistem memilih pendekatan at-least-once delivery yang lebih praktis, lalu mengandalkan idempotent consumer untuk menjaga hasil akhir tetap benar. Hal ini sesuai dengan pembahasan karakteristik sistem terdistribusi seperti heterogeneity, openness, scalability, dan failure handling pada Bab 1 (Tanenbaum & Van Steen, 2007).

### T2 — Client-Server vs Publish-Subscribe untuk Aggregator

Arsitektur client-server menggunakan hubungan langsung antara client sebagai pengirim request dan server sebagai pemroses request. Model ini cocok untuk operasi request-response yang sederhana, misalnya client meminta data dan server langsung mengembalikan hasil. Namun, untuk log aggregator, pendekatan client-server murni kurang fleksibel karena publisher akan lebih bergantung pada server pemroses. Publish-subscribe lebih cocok ketika banyak publisher mengirim event ke sistem dan pemrosesan event dapat dilakukan secara asynchronous. Dalam Pub-Sub, publisher cukup menerbitkan event ke topic tertentu, sedangkan subscriber atau consumer memproses event tanpa harus diketahui langsung oleh publisher. Keuntungan teknisnya adalah loose coupling, scalability, dan separation of concerns. Publisher tidak perlu menunggu proses deduplication selesai secara langsung, karena event dapat masuk ke queue dan diproses oleh consumer. Pub-Sub dipilih ketika sistem membutuhkan pemrosesan event/log dalam jumlah besar, kemungkinan banyak source, dan toleransi terhadap retry. Kekurangannya adalah ordering dan delivery semantics menjadi lebih kompleks. Perbandingan ini berkaitan dengan pembahasan arsitektur sistem terdistribusi dan communication style pada Bab 2 (Tanenbaum & Van Steen, 2007).

### T3 — At-least-once vs Exactly-once Delivery Semantics

At-least-once delivery berarti sistem menjamin event dikirim minimal satu kali, tetapi event yang sama dapat diterima lebih dari satu kali. Semantics ini umum dipakai karena lebih mudah dicapai pada sistem yang memiliki retry saat terjadi failure. Jika publisher tidak menerima acknowledgement, publisher dapat mengirim ulang event, sehingga risiko kehilangan event berkurang. Namun, konsekuensinya adalah muncul duplicate event. Exactly-once delivery berarti event diproses tepat satu kali. Secara konseptual, model ini ideal, tetapi dalam sistem terdistribusi sangat sulit dan mahal karena membutuhkan koordinasi kuat, penyimpanan status yang konsisten, dan mekanisme transaksi atau acknowledgement yang ketat. Pada implementasi aggregator ini, pendekatan yang dipilih adalah at-least-once delivery dengan idempotent consumer. Consumer menjadi krusial karena retry dapat menyebabkan event yang sama masuk berulang kali. Dengan deduplication berdasarkan `(topic, event_id)`, consumer hanya memproses event unik satu kali. Jika duplicate event diterima, state akhir tetap tidak berubah. Ini menunjukkan bahwa idempotency adalah strategi praktis untuk menghadapi retry dan duplicate delivery pada komunikasi terdistribusi sebagaimana dibahas dalam Bab 3 (Tanenbaum & Van Steen, 2007).

### T4 — Skema Penamaan Topic dan Event ID

Skema penamaan topic pada aggregator ini menggunakan pola hierarkis berbasis domain, misalnya `app.login`, `app.payment`, atau `service.domain.action`. Pola ini memudahkan pengelompokan event berdasarkan konteks dan sumber log. Topic yang jelas membantu subscriber memfilter event, memudahkan observability, dan membuat endpoint `GET /events?topic=...` lebih mudah digunakan. Untuk `event_id`, sistem sebaiknya menggunakan identifier yang unik dan collision-resistant, misalnya UUID, ULID, atau kombinasi source dengan monotonic counter. Pada implementasi dan pengujian, `event_id` dibuat eksplisit seperti `evt-001`, `pay-001`, atau `stress-1`, tetapi dalam production design lebih aman memakai UUID/ULID. Deduplication key yang digunakan adalah pasangan `(topic, event_id)`, bukan hanya `event_id`. Dengan demikian, dua event dari topic berbeda tidak dianggap duplikat walaupun memiliki `event_id` yang sama. Skema ini juga memudahkan penamaan dan pencarian object dalam sistem terdistribusi, sesuai pembahasan naming dan identifier pada Bab 4. Penamaan yang konsisten sangat penting karena kesalahan desain identifier dapat menyebabkan false duplicate atau collision yang mengganggu hasil deduplication (Tanenbaum & Van Steen, 2007).

### T5 — Ordering, Timestamp, dan Clock

Total ordering tidak selalu diperlukan pada log aggregator. Dalam sistem ini, tujuan utama aggregator adalah menyimpan event unik dan mencegah pemrosesan ulang event yang sama, bukan menjalankan transaksi global yang bergantung pada urutan semua event. Karena itu, ordering yang dibutuhkan cukup bersifat praktis, misalnya berdasarkan `timestamp`, `processed_at`, atau urutan masuk ke queue. Total ordering akan menambah kompleksitas karena membutuhkan koordinasi antar source atau mekanisme sequencer global. Pada sistem terdistribusi, setiap node dapat memiliki clock yang berbeda, sehingga timestamp dari publisher tidak selalu sepenuhnya akurat. Pendekatan praktis yang dapat digunakan adalah kombinasi event timestamp ISO8601, source identifier, dan monotonic counter per source. Dengan cara ini, event dari source yang sama dapat diurutkan lebih mudah, meskipun global ordering tetap tidak dijamin. Batasannya adalah clock skew, network delay, dan kemungkinan event datang terlambat. Oleh karena itu, laporan event sebaiknya tidak mengandalkan timestamp sebagai satu-satunya sumber kebenaran. Pertimbangan ini berkaitan dengan pembahasan time, clock synchronization, dan event ordering pada Bab 5 (Tanenbaum & Van Steen, 2007).

### T6 — Failure Modes dan Strategi Mitigasi

Failure modes utama pada Pub-Sub log aggregator meliputi duplicate delivery, out-of-order event, crash pada aggregator, queue loss, dan kegagalan saat menulis ke dedup store. Duplicate delivery dapat terjadi ketika publisher melakukan retry karena tidak menerima acknowledgement. Out-of-order event dapat terjadi karena perbedaan latency atau clock antar source. Crash dapat menyebabkan event yang masih berada di memory queue belum sempat diproses. Strategi mitigasi yang diterapkan adalah idempotent consumer dan durable dedup store menggunakan SQLite. Duplikasi ditangani dengan primary key `(topic, event_id)`, sehingga event yang sama tidak dapat disimpan dua kali. Untuk crash/restart, file SQLite disimpan melalui Docker volume sehingga event yang sudah diproses tetap tercatat setelah container dijalankan ulang. Retry dan backoff dapat diterapkan pada publisher agar pengiriman ulang tidak membanjiri aggregator. Logging juga penting untuk mendeteksi duplicate event dan memudahkan debugging. Kelemahan implementasi ini adalah queue masih in-memory, sehingga event yang sudah diterima tetapi belum diproses dapat hilang jika proses crash. Failure handling seperti ini berhubungan dengan prinsip fault tolerance pada Bab 6 (Tanenbaum & Van Steen, 2007).

### T7 — Eventual Consistency, Idempotency, dan Deduplication

Eventual consistency berarti sistem tidak harus selalu langsung konsisten pada setiap saat, tetapi jika tidak ada update baru dan semua event telah selesai diproses, sistem akhirnya mencapai state yang benar. Pada aggregator ini, event yang masuk melalui `POST /publish` diterima terlebih dahulu, lalu diproses secara asynchronous oleh consumer worker dari `asyncio.Queue`. Karena ada pemisahan antara penerimaan dan pemrosesan, mungkin terdapat jeda singkat sebelum event muncul di `GET /events` atau tercermin pada `GET /stats`. Namun, setelah queue selesai diproses, state akhir akan berisi hanya event unik. Idempotency dan deduplication membantu mencapai konsistensi karena duplicate event tidak menyebabkan state akhir berubah secara berlebihan. Tanpa deduplication, retry dapat membuat event yang sama tersimpan berkali-kali dan menyebabkan hasil statistik tidak benar. Dengan primary key `(topic, event_id)`, sistem memastikan setiap event logis hanya memiliki satu representasi dalam store. Model ini sesuai dengan gagasan consistency dan replication, yaitu bagaimana sistem mempertahankan state yang dapat diterima meskipun ada delay, duplikasi, dan komunikasi asynchronous seperti dibahas pada Bab 7 (Tanenbaum & Van Steen, 2007).

### T8 — Metrik Evaluasi Sistem dan Kaitan dengan Desain

Metrik evaluasi yang relevan untuk Pub-Sub log aggregator meliputi throughput, latency, duplicate rate, jumlah event unik, error rate, dan recovery setelah restart. Throughput menunjukkan jumlah event yang dapat diterima atau diproses per satuan waktu. Pada tugas ini, sistem diuji dengan 5.000 event dan minimal 20% duplikasi untuk memastikan aggregator tetap responsif. Latency menunjukkan waktu dari event diterima sampai event selesai diproses dan tersedia melalui `GET /events`. Duplicate rate menunjukkan proporsi event yang dibuang karena memiliki `(topic, event_id)` yang sama. Metrik `received`, `unique_processed`, dan `duplicate_dropped` pada endpoint `GET /stats` dirancang untuk mengamati perilaku tersebut. Recovery setelah restart juga penting untuk mengevaluasi apakah dedup store benar-benar durable. Desain SQLite dipilih untuk menjaga data event unik tetap tersedia setelah container restart, sedangkan runtime stats seperti `received` dan `duplicate_dropped` dapat reset karena disimpan di memory. Metrik-metrik ini berkaitan dengan keputusan desain pada Bab 1–7, terutama scalability, communication, fault tolerance, dan consistency (Tanenbaum & Van Steen, 2007).

## 7. Referensi

Tanenbaum, A. S., & Van Steen, M. (2007). _Distributed systems: Principles and paradigms_. Pearson Prentice Hall.
