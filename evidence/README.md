# Bằng chứng bàn giao

Các bằng chứng hiện hành cho **v1.2.0, profile bắt đầu01/05/2026**:

- `continuous/`: số liệu snapshot, từng coin, ledger và đối chiếu factor/scheduler/equity độc lập.
- `pytest_results_v1_2.xml`:23tests pass, gồm regression cũ và May1/warmup/migration/restart/API.
- `live_profile_v1_2.json`: health/API của backend v1.2 gọi dữ liệu Binance thật sau nâng cấp.
- `ui_may1.json`, `ui_may1_local.jpg`, `ui_may1_mobile_coin.jpg`: kiểm tra tab local thật, mốc trục01/05, tổng thể/từng coin, không tràn/chồng nhãn trên màn hình nhỏ.

Các file khác như `pytest_results_v1_1.xml`, `ui_smoke.json`, ảnh `ui_desktop*`, `live_worker_smoke.json` và `standalone_release_check.json` là bằng chứng bàn giao trước v1.2, giữ để đối chiếu; không dùng số liệu trong đó làm kết quả hiện tại. Mẫu241lệnh gốc ở `data/baseline`/`data/reference180` cũng chỉ là audit riêng.

Kiểm tra giải nén gói v1.2 được xuất cạnh ZIP thành file `.verification.json`, không ghi đè các bằng chứng cũ hoặc làm thay đổi manifest của gói đang kiểm tra. State, cookie key, log chạy thử và backup SQLite không nằm trong gói.
