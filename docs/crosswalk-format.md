# Format Crosswalk 1.0

## Tujuan

Crosswalk menghubungkan unit sumber dengan sel GeoSquare. Contoh unit sumber adalah desa. Nilai dari satu desa bisa dibagi ke beberapa sel dengan `bobot`.

Format ini juga dipakai untuk memetakan GID V1 ke GID V2. GID V1 masuk sebagai `sumber_id`. GID V2 masuk sebagai `gid`.

## Tabel

Tabel punya tiga kolom berikut.

| Kolom | Tipe | Aturan |
| --- | --- | --- |
| `sumber_id` | teks | ID unit sumber. Tidak boleh kosong. |
| `gid` | teks | GID V2 yang valid. Levelnya harus sama dengan level di manifest. |
| `bobot` | angka | Harus finite dan lebih besar dari 0. Ini adalah bagian nilai sumber yang masuk ke sel itu. |

Semua bobot untuk satu `sumber_id` harus berjumlah 1, dengan toleransi `1e-9`. `sumber_id` tanpa baris ditolak. Karena itu, setiap unit sumber yang dipakai harus punya setidaknya satu baris.

Pasangan `(sumber_id, gid)` tidak boleh muncul dua kali. Setiap `gid` harus valid dan harus memakai level dari manifest.

## Manifest JSON

Simpan manifest JSON di sebelah file tabel. Isinya:

```json
{
  "format_version": "1.0",
  "spec_version": "2.0",
  "domain_code": "ID",
  "level": 2,
  "weight_kind": "luas",
  "source_description": "Batas desa tahun 2025",
  "created_at": "2026-11-19T10:00:00Z",
  "registry_version": "2.0.0"
}
```

`level` adalah angka 0 sampai 14. `weight_kind` harus salah satu dari `luas`, `bangunan`, `populasi`, atau `lainnya`.

`weight_kind` menjelaskan apa yang dihitung oleh bobot. Pada format 1.0, mulai dengan `luas`. Artinya, bobot memakai bagian luas sumber yang masuk ke setiap sel.

`created_at` memakai format ISO 8601. `registry_version` menunjuk versi registry yang dipakai saat membuat tabel.

## Contoh

### Desa dibagi ke tiga sel

```text
sumber_id,gid,bobot
DESA-001,2F,0.50
DESA-001,2G,0.30
DESA-001,2H,0.20
```

Bobot desa `DESA-001` berjumlah 1.

### Pemetaan GID V1 ke GID V2

```text
sumber_id,gid,bobot
v1:abc123,2F,1.0
```

GID V1 `v1:abc123` dipakai sebagai ID sumber. `2F` harus GID V2 yang valid pada level manifest.
