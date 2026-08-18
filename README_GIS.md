# GIS / Map API - Tài liệu mô tả

Tài liệu này mô tả các API GIS mới, độc lập với API routing hiện có.

**Base URL:** `http://<host>:<port>/api/v1/map`

**Nguyên tắc chung:**
- Toàn bộ dữ liệu geometry (điểm/đoạn cáp) được lưu ở **PostgreSQL + PostGIS**, chiếu (projection) từ MongoDB, liên kết qua `source_id` (= `ma_diem` cho điểm, = `_id` cable cho đoạn).
- MongoDB vẫn là nguồn dữ liệu nghiệp vụ chính xác nhất (tên điểm, mã tuyến, trạng thái...). API GIS chỉ trả các field cần thiết cho việc hiển thị bản đồ.
- Toạ độ dùng hệ **WGS84 (SRID 4326)**: `lng` = kinh độ, `lat` = vĩ độ.
- Response bọc trong `{"success": true/false, "data": ...}` giống các API routing hiện tại.
- Lỗi trả về theo chuẩn HTTP: `400` (tham số sai), `404` (không tìm thấy), `409` (xung đột version), `500` (lỗi server).

---

## Mục lục

1. [GET /map/points](#1-get-mappoints) — Danh sách điểm theo viewport (BBox)
2. [GET /map/points/{point_id}](#2-get-mappointspoint_id) — Chi tiết 1 điểm
3. [GET /map/segments](#3-get-mapsegments) — Danh sách đoạn cáp theo viewport (BBox)
4. [GET /map/segments/{segment_id}](#4-get-mapsegmentssegment_id) — Chi tiết đoạn cáp (kèm danh sách SID)
5. [GET /map/segments/{segment_id}/geometry](#5-get-mapsegmentssegment_idgeometry) — Lấy riêng geometry
6. [PUT /map/segments/{segment_id}/geometry](#6-put-mapsegmentssegment_idgeometry) — Cập nhật geometry
7. [GET /map/routes](#7-get-maproutes) — Điểm + đoạn cáp của **riêng 1 tuyến** (không lẫn tuyến khác)
8. [GET /map/nearby](#8-get-mapnearby) — Tìm điểm/đoạn gần 1 vị trí
9. [GET /map/search](#9-get-mapsearch) — Tìm kiếm điểm **và/hoặc tuyến**
10. [GET /map/sid/{sid_value}](#10-get-mapsidsid_value) — Sơ đồ map theo 1 SID cụ thể
11. [POST /map/sync](#11-post-mapsync) — Đồng bộ dữ liệu Mongo → PostGIS

---

## 1. GET /map/points

Lấy danh sách điểm nằm trong viewport (BBox) hiện tại của bản đồ. Dùng khi người dùng pan/zoom Google Maps.

**Query params:**

| Param     | Kiểu  | Bắt buộc | Mô tả |
|-----------|-------|----------|-------|
| `min_lng` | float | ✅ | Kinh độ nhỏ nhất của viewport |
| `min_lat` | float | ✅ | Vĩ độ nhỏ nhất của viewport |
| `max_lng` | float | ✅ | Kinh độ lớn nhất của viewport |
| `max_lat` | float | ✅ | Vĩ độ lớn nhất của viewport |
| `zoom`    | int   | ❌ | Zoom level hiện tại (tham khảo) |
| `limit`   | int   | ❌ | Mặc định 2000, tối đa 20000 |

**Request mẫu:**

```
GET /api/v1/map/points?min_lng=105.78&min_lat=21.02&max_lng=105.80&max_lat=21.04&zoom=15&limit=500
```

**Response 200:**

```json
{
  "success": true,
  "data": [
    {
      "source_id": "2.124019-106007.MX004",
      "ma_diem": "2.124019-106007.MX004",
      "ten_diem": "Măng xông 4",
      "lat": 21.030731,
      "lng": 105.782411,
      "point_type": "MX",
      "ma_tuyen": "2.124019-106007",
      "parent_id": "f40a5c05b3224ad2a8d0beceb2b21054"
    }
  ]
}
```

**Response lỗi 400** (BBox không hợp lệ, vd min ≥ max):

```json
{ "detail": "BBox không hợp lệ (min phải nhỏ hơn max)." }
```

---

## 2. GET /map/points/{point_id}

Lấy chi tiết 1 điểm theo `point_id` = `ma_diem`.

**Request mẫu:**

```
GET /api/v1/map/points/2.124019-106007.MX004
```

**Response 200:**

```json
{
  "success": true,
  "data": {
    "source_id": "2.124019-106007.MX004",
    "ma_diem": "2.124019-106007.MX004",
    "ten_diem": "Măng xông 4",
    "lat": 21.030731,
    "lng": 105.782411,
    "point_type": "MX",
    "ma_tuyen": "2.124019-106007",
    "parent_id": "f40a5c05b3224ad2a8d0beceb2b21054"
  }
}
```

**Response lỗi 404** (điểm chưa được đồng bộ vào GIS layer, hoặc không tồn tại):

```json
{ "detail": "Không tìm thấy điểm '2.124019-106007.MX004' trong GIS layer." }
```

---

## 3. GET /map/segments

Lấy danh sách đoạn cáp (dạng LineString) nằm trong viewport để vẽ polyline lên bản đồ.

**Query params:** giống hệt `/map/points` (`min_lng`, `min_lat`, `max_lng`, `max_lat`, `zoom`, `limit`).

**Request mẫu:**

```
GET /api/v1/map/segments?min_lng=105.78&min_lat=21.02&max_lng=105.80&max_lat=21.04&limit=1000
```

**Response 200:**

```json
{
  "success": true,
  "data": [
    {
      "source_id": "6f2a1c...cable_id",
      "start_point_id": "2.124019-106007.MX004",
      "end_point_id": "2.124019-106007.MX005",
      "ma_tuyen": "2.124019-106007",
      "parent_id": "f40a5c05b3224ad2a8d0beceb2b21054",
      "geometry": {
        "type": "LineString",
        "coordinates": [
          [105.782411, 21.030731],
          [105.783500, 21.031100]
        ]
      },
      "geometry_source": "AUTO",
      "geometry_version": 1
    }
  ]
}
```

`geometry_source` là một trong: `AUTO` (đường thẳng tự sinh giữa 2 điểm), `USER` (người dùng đã tự chỉnh trên map), `IMPORTED`, `GOOGLE`.

---

## 4. GET /map/segments/{segment_id}

Chi tiết 1 đoạn cáp: segment + thông tin điểm đầu/cuối + geometry hiện tại + **danh sách SID đang đi qua đoạn này**. `segment_id` = `_id` của cable trong MongoDB.

`sid_list` được lấy trực tiếp từ MongoDB (cable_detail/sợi thuộc cable này → sid_cable active thuộc các sợi đó) — không cần đồng bộ sang PostGIS vì đây là business data, không phải geometry.

**Request mẫu:**

```
GET /api/v1/map/segments/6f2a1c...cable_id
```

**Response 200:**

```json
{
  "success": true,
  "data": {
    "segment": {
      "source_id": "6f2a1c...cable_id",
      "start_point_id": "2.124019-106007.MX004",
      "end_point_id": "2.124019-106007.MX005",
      "ma_tuyen": "2.124019-106007",
      "parent_id": "f40a5c05b3224ad2a8d0beceb2b21054",
      "geometry": {
        "type": "LineString",
        "coordinates": [[105.782411, 21.030731], [105.783500, 21.031100]]
      },
      "geometry_source": "AUTO",
      "geometry_version": 1
    },
    "start_point": {
      "source_id": "2.124019-106007.MX004",
      "ma_diem": "2.124019-106007.MX004",
      "ten_diem": "Măng xông 4",
      "lat": 21.030731,
      "lng": 105.782411,
      "point_type": "MX",
      "ma_tuyen": "2.124019-106007",
      "parent_id": "f40a5c05b3224ad2a8d0beceb2b21054"
    },
    "end_point": {
      "source_id": "2.124019-106007.MX005",
      "ma_diem": "2.124019-106007.MX005",
      "ten_diem": "Măng xông 5",
      "lat": 21.031100,
      "lng": 105.783500,
      "point_type": "MX",
      "ma_tuyen": "2.124019-106007",
      "parent_id": "f40a5c05b3224ad2a8d0beceb2b21054"
    },
    "sid_list": [
      {
        "sid_cable_id": "9a1b2c...",
        "sid": "AMS0924001",
        "ten_khach_hang": "Công ty ABC",
        "fiber_id": "d4e5f6...",
        "cable_number": 3,
        "ma_tuyen": "2.124019-106007"
      },
      {
        "sid_cable_id": "9a1b2d...",
        "sid": "AMS0924002",
        "ten_khach_hang": "Công ty XYZ",
        "fiber_id": "d4e5f7...",
        "cable_number": 5,
        "ma_tuyen": "2.124019-106007"
      }
    ],
    "sid_count": 2,
    "editable": true
  }
}
```

**Response lỗi 404:**

```json
{ "detail": "Không tìm thấy đoạn cáp '6f2a1c...cable_id' trong GIS layer." }
```

---

## 5. GET /map/segments/{segment_id}/geometry

Chỉ lấy phần geometry (nhẹ hơn, dùng khi mở editor chỉnh sửa polyline).

**Request mẫu:**

```
GET /api/v1/map/segments/6f2a1c...cable_id/geometry
```

**Response 200:**

```json
{
  "success": true,
  "data": {
    "source_id": "6f2a1c...cable_id",
    "geometry": {
      "type": "LineString",
      "coordinates": [[105.782411, 21.030731], [105.783500, 21.031100]]
    },
    "geometry_source": "AUTO",
    "geometry_version": 1
  }
}
```

---

## 6. PUT /map/segments/{segment_id}/geometry

Cập nhật geometry của 1 đoạn cáp — dùng khi người dùng kéo/chỉnh polyline trên Google Maps rồi lưu lại.

**Request body:**

```json
{
  "geometry": {
    "type": "LineString",
    "coordinates": [
      [105.782411, 21.030731],
      [105.783500, 21.031100],
      [105.785000, 21.032500],
      [105.790000, 21.035000]
    ]
  },
  "geometry_source": "USER",
  "expected_version": 1
}
```

**Giải thích field:**

| Field | Bắt buộc | Mô tả |
|-------|----------|-------|
| `geometry.type` | ✅ | Phải là `"LineString"` |
| `geometry.coordinates` | ✅ | Mảng `[lng, lat]`, tối thiểu 2 điểm |
| `geometry_source` | ❌ (mặc định `USER`) | `AUTO`/`USER`/`IMPORTED`/`GOOGLE` |
| `expected_version` | ❌ | Nếu truyền, backend sẽ so với `geometry_version` hiện tại trước khi ghi — dùng để tránh 2 người ghi đè chỉnh sửa của nhau (optimistic locking) |

**Validate backend thực hiện:**
- `type` đúng `LineString`, `coordinates` có ≥ 2 điểm (Pydantic validate).
- Mỗi toạ độ: `-180 ≤ lng ≤ 180`, `-90 ≤ lat ≤ 90`.
- Segment phải tồn tại trong GIS layer (đã được sync).
- Nếu `expected_version` không khớp version hiện tại → trả lỗi `409`.

**Response 200 (thành công — `geometry_version` tự tăng +1):**

```json
{
  "success": true,
  "data": {
    "source_id": "6f2a1c...cable_id",
    "start_point_id": "2.124019-106007.MX004",
    "end_point_id": "2.124019-106007.MX005",
    "ma_tuyen": "2.124019-106007",
    "parent_id": "f40a5c05b3224ad2a8d0beceb2b21054",
    "geometry": {
      "type": "LineString",
      "coordinates": [
        [105.782411, 21.030731],
        [105.783500, 21.031100],
        [105.785000, 21.032500],
        [105.790000, 21.035000]
      ]
    },
    "geometry_source": "USER",
    "geometry_version": 2
  }
}
```

**Response lỗi 400** (coordinate không hợp lệ, do Pydantic validate trước khi vào tới service):

```json
{
  "detail": [
    {
      "loc": ["body", "geometry", "coordinates"],
      "msg": "Value error, Longitude không hợp lệ: 250.5",
      "type": "value_error"
    }
  ]
}
```

**Response lỗi 404** (segment chưa tồn tại trong GIS layer):

```json
{ "detail": "Không tìm thấy đoạn cáp '6f2a1c...cable_id' trong GIS layer." }
```

**Response lỗi 409** (version không khớp — có người khác vừa sửa trước):

```json
{ "detail": "Version không khớp: hiện tại=2, client gửi expected_version=1." }
```
→ Xử lý ở frontend: gọi lại `GET /map/segments/{id}` để lấy version + geometry mới nhất, thông báo người dùng, rồi cho họ chỉnh lại trên dữ liệu mới.

---

## 7. GET /map/routes

Lấy **toàn bộ điểm + đoạn cáp của riêng 1 tuyến** — dùng khi người dùng chọn 1 tuyến (ví dụ từ kết quả `/map/search` loại `route`) và muốn xem/hiển thị **chỉ tuyến đó trên map, không lẫn các tuyến khác**. Không phân trang theo viewport (khác `/map/points`, `/map/segments`) — trả toàn bộ để zoom-to-fit.

**Query params:** truyền **một trong hai**:

| Param | Kiểu | Mô tả |
|-------|------|-------|
| `tuyen_id` | string | `_id` của tuyến (parent_id) |
| `ma_tuyen` | string | Mã tuyến |

**Request mẫu:**

```
GET /api/v1/map/routes?ma_tuyen=2.124019-106007
```
hoặc
```
GET /api/v1/map/routes?tuyen_id=f40a5c05b3224ad2a8d0beceb2b21054
```

**Response 200:**

```json
{
  "success": true,
  "data": {
    "tuyen_id": "f40a5c05b3224ad2a8d0beceb2b21054",
    "points": [
      {
        "source_id": "2.124019-106007.MX001",
        "ma_diem": "2.124019-106007.MX001",
        "ten_diem": "Măng xông 1",
        "lat": 21.030000,
        "lng": 105.782000,
        "point_type": "MX",
        "ma_tuyen": "2.124019-106007",
        "parent_id": "f40a5c05b3224ad2a8d0beceb2b21054"
      }
    ],
    "segments": [
      {
        "source_id": "6f2a1c...cable_id_1",
        "start_point_id": "2.124019-106007.MX001",
        "end_point_id": "2.124019-106007.MX002",
        "ma_tuyen": "2.124019-106007",
        "parent_id": "f40a5c05b3224ad2a8d0beceb2b21054",
        "geometry": { "type": "LineString", "coordinates": [["..."]] },
        "geometry_source": "AUTO",
        "geometry_version": 1
      },
      {
        "source_id": "6f2a1c...cable_id_2",
        "start_point_id": "2.124019-106007.MX002",
        "end_point_id": "2.124019-106007.MX003",
        "ma_tuyen": "2.124019-106007",
        "parent_id": "f40a5c05b3224ad2a8d0beceb2b21054",
        "geometry": { "type": "LineString", "coordinates": [["..."]] },
        "geometry_source": "USER",
        "geometry_version": 3
      }
    ]
  }
}
```

**Response lỗi 400** (thiếu cả `tuyen_id` và `ma_tuyen`):

```json
{ "detail": "Cần truyền tuyen_id hoặc ma_tuyen." }
```

**Response lỗi 404** (tuyến không tồn tại, hoặc tồn tại nhưng chưa có dữ liệu trong GIS layer — cần chạy `/map/sync`):

```json
{ "detail": "Tuyến 'f40a5c05...' chưa có dữ liệu trong GIS layer (có thể cần chạy /map/sync)." }
```

> **Endpoint cũ `GET /map/routes/{route_id}`** vẫn hoạt động (alias, tương đương `?tuyen_id={route_id}`, chỉ trả `segments`) nhưng đã **deprecated** — nên chuyển sang dùng `GET /map/routes` ở trên.

---

## 8. GET /map/nearby

Tìm các điểm/đoạn cáp gần 1 vị trí cho trước (bán kính tính bằng mét), dùng PostGIS spatial query (`ST_DWithin`).

**Query params:**

| Param     | Kiểu   | Bắt buộc | Mô tả |
|-----------|--------|----------|-------|
| `lat`     | float  | ✅ | Vĩ độ vị trí tìm |
| `lng`     | float  | ✅ | Kinh độ vị trí tìm |
| `radius`  | float  | ❌ | Mặc định 500m, tối đa cấu hình `GIS_NEARBY_MAX_RADIUS_M` (mặc định 20000m) |
| `include` | string | ❌ | `points`, `segments`, hoặc `points,segments` (mặc định cả 2) |
| `limit`   | int    | ❌ | Mặc định 50, tối đa 500 |

**Request mẫu:**

```
GET /api/v1/map/nearby?lat=21.030731&lng=105.782411&radius=300&include=points,segments&limit=20
```

**Response 200:**

```json
{
  "success": true,
  "data": {
    "points": [
      {
        "source_id": "2.124019-106007.MX004",
        "ma_diem": "2.124019-106007.MX004",
        "ten_diem": "Măng xông 4",
        "lat": 21.030731,
        "lng": 105.782411,
        "point_type": "MX",
        "ma_tuyen": "2.124019-106007",
        "parent_id": "f40a5c05b3224ad2a8d0beceb2b21054",
        "distance_m": 0.0
      }
    ],
    "segments": [
      {
        "source_id": "6f2a1c...cable_id",
        "start_point_id": "2.124019-106007.MX004",
        "end_point_id": "2.124019-106007.MX005",
        "ma_tuyen": "2.124019-106007",
        "distance_m": 12.4
      }
    ]
  }
}
```

**Response lỗi 400** (radius vượt giới hạn cho phép):

```json
{ "detail": "radius vượt quá giới hạn cho phép (20000m)." }
```

---

## 9. GET /map/search

Tìm kiếm **điểm** và/hoặc **tuyến** theo mã/tên. Tìm kiếm chạy trên MongoDB (nguồn business data chính xác nhất), toạ độ (cho điểm) được ghép thêm từ PostGIS.

**Query params:**

| Param   | Kiểu   | Bắt buộc | Mô tả |
|---------|--------|----------|-------|
| `q`     | string | ✅ | Từ khoá (không phân biệt hoa/thường) |
| `type`  | string | ❌ | `point`, `route`, hoặc `point,route` (mặc định cả 2) |
| `limit` | int    | ❌ | Mặc định 20, tối đa 100 (áp dụng riêng cho mỗi loại) |

**2 loại kết quả:**

- **`type: "point"`** — điểm khớp `ma_diem`/`ten_diem`/`ma_tuyen`, có sẵn `lat`/`lng` để nhảy/zoom tới ngay. Nếu khớp qua `ma_tuyen`, mỗi điểm cùng tuyến ra 1 kết quả riêng — **không phải cách đúng để xem cả tuyến** (dễ lẫn với tuyến khác đi ngang khu vực đó).
- **`type: "route"`** — tuyến khớp `ma_tuyen`/`ten_tuyen`, `source_id` = `tuyen_id` (parent_id) để gọi tiếp `GET /map/routes?tuyen_id=...`. **Đây là cách đúng để hiển thị riêng 1 tuyến, không lẫn tuyến khác.**

**Request mẫu (tìm cả điểm lẫn tuyến):**

```
GET /api/v1/map/search?q=2.124019-106007
```

**Response 200:**

```json
{
  "success": true,
  "data": [
    {
      "type": "point",
      "source_id": "2.124019-106007.MX004",
      "label": "Măng xông 4",
      "ma_tuyen": "2.124019-106007",
      "lat": 21.030731,
      "lng": 105.782411
    },
    {
      "type": "point",
      "source_id": "2.124019-106007.MX005",
      "label": "Măng xông 5",
      "ma_tuyen": "2.124019-106007",
      "lat": 21.031100,
      "lng": 105.783500
    },
    {
      "type": "route",
      "source_id": "f40a5c05b3224ad2a8d0beceb2b21054",
      "label": "Tuyến Long Xuyên - Cần Thơ",
      "ma_tuyen": "2.124019-106007",
      "lat": null,
      "lng": null
    }
  ]
}
```

**Request mẫu (chỉ tìm tuyến — dùng cho luồng "xem riêng 1 tuyến trên map"):**

```
GET /api/v1/map/search?q=2.124019-106007&type=route
```

Frontend flow đề xuất: người dùng gõ mã/tên tuyến → gọi `/map/search?type=route` → hiện danh sách tuyến khớp → người dùng chọn 1 tuyến → gọi `GET /map/routes?tuyen_id={source_id}` để lấy toàn bộ điểm + đoạn cáp **chỉ của tuyến đó**, ẩn hết các tuyến/điểm/đoạn khác đang hiển thị.

> Lưu ý: nếu điểm khớp từ khoá nhưng **chưa được đồng bộ sang GIS layer** (chưa chạy `/map/sync` hoặc điểm thiếu `vi_do`/`kinh_do` ở Mongo), `lat`/`lng` sẽ trả về `null` thay vì báo lỗi — frontend nên tự xử lý trường hợp này (ví dụ ẩn marker, hiện cảnh báo "chưa có toạ độ").

---

## 10. GET /map/sid/{sid_value}

Sơ đồ **map theo 1 SID cụ thể** — dùng khi người dùng chuyển chế độ xem map sang "theo SID": hiển thị các điểm + đoạn cáp thực tế mà SID đó đi qua, với geometry thật (không phải chỉ label như `/routing/diagram/sid`).

Luồng truy vết giống `GET /routing/diagram/sid`:
```
SID.value → sid_cable → cable_detail (sợi) → cable (đoạn) → tuyến → điểm
```

Khác biệt so với `/routing/diagram/sid`:
- **`nodes`** có sẵn `lat`/`lng` thật (ưu tiên từ PostGIS, fallback từ MongoDB nếu điểm chưa sync).
- **`edges`** được **gộp theo `cable_id`** (1 đoạn cáp = 1 polyline duy nhất) thay vì theo từng sợi — tránh vẽ chồng nhiều đường trùng nhau khi 1 đoạn có nhiều sợi/SID. Danh sách SID đi qua đoạn đó nằm trong `list_sid`.
- **`geometry`** là LineString GeoJSON thật lấy từ PostGIS (`geometry_source` cho biết đó là `AUTO`/`USER`/...). Nếu đoạn cáp **chưa được sync** sang PostGIS, hệ thống tự fallback vẽ đường thẳng tạm nối điểm đầu–cuối (đánh dấu `geometry_source: "AUTO"`) để map vẫn hiển thị được, không bị thiếu đoạn.

**Request mẫu:**

```
GET /api/v1/map/sid/AMS0924001
```

**Response 200 (tìm thấy):**

```json
{
  "success": true,
  "data": {
    "sid": "AMS0924001",
    "nodes": [
      {
        "id": "2.124019-106007.MX004",
        "label": "Măng xông 4",
        "lat": 21.030731,
        "lng": 105.782411,
        "point_type": "MX",
        "ma_tuyen": "2.124019-106007",
        "ten_tuyen": "Tuyến Long Xuyên - Cần Thơ"
      },
      {
        "id": "2.124019-106007.MX005",
        "label": "Măng xông 5",
        "lat": 21.031100,
        "lng": 105.783500,
        "point_type": "MX",
        "ma_tuyen": "2.124019-106007",
        "ten_tuyen": "Tuyến Long Xuyên - Cần Thơ"
      }
    ],
    "edges": [
      {
        "id": "6f2a1c...cable_id",
        "code": "MX004-MX005",
        "from": "2.124019-106007.MX004",
        "to": "2.124019-106007.MX005",
        "ma_tuyen": "2.124019-106007",
        "ten_tuyen": "Tuyến Long Xuyên - Cần Thơ",
        "geometry": {
          "type": "LineString",
          "coordinates": [[105.782411, 21.030731], [105.783500, 21.031100]]
        },
        "geometry_source": "AUTO",
        "list_sid": [
          {
            "sid_cable_id": "9a1b2c...",
            "sid": "AMS0924001",
            "ten_khach_hang": "Công ty ABC",
            "fiber_id": "d4e5f6...",
            "cable_number": 3
          }
        ]
      }
    ]
  }
}
```

**Response 200 (không tìm thấy SID — vẫn trả 200, không phải 404, giống hành vi của `/routing/diagram/sid`):**

```json
{
  "success": true,
  "data": {
    "sid": "AMS9999999",
    "nodes": [],
    "edges": [],
    "message": "Không tìm thấy SID."
  }
}
```

---

## 11. POST /map/sync

Đồng bộ (projection) toàn bộ điểm + đoạn cáp đang active từ MongoDB sang PostGIS. **Idempotent** — gọi lại nhiều lần an toàn (upsert theo `source_id`), **không sửa MongoDB**.

**Request:** không cần body.

```
POST /api/v1/map/sync
```

**Response 200:**

```json
{
  "success": true,
  "data": {
    "started_at": "2026-08-10T02:00:00.123456+00:00",
    "finished_at": "2026-08-10T02:00:04.987654+00:00",
    "duration_seconds": 4.86,
    "points": {
      "synced_points": 15234,
      "skipped_no_coordinate": 12,
      "skipped_ma_diem_sample": ["2.124019-106007.MX999", "..."]
    },
    "segments": {
      "synced_segments": 15108,
      "skipped_missing_coordinate": 3,
      "skipped_cable_id_sample": ["6f2a1c...", "..."]
    }
  }
}
```

- `skipped_no_coordinate` / `skipped_missing_coordinate`: số điểm/đoạn bị bỏ qua vì thiếu `vi_do`/`kinh_do` hợp lệ ở MongoDB — cần bổ sung toạ độ ở nguồn rồi chạy sync lại.
- Với dataset lớn (hàng trăm nghìn bản ghi), khuyến nghị chạy `python -m scripts.gis_initial_sync` (CLI) thay vì gọi qua HTTP để tránh timeout request.

---

## Tổng hợp mã lỗi

| HTTP code | Ý nghĩa | Ví dụ |
|-----------|---------|-------|
| 400 | Tham số/geometry không hợp lệ | BBox sai, coordinate ngoài khoảng, radius quá lớn |
| 404 | Không tìm thấy trong GIS layer | Điểm/đoạn/tuyến chưa được sync hoặc không tồn tại |
| 409 | Xung đột version khi update geometry | `expected_version` không khớp |
| 500 | Lỗi server / lỗi kết nối PostGIS | Postgres không kết nối được, lỗi SQL |