# Review GeoSquare Grid V1 dan V2

**Tanggal:** 2026-09-18
**Cakupan:** `geosquare-grid` (V1) dan `geosquare-grid-v2` (V2)
**Jenis review:** Review arsitektur dan implementasi
**Rekomendasi:** Lanjutkan arah V2. Tapi jangan anggap V2 siap produksi sebelum masalah rilis, migrasi, batas negara, dan pengujian selesai.

## Ringkasan

Gagasan utama GeoSquare sudah tepat. Lokasi dibuat sebagai susunan kotak yang mudah dipahami. Geometri dihitung dari ID saat dibutuhkan. Kita tidak perlu menyimpan semua poligon sel grid.

V1 sudah punya beberapa ide penting:

- pembagian bergantian 5 dan 2;
- hubungan parent-child lewat prefix ID; dan
- geometri yang dihitung saat dibutuhkan.

Tapi V1 belum memakai grid metrik berbasis proyeksi negara. Implementasinya juga belum konsisten.

V2 adalah arah yang benar. V2 memperbaiki model identitas, proyeksi, geometri, hierarki, tetangga, jarak, polyfill, dan registri negara.

Tetapi V2 masih lebih tepat disebut **fondasi kandidat rilis**, bukan produk siap produksi.

Masalah utamanya:

- Adapter migrasi V1 ke V2 sudah dibuat, tetapi belum divalidasi lewat pytest dan belum dipakai untuk data produksi.
- Batas negara belum dipakai langsung oleh operasi utama.
- Belum ada bukti kuat untuk negara yang sangat lebar atau punya wilayah terpisah, seperti Amerika Serikat dan Rusia.
- “Kotak 50 m” akurat di CRS grid. Belum tentu akurat 50 m di permukaan bumi pada semua lokasi.
- API utama masih rumit untuk pengguna biasa.
- Private key lama sudah dihapus dari repository. Database saat ini sudah ditandatangani ulang dengan key baru yang disimpan di luar repository.
- Path registry aktif dan contoh loader sudah diperbaiki. Build wheel/sdist bersih masih perlu dijalankan.

**Keputusan utama:** Pertahankan model inti V2. Jadikan V1 sebagai decoder legacy. Jangan mencoba memperbaiki geometri V1 untuk menjadi fondasi baru.

## 1. Kriteria review

Review ini memakai tujuan berikut:

1. **Mudah dipahami:** pengguna bisa memahami ukuran, hierarki, dan posisi tanpa memahami detail proyeksi.
2. **Intuisi metrik:** sel 50 m kira-kira berarti 50 m x 50 m. Selisihnya harus dijelaskan.
3. **Hierarki jelas:** parent bisa dicari dari child. Child bisa dibuat dari parent. Tidak perlu query database.
4. **Hitung saat dibutuhkan:** ID dan profil menjadi sumber kebenaran. Poligon tidak perlu disimpan untuk setiap sel.
5. **Analisis grid:** tetangga, ring, dan jarak dihitung dari indeks integer.
6. **Scope negara:** setiap negara bisa punya proyeksi dan registri sendiri.
7. **Kompatibilitas:** data V1 bisa dipindahkan secara jelas ke V2. Polyfill dan operasi geometri tetap tersedia.
8. **Alamat untuk manusia:** alias yang lebih mudah disebut bisa ditambahkan tanpa menggantikan ID utama.

Ada dua hal yang perlu dipisahkan:

- **Domain matematika:** seluruh kotak besar tempat ID dan hubungan grid dihitung.
- **Batas operasional negara:** aturan untuk menentukan apakah sel dianggap masuk negara tertentu.

V2 sudah memisahkan dua konsep ini. Tapi produk tetap butuh API yang mudah untuk menerapkan aturan batas negara.

## 2. Review V1

### Hal yang sudah benar di V1

- Pembagian `5, 2, 5, 2, ...` membuat urutan ukuran yang mudah dipahami.
- ID bersifat hierarkis. Menghapus karakter terakhir secara konsep menghasilkan parent.
- Geometri dihitung dari ID.
- Sudah ada konsep polyfill dan pemetaan ukuran ke level.
- Matriks karakter menyimpan posisi baris dan kolom setiap pembagian.

Ide-ide ini layak dipertahankan. Tapi V1 belum cukup untuk menjadi grid metrik nasional.

### Masalah utama V1

#### 2.1 Koordinatnya bukan grid metrik negara

`geosquare-grid/src/geosquare_grid/core.py` memakai rentang hard-coded sekitar `(-217, 232.1576)` dan `(-216, 233.1576)`.

Tidak ada:

- transformasi CRS;
- profil negara;
- penanganan datum atau epoch; dan
- jaminan ukuran dalam meter.

Geometri V1 hanya berbentuk kotak pada bidang koordinat internal. Itu bukan kotak fisik yang akurat di bumi. Lebar timur-barat juga berubah menurut lintang.

Ini tidak cocok dengan tujuan sel 50 m atau proyeksi khusus negara.

#### 2.2 API object-nya rapuh

`GeosquareGrid` bersifat mutable dan bisa hanya terisi sebagian.

`get_gid()` dan `get_lonlat()` punya sedikit logika pemulihan. Tetapi `get_bound()` dan `get_geometry()` langsung memakai `self.gid`. Keduanya bisa gagal jika object belum diisi.

`from_gid()` juga belum memvalidasi panjang ID, karakter, dan level dengan baik.

Masalah lain:

- `from_address()` memanggil `address_to_gid()`, tetapi implementasi yang berfungsi tidak ada.
- `setup.cfg` mendaftarkan command `geosquare-grid = geosquare_grid:main`, tetapi `main` tidak ada di `__init__.py`.

#### 2.3 API hierarkinya belum jelas

Helper `_to_parent()` dan `_to_children()` menunjukkan konsep parent-child. Tetapi belum ada API publik yang rapi.

Nama method `parrent_to_allchildren` juga salah eja.

Perbandingan level di method itu juga keliru. Kode menghitung `len(key) - resolution`, bukan membandingkan target level secara langsung. Hasilnya bisa salah.

V1 juga belum punya operasi tetangga dan jarak grid.

#### 2.4 Polyfill masih ambigu dan tidak aman

Polyfill default dimulai dari sel level-1 `"2"`, bukan dari root domain yang jelas.

Dokumentasi dan kode untuk `fullcover` juga berbeda. Saat `fullcover=False`, kode hanya menerima sel dengan cakupan lebih dari 50% pada level terakhir. Itu bukan definisi “semua sel yang beririsan”.

V1 juga belum punya:

- perhitungan luas berdasarkan proyeksi;
- batas jumlah kandidat;
- aturan batas negara; dan
- perilaku yang jelas untuk geometri besar.

#### 2.5 Test V1 belum bisa menjadi kontrak

`geosquare-grid/tests/test_geosquare_grid.py` punya banyak fixture yang saling bertentangan. Contohnya:

- memanggil `lonlat_to_gid(..., level=14)` tetapi mengharapkan ID 11/12 karakter;
- memanggil `from_lonlat(..., level=5)` tetapi mengharapkan ID resolusi tinggi;
- mengharapkan bounds yang berbeda di beberapa test; dan
- memanggil `get_geometry()` dari object yang belum diinisialisasi.

README menyebut level 1–14. Tetapi `core.py` juga punya level 15 / 1 m.

Jadi perilaku V1 belum bisa dipakai sebagai kontrak kompatibilitas yang aman.

### Kesimpulan V1

V1 sebaiknya dianggap sebagai **prototype legacy**. Simpan decoder-nya untuk proses migrasi. Pertahankan ide hierarkinya. Tapi jangan teruskan model koordinatnya. Jangan pakai bare ID V1 sebagai ID V2.

## 3. Review V2

### Hal yang sudah jauh lebih baik

#### 3.1 Identitas utama sudah jelas

V2 memakai identitas utama berikut:

```text
(domain_code, level, x_idx, y_idx)
```

GID, packed integer, dan geometri hanya bentuk turunan dari identitas ini.

Ini keputusan yang bagus. Indeks integer membuat hierarki, tetangga, query area kotak, dan geometri lebih mudah dihitung.

Format eksternal V2 juga sudah diberi versi dan domain:

```text
geosquare:v2:<domain>:<gid>
```

Dengan begitu, bare GID V1 tidak mudah salah dianggap sebagai GID V2.

#### 3.2 Hierarki sesuai tujuan ukuran

V2 memakai root 50.000 km dan pembagian bergantian `[5, 2, 5, 2, ...]` sampai level 14.

| Level | Sisi sel di CRS grid |
|---:|---:|
| 0 | 50.000 km |
| 1 | 10.000 km |
| 2 | 5.000 km |
| 3 | 1.000 km |
| 4 | 500 km |
| 5 | 100 km |
| 6 | 50 km |
| 7 | 10 km |
| 8 | 5 km |
| 9 | 1 km |
| 10 | 500 m |
| 11 | 100 m |
| 12 | 50 m |
| 13 | 10 m |
| 14 | 5 m |

V2 berhenti di 5 m karena seluruh 49 bit jalur sudah dipakai oleh format signed Int64.

Ini masuk akal. Tetapi hilangnya level 1 m dari V1 harus dianggap sebagai perubahan kompatibilitas yang resmi.

#### 3.3 Geometri dihitung saat dibutuhkan

`src/geosquare_v2/grid.py` menghitung bounds dari origin, level, dan indeks.

`geometry.py` membuat kotak projected secara langsung. Untuk tampilan WGS84, garisnya dibuat lebih rapat dulu supaya bentuknya lebih akurat setelah transformasi.

Ini memenuhi prinsip compute-on-read. Geometri tampilan tidak menjadi sumber identitas.

#### 3.4 Analisis grid memakai cara yang tepat

`parent()`, `children()`, `neighbor()`, `k_disk()`, `k_ring()`, dan `distance_m()` bekerja dari indeks integer.

Ini lebih cepat dan lebih jelas daripada memakai buffer polygon.

Jarak saat ini didefinisikan sebagai jarak Euclidean pada CRS grid, untuk sel dengan level yang sama.

#### 3.5 Polyfill V2 jauh lebih kuat

`polyfill.py` sudah punya:

- transformasi CRS dengan `always_xy=True`;
- normalisasi polygon;
- clipping ke mathematical root;
- batas jumlah kandidat;
- urutan hasil yang konsisten;
- mode planar dan equal-area; dan
- rasio cakupan per sel.

Ini sudah cocok sebagai implementasi referensi.

Masalah tersisanya bukan algoritma polyfill. Masalahnya adalah cara pengguna mendapatkan domain yang benar dan menerapkan aturan batas negara.

#### 3.6 Arah registry sudah tepat

Registry bertanda tangan digital V2 menyimpan dan memeriksa:

- identitas domain;
- definisi CRS dalam WKT2;
- CRS equal-area;
- origin dan root;
- epoch;
- metadata galat skala;
- hash batas negara; dan
- resource PROJ.

ID dan VN adalah kandidat yang baik karena bentuk wilayah dan proyeksinya berbeda.

SQLite juga cocok untuk artefak rilis yang sudah diverifikasi.

## 4. Status terhadap kebutuhan

| Kebutuhan | Status | Catatan |
|---|---|---|
| Hierarki | **Ya** | V2 mempertahankan pola 5/2 dan ukuran yang mudah dipahami. |
| Parent-child | **Ya** | Indeks dan prefix GID mendukungnya tanpa menyimpan geometri. Test scalar masih perlu ditambah. |
| Compute-on-read | **Ya** | Bounds dan geometri dihitung dari ID/profil. |
| Sel se-kotak mungkin | **Ya di CRS; sebagian di bumi** | Sel kotak sempurna di CRS grid. Tidak selalu kotak sempurna di permukaan bumi. |
| Intuisi 50 m | **Sebagian besar ya** | Level 12 adalah kotak 50 m di CRS grid. Galat skalanya harus ditampilkan. |
| Kompatibilitas legacy | **Belum** | Adapter migrasi V1 ke V2 belum ada. |
| Polyfill | **Ya, dengan gap kebijakan** | Polyfill sudah kuat, tetapi batas negara belum diterapkan. |
| Analisis tetangga | **Ya di level inti** | Neighbour, ring, dan disk sudah ada. Versi yang sadar batas negara belum ada. |
| Jarak grid | **Ya untuk level sama** | Jarak integer Euclidean sudah ada. Jarak lintas level harus tetap eksplisit. |
| Proyeksi per negara | **Ada sebagai kandidat** | ID dan VN punya profil bertanda tangan digital dengan CRS grid dan equal-area. |
| Negara lebar/terpisah | **Belum terbukti** | Belum ada fixture untuk AS, Rusia, antimeridian, atau wilayah terpencil. |
| Registry negara | **Fondasi kuat** | Loader dan hash sudah ada. Path file dan default verifikasi perlu diperbaiki. |
| Alias manusia | **Belum ada** | Alias sebaiknya menjadi lapisan tampilan terpisah. |

## 5. Keputusan desain yang masih perlu dibuat

### 5.1 Jelaskan arti “kotak 50 m”

V2 sudah jujur secara teknis. Sel adalah kotak sempurna di CRS grid.

Itu tidak sama dengan jaminan bahwa ukuran fisiknya selalu tepat 50 m x 50 m di bumi.

Metadata kandidat saat ini mencatat kira-kira:

- Indonesia: galat skala arah maksimum sekitar `1,8711%`;
- Vietnam: galat skala arah maksimum sekitar `0,4922%`.

Jadi level 12 memang 50 m di grid. Ukuran di bumi bisa sedikit berbeda menurut lokasi dan arah.

Dokumentasi pengguna sebaiknya memakai kalimat seperti:

> “Sel grid 50 m di CRS canonical domain. Galat ukuran di bumi mengikuti metadata profil.”

Jika produk butuh ukuran fisik yang sangat ketat, satu proyeksi nasional mungkin tidak cukup. Kita mungkin perlu zona lokal atau konstruksi geodesik. Konsekuensinya, hierarki dan tetangga lintas zona menjadi lebih rumit.

### 5.2 Buat aturan batas negara yang siap dipakai

V2 sengaja tidak memasukkan batas negara ke identitas matematika. Ini keputusan yang baik untuk menjaga ID tetap stabil.

Tetapi pengguna biasa tidak seharusnya menulis aturan ini sendiri.

Library sebaiknya menyediakan policy bernama, misalnya:

- `CENTROID_COVERED`;
- `INTERSECTS_BOUNDARY`; dan
- `MIN_BOUNDARY_COVERAGE >= threshold`.

Policy yang dipakai harus terlihat di hasil atau metadata request.

Sel di luar negara tetap boleh valid secara matematika. Tetapi aplikasi bisa meminta hanya sel yang masuk batas operasional negara.

Bedakan juga:

- **Verifikasi batas:** memastikan file batas cocok dengan hash profil.
- **Filter batas:** menentukan apakah titik atau sel dianggap masuk negara.

V2 punya yang pertama secara opsional. Yang kedua masih diserahkan ke caller.

### 5.3 Satu negara belum tentu satu proyeksi yang praktis

Satu profil per negara memang sederhana. Namespace dan hierarki negara tetap utuh.

Tapi ini sulit untuk negara yang:

- sangat lebar dari barat ke timur, seperti Rusia atau AS;
- punya wilayah terpisah, seperti Alaska dan Hawaii;
- melewati antimeridian; atau
- punya komponen wilayah dengan kebutuhan galat yang berbeda.

Strategi V2 saat ini masih bisa dipakai sebagai identitas nasional. Tetapi root-nya bisa sangat besar dan banyak area kosong. Galat skalanya juga bisa terlalu besar.

Sebelum menambah banyak negara, setiap profil perlu melewati kriteria ini:

1. semua komponen batas masuk ke root setelah transformasi;
2. antimeridian ditangani secara jelas;
3. ada batas maksimum galat skala;
4. ada batas maksimum area kosong root;
5. kebijakan wilayah dan teritori jelas;
6. sampling batas dan interior memakai titik yang cukup rapat; dan
7. jelas apakah tetangga lintas komponen memang bermakna.

Jika satu CRS tidak memenuhi batas galat, ada dua pilihan yang jujur:

- tetap memakai satu CRS nasional dan menampilkan galat yang lebih besar; atau
- memakai subdomain regional yang punya versi jelas, dengan aturan khusus untuk hubungan lintas wilayah.

Jangan membuat beberapa root bergaya UTM lalu menganggap semuanya satu grid yang mulus.

### 5.4 Alias harus terpisah dari ID utama

Kombinasi tiga kata acak belum tentu mudah dipahami. Masalahnya juga bisa muncul dari bahasa, ejaan, perubahan nama tempat, collision, dan wilayah kosong.

Alias yang lebih baik harus punya struktur. Contohnya:

```text
<negara> / <wilayah> / <skala> / <arah utara-selatan> / <arah timur-barat>
```

Aturan alias yang disarankan:

- ID utama tetap `geosquare:v2:<domain>:<gid>`;
- alias punya versi sendiri;
- alias bisa di-resolve kembali ke ID utama;
- posisi dijelaskan dengan bagian yang bermakna, bukan kata acak;
- nama tempat hanya menjadi label, bukan identitas utama;
- ada fallback netral untuk daerah rural, laut, dan wilayah terpencil; dan
- skala ditampilkan jelas, misalnya 50 m atau 1 km.

Alias boleh memudahkan manusia. Tetapi alias bukan sumber kebenaran geometri.

## 6. Risiko dan masalah rilis V2

### P0 — private key exposure: addressed

The old private and public PEM files were deleted from the repository. A new Ed25519 key pair now exists outside the Git repository at the workspace root. The private key has mode `600`.

The database signature and `registry-trust.json` were regenerated with the new key ID `geosquare-registry-2026-09`.

The signing scripts now reject private-key paths inside the repository, and `*.pem` is ignored by Git. The private key must still stay outside the repository and must not be committed or distributed.

### P0 — registry path and package cleanup: addressed in source

The canonical SQLite path is:

```text
src/geosquare_v2/db/registry.db
src/geosquare_v2/db/registry.db.sig
```

Active documentation and `pyproject.toml` now use this path. Loader examples also use the correct constructor order.

A clean wheel/sdist install still needs to be tested. The active environment also rejects the signed registry when its local `proj.db` hash does not match the signed release resource.

### P1 — adapter migrasi V1 ke V2: implemented

`src/geosquare_v2/migration.py` now decodes V1 GIDs in isolation and supports point and area migration with provenance. Pytest validation is still blocked because pytest is not installed.

Module migrasi yang benar minimal harus mendukung:

- decode V1 dengan versi V1 yang jelas;
- memakai koordinat sumber jika tersedia;
- migrasi titik lewat representative point;
- migrasi area lewat geometri sel V1;
- pemilihan domain dan level target;
- hasil satu-ke-banyak untuk area;
- method dan threshold coverage;
- versi CRS dan profil sumber/target; dan
- provenance, ketidakpastian, dan metode migrasi.

Tidak ada konversi string langsung yang aman dari V1 ke V2. Root, proyeksi, level, dan alphabet-nya berbeda.

Bare ID V1 tidak boleh dianggap sebagai GID V2.

### P1 — verifikasi batas belum konsisten

`DbRegistryLoader` memakai default `verify_boundaries=False`.

Beberapa dokumen justru memberi kesan bahwa loader selalu memeriksa hash batas. Fixture analytics juga memberi `boundary_root` tanpa mengaktifkan verifikasi.

Mode database-only mungkin memang berguna. Tetapi dokumentasi harus membedakan dengan jelas:

- load database signed saja; dan
- load release lengkap dengan verifikasi file batas.

Untuk aplikasi negara, default yang lebih aman adalah verified release bundle atau constructor yang membuat mode tanpa verifikasi terlihat jelas.

### P1 — test negara nyata masih kurang

Test yang ada mencakup migrasi registry sintetis, signature tampering, geometri/polyfill, batch, dan source UDF.

Tetapi belum ada suite scalar lengkap untuk:

- semua karakter valid pada level 5x5 dan 2x2;
- GID malformed dan karakter 2x2 yang tidak valid;
- batas root dan batas antar-sel;
- parent-child di area carry;
- clipping untuk neighbour, ring, dan disk;
- semua kasus invalid packed ID;
- antimeridian dan multipolygon;
- pulau terpencil dan negara sangat lebar; dan
- filter batas negara yang benar-benar dijalankan.

Test analytics ID/VN memang memakai artefak kandidat nyata. Tetapi test itu tidak mengaktifkan verifikasi batas.

### P1 — sampling proyeksi belum cukup

`generate_release_candidates.py` mengambil sample dari vertex batas negara.

Sampling vertex saja bisa melewatkan:

- garis panjang di antara dua vertex;
- komponen kecil atau bentuk yang rumit;
- titik galat maksimum di bagian interior; dan
- masalah antimeridian.

Metadata sekarang tetap berguna. Tetapi sebaiknya diberi label sebagai hasil sampling vertex batas.

Tambahkan sampling batas yang lebih rapat dan titik interior.

### P2 — API utama masih terlalu rumit

Flow scalar sekarang meminta:

1. profil yang sudah diverifikasi;
2. object `GeosquareGrid`; dan
3. transformer buatan caller dengan `always_xy=True`.

Ini bagus untuk API level rendah. Tapi bukan API utama untuk pengguna biasa.

Tambahkan facade berbasis registry yang bisa:

1. menerima longitude, latitude, domain, level, dan versi profil;
2. memuat dan memverifikasi profil;
3. membuat transformer yang benar;
4. menerapkan epoch dan policy batas;
5. mengembalikan canonical fields, URI, GID, bounds, dan alias opsional; dan
6. menampilkan akurasi skala profil.

API level rendah tetap dipertahankan untuk pengguna ahli dan warehouse.

### P2 — aturan epoch belum sepenuhnya masuk API

Profile menyimpan reference epoch. Tetapi encoder publik belum menerima coordinate epoch dan belum membuat transformasi time-dependent.

Untuk sementara, caller harus lebih dulu menyamakan koordinat dengan epoch profil.

API harus menolak epoch yang tidak didukung dan mencatat asumsi epoch tersebut.

### P2 — level 1 m V1 tidak ada di V2

V1 punya level 15 / 1 m. V2 berhenti di 5 m.

Alasannya masuk akal: format signed Int64 sudah penuh.

Tetapi ini tetap perubahan kompatibilitas. Jika 1 m diperlukan, buat format atau versi ID baru. Jangan mengubah arti level lama secara diam-diam.

## 7. Arsitektur target

### Layer A: core V2

Pertahankan bagian ini:

- identitas `(domain, level, x_idx, y_idx)`;
- codec GID yang ketat;
- codec packed Int64;
- pembuatan kotak pada CRS grid;
- parent, child, neighbour, ring, disk, dan distance; serta
- polyfill dengan coverage mode yang jelas.

Jangan masukkan geometri V1 ke layer ini.

### Layer B: registry domain signed

Tambahkan field profil untuk:

- komponen batas dan policy inclusion;
- aturan antimeridian;
- batas penerimaan galat proyeksi;
- metode dan cakupan sampling galat;
- versi batas operasional;
- versi profil dan registry; dan
- apakah topology lintas komponen diperbolehkan.

Registry tetap immutable setelah ditandatangani.

### Layer C: facade berbasis policy

Sediakan operasi level tinggi seperti:

```text
index_point(domain, lon, lat, level, boundary_policy)
cell_geometry(uri, output_crs)
polyfill(domain, geometry, source_crs, level, boundary_policy, coverage_mode)
neighbourhood(uri, k, boundary_policy)
distance(uri_a, uri_b, mode)
```

Hasilnya sebaiknya memuat:

- versi domain dan profil;
- level;
- ukuran sel di CRS grid;
- galat skala;
- policy batas; dan
- asumsi epoch.

### Layer D: package migrasi

Migrasi V1 harus terpisah dan eksplisit.

Hasilnya jangan hanya string ID baru. Simpan juga record migrasi.

Satu sel V1 bisa menjadi banyak sel V2. Ini normal untuk data area. Simpan mapping, coverage, dan provenance-nya.

### Layer E: service alias

Alias harus versioned, bisa dilokalkan, dan bisa di-resolve ke canonical URI.

Alias tidak boleh dipakai untuk menghitung parent, jarak, atau geometri.

## 8. Rencana kerja prioritas

### Blocker rilis

1. Hapus dan rotate private key yang ter-track.
2. Pilih satu layout registry/package. Samakan code, package, script, dan dokumentasi.
3. Build dan load wheel/sdist di CI menggunakan environment bersih.
4. Putuskan apakah rilis wajib memverifikasi file batas. Buat mode ini eksplisit.

### Kebenaran core

5. Tambah test scalar untuk codec, root edge, hierarki, packing, topology, dan distance.
6. Tambah test ID/VN dengan verifikasi batas aktif.
7. Tambah fixture antimeridian, multipolygon, wilayah terpisah, dan negara lebar.
8. Ganti atau lengkapi sampling vertex dengan sampling batas dan interior yang lebih rapat.
9. Buat policy filter batas dan pakai implementasi yang sama untuk point indexing dan polyfill.

### Kompatibilitas dan kemudahan pakai

10. Buat package migrasi V1 dengan pilihan point/area, coverage, dan provenance.
11. Buat facade registry yang menyembunyikan setup transformer biasa.
12. Tambahkan parser dan validator untuk versioned URI.
13. Dokumentasikan jarak grid level sama, asumsi epoch, dan beda antara meter grid dengan ukuran fisik di bumi.
14. Rancang alias setelah vocabulary wilayah dan API canonical sudah stabil.

## 9. Kesimpulan akhir

### Apakah V2 arah yang benar?

**Ya.** V2 memperbaiki masalah utama V1. Grid sekarang berbasis profil negara dan CRS proyeksi. Hierarki dan compute-on-read tetap dipertahankan.

Identitas Cartesian V2 juga lebih kuat daripada hanya mengandalkan string GID.

### Apakah V2 sudah memenuhi semua kebutuhan?

**Belum.** V2 sudah memenuhi banyak kebutuhan teknis inti. Tetapi kebutuhan operasionalnya belum selesai:

- adapter migrasi sudah ada tetapi belum divalidasi penuh;
- belum ada API batas negara yang mudah;
- belum ada kebijakan yang terbukti untuk negara ekstrem;
- clean wheel/sdist belum diuji;
- environment aktif belum cocok dengan hash resource PROJ rilis; dan
- test negara nyata belum cukup.

Rekomendasi akhirnya:

> **Pakai core V2. Bekukan V1 sebagai decoder legacy. Lengkapi V2 dengan registry terverifikasi, facade policy, dan sistem migrasi sebelum menambah alias atau banyak negara baru.**

Dengan cara ini, ide terbaik V1 dan V2 tetap dipakai. Risiko geometri V1 dan masalah rilis V2 tidak ikut menjadi masalah permanen di data.

## Bukti yang diperiksa

- V1: `src/geosquare_grid/core.py`, `src/geosquare_grid/__init__.py`, `README.md`, `setup.cfg`, `tests/test_geosquare_grid.py`.
- Dokumen V2: `V2SPECS.md`, `ARCHITECTURE_DECISIONS.md`, `CRUCIAL_LOGIC.md`, `README.md`, `RELEASE_CANDIDATE.md`, `SQLITE_REGISTRY_GUIDE.md`.
- Implementasi V2: `src/geosquare_v2/codec.py`, `grid.py`, `packing.py`, `geometry.py`, `polyfill.py`, `batch.py`, `manifest.py`, `db.py`, `release.py`, dan `registry.py`.
- Artefak, script, dan test V2: profil negara, metadata skala, `scripts/generate_release_candidates.py`, `scripts/migrate_registry_to_db.py`, `scripts/sign_registry_db.py`, dan semua file dalam `tests/`.

Test yang ada tidak dijalankan di environment ini karena Python aktif tidak memiliki `pytest` (`No module named pytest`). Jadi laporan ini menggabungkan inspeksi kode dengan test yang dideklarasikan di repository. Laporan ini tidak menyatakan bahwa seluruh test saat ini lulus.
