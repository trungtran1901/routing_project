# Routing API - Danh sách API

API Python (FastAPI + MongoDB) xử lý routing tự động khi thêm/xóa điểm, đồng bộ sợi và tính toán thống kê tuyến.

---

## Chạy server

```bash
uvicorn app.main:app --reload --port 8000
```

Swagger UI: http://localhost:8000/docs

---

**Các file chính:**
- **`app/main.py`**: FastAPI app và cấu hình lifespan ([app/main.py](app/main.py)).
- **`app/routers/routing.py`**: Tập hợp endpoint của module routing ([app/routers/routing.py](app/routers/routing.py)).
- **Models (request/response):** [app/models/point.py](app/models/point.py), [app/models/cable.py](app/models/cable.py), [app/models/cable_detail.py](app/models/cable_detail.py), [app/models/sid.py](app/models/sid.py), [app/models/tuyen.py](app/models/tuyen.py).

---

**Base URL:** `http://<host>:<port>/api/v1` (router đã include với `prefix="/api/v1"`).

**Endpoints:**

- **Health**: **GET** `/health`
  - **Mô tả:** Kiểm tra trạng thái server.
  - **Response mẫu:**
    ```json
    {"status": "ok"}
    ```

- **Thêm điểm**: **POST** `/api/v1/routing/points`
  - **Mô tả:** Thêm điểm mới vào tuyến (thêm cuối hoặc chèn giữa tùy `start_point`).
  - **Request (PointCreateRequest)**: bắt buộc `ma_diem`, `ten_diem`, `parent_id`, `ma_tuyen`. Một số trường chính:
    - `ma_diem` (str), `ten_diem` (str)
    - `parent_id` (str) — id tuyến
    - `ma_tuyen` (str)
    - `start_point` (object|null) — nếu null → thêm cuối; nếu object → chèn sau điểm này
  - **Request mẫu:**
    ```json
    {
      "ma_diem": "2.124019-106007.MX006",
      "ten_diem": "Măng xông 6",
      "parent_id": "f40a5c05b3224ad2a8d0beceb2b21054",
      "ma_tuyen": "2.124019-106007",
      "start_point": null
    }
    ```
  - **Response mẫu:**
    ```json
    {"success": true, "data": {"point_id": "<new_id>", "created": true}}
    ```

- **Xóa điểm (mềm)**: **POST** `/api/v1/routing/points/delete`
  - **Mô tả:** Soft-delete điểm và vô hiệu hóa/ghép lại đoạn cáp tương ứng.
  - **Request (PointDeleteRequest):** `ma_diem`, `ma_tuyen`, `parent_id` + thông tin người xóa (tuỳ chọn).
  - **Request mẫu:**
    ```json
    {"ma_diem": "2.124019-106007.MX005", "ma_tuyen": "2.124019-106007", "parent_id": "f40a5c05..."}
    ```
  - **Response mẫu:**
    ```json
    {"success": true, "data": {"deleted": true, "affected_cables": 2}}
    ```

- **Sơ đồ tuyến (nodes+edges)**: **GET** `/api/v1/routing/diagram`
  - **Mô tả:** Trả về dữ liệu để vẽ sơ đồ tuyến (nodes + edges). Truyền **một trong** `tuyen_id` hoặc `ma_tuyen`.
  - **Query params:** `tuyen_id` (str, optional), `ma_tuyen` (str, optional)
  - **Response mẫu:**
    ```json
    {"success": true, "data": {"nodes": [{"id":"AGG001","label":"Long Xuyên"}], "edges": [{"id":"C1-C2","from":"C1","to":"C2","label":"Măng xông 1 - 2"}]}}
    ```

- **Sơ đồ theo sợi (mỗi edge = cable_detail)**: **GET** `/api/v1/routing/diagram/fiber`
  - **Mô tả:** Mỗi edge tương ứng một sợi (`cable_detail`). Truyền `tuyen_id` hoặc `ma_tuyen`.
  - **Response mẫu:** tương tự `/diagram` nhưng `customData` chứa thông tin sợi (cable_detail).

- **Sơ đồ theo SID**: **GET** `/api/v1/routing/diagram/sid`
  - **Mô tả:** Truy vết một `sid` (vd `AMS0924001`) qua các sợi/đoạn/tuyến.
  - **Query params:** `sid` (str, required)
  - **Response mẫu:**
    ```json
    {"success": true, "data": {"nodes": [...], "edges": [...], "sid":"AMS0924001"}}
    ```

- **Đồng bộ cable_detail theo total_cable**: **POST** `/api/v1/routing/sync-cable`
  - **Mô tả:** Đồng bộ số lượng `cable_detail` theo `total_cable` của đoạn cáp.
  - **Request (CableSyncRequest):** trường chính: `_id` (id đoạn cáp), `parent_id`, `ma_tuyen`, `total_cable`.
  - **Request mẫu:**
    ```json
    {"_id":"<cable_id>", "parent_id":"<tuyen_id>", "ma_tuyen":"...", "total_cable": 48}
    ```
  - **Response mẫu:**
    ```json
    {"success": true, "data": {"created": 48, "deleted": 0, "available_cable": 48}}
    ```

- **Cập nhật trạng thái sợi theo SID**: **POST** `/api/v1/routing/cables/update-fiber-status`
  - **Mô tả:** Cập nhật `total_sid` và `status` cho `cable_detail` khi SID được gắn/huỷ.
  - **Request (SIDCableRequest):** `_id` (id sid_cable), `parent_id` (id cable_detail), optional `SID` ref.
  - **Request mẫu:**
    ```json
    {"_id":"<sid_cable_id>", "parent_id":"<cable_detail_id>", "SID": {"value":"AMS0924001"}}
    ```
  - **Response mẫu:**
    ```json
    {"success": true, "data": {"updated_cable_detail": "<id>", "total_sid": 1}}
    ```

- **Cập nhật thống kê trạng thái đoạn cáp**: **POST** `/api/v1/routing/cables/update-status`
  - **Mô tả:** Tính `error_cable`, `used_cable`, `so_luong_sid`, `total_sid_raw` cho đoạn cáp.
  - **Request (CableDetailStatusRequest):** `_id` (id cable_detail) hoặc `parent_id` (id cable)
  - **Response mẫu:**
    ```json
    {"success": true, "data": {"error_cable": 2, "used_cable": 10, "so_luong_sid": 12}}
    ```

- **Tính & cập nhật thống kê tuyến**: **POST** `/api/v1/routing/tuyen/update-stats`
  - **Mô tả:** Dựa trên một đoạn cáp (dùng `parent_id`) để tính và cập nhật các trường thống kê trên tuyến chính.
  - **Request (TuyenStatsRequest):** `_id`, `parent_id`, `ma_tuyen` (tham khảo model).
  - **Response mẫu:**
    ```json
    {"success": true, "data": {"so_luong_link_mang_kh": 120, "chieu_dai_km": 42.5}}
    ```

---

## Gợi ý
- Xem router: [app/routers/routing.py](app/routers/routing.py) để biết chi tiết mô tả cho từng endpoint.
- Xem các Pydantic model để biết cấu trúc payload chi tiết: [app/models/point.py](app/models/point.py), [app/models/cable.py](app/models/cable.py), [app/models/cable_detail.py](app/models/cable_detail.py), [app/models/sid.py](app/models/sid.py), [app/models/tuyen.py](app/models/tuyen.py).

---

**File Descriptions (developer guide)**

- **`app/main.py`** ([app/main.py](app/main.py))
  - Tạo và cấu hình FastAPI app, đăng ký CORS và `router` với prefix `/api/v1`.
  - Lifespan: kết nối/đóng kết nối tới MongoDB (sử dụng `app.core.database`).

- **`app/core/config.py`** ([app/core/config.py](app/core/config.py))
  - Đọc cấu hình ứng dụng từ `.env` thông qua Pydantic `Settings`.
  - Chứa `MONGODB_URI`, `DATABASE_NAME`, CORS, và các cấu hình liên quan.

- **`app/core/database.py`** ([app/core/database.py](app/core/database.py))
  - Quản lý kết nối MongoDB (`connect_to_mongo`, `close_mongo_connection`).
  - Export `get_database()` để dùng trong `Depends` của router.
  - Định nghĩa tên các collection dùng trong project: `COLLECTION_POINTS`, `COLLECTION_CABLES`, `COLLECTION_CABLE_DETAIL`, `COLLECTION_SID_CABLE`.

- **`app/routers/routing.py`** ([app/routers/routing.py](app/routers/routing.py))
  - Định nghĩa tất cả endpoint liên quan đến routing, sync và thống kê:
    - `POST /routing/points` — thêm điểm (thêm cuối / chèn giữa)
    - `POST /routing/points/delete` — xóa mềm điểm và xử lý đoạn cáp
    - `GET /routing/diagram`, `GET /routing/diagram/fiber`, `GET /routing/diagram/sid` — trả dữ liệu sơ đồ
    - `POST /routing/sync-cable` — đồng bộ `cable_detail`
    - `POST /routing/cables/update-fiber-status` — cập nhật sợi theo SID
    - `POST /routing/cables/update-status` — cập nhật thống kê đoạn cáp
    - `POST /routing/tuyen/update-stats` — cập nhật thống kê tuyến
  - Các endpoint chuyển tiếp logic chính tới các service trong `app/services/`.

- **`app/models/`** (Pydantic models)
  - `point.py`: `PointCreateRequest`, `PointDeleteRequest`, và cấu trúc `Point`/`Station`/`StartPointRef`.
  - `cable.py`: `CableSyncRequest` (payload để đồng bộ `cable_detail`).
  - `cable_detail.py`: `CableDetailStatusRequest` (cập nhật trạng thái sợi).
  - `sid.py`: `SIDCableRequest` (payload SID → cable_detail).
  - `tuyen.py`: `TuyenStatsRequest` (dữ liệu dùng để tính thống kê tuyến).

- **`app/services/`**
  - `routing_service.py`: Core business logic tạo/vô hiệu hóa/ghép đoạn cáp khi thêm/xóa/chèn điểm. Hàm chính:
    - `process_add_point` (gọi `handle_add_point_to_end` hoặc `handle_insert_point_between` tùy payload)
    - `handle_delete_point` (xử lý xóa điểm và nối lại A→C)
  - `cable_detail_service.py`: Đồng bộ `cable_detail` theo `total_cable`, tạo/soft-delete sợi và cascade SID.
  - `sid_service.py`: Cập nhật `total_sid` và trạng thái sợi khi SID được gắn vào sợi.
  - `cable_status_service.py`: Tính `error_cable`, `used_cable`, `available_cable`, `so_luong_sid` và cập nhật lên đoạn cáp.
  - `tuyen_stats_service.py`: (nếu có) Tính và cập nhật các trường thống kê trên tuyến chính dựa trên tất cả đoạn cáp.

- **Các collection MongoDB** (tên ở [app/core/database.py](app/core/database.py))
  - `instance_data_hatang_quanlytuyen_newversion_detail`: Điểm trên tuyến (point).
  - `instance_data_hatang_quan_ly_cable`: Đoạn cáp (cable).
  - `instance_data_hatang_quan_ly_cable_detail`: Sợi chi tiết (cable_detail).
  - `instance_data_hatang_danhsach_sid_cable`: Danh sách SID gắn vào sợi.

---

Nếu bạn muốn, tôi có thể:
- Thêm response schema chi tiết (từ service trả về) cho từng endpoint.
- Sinh file Postman/Insomnia export hoặc một OpenAPI snippet tuỳ chỉnh.
