# Kiểm thử Signal_GFIVIP_4h v1.2.0 — 22/11/2026

Profile mới từ **01/05/2026 00:00UTC**. Snapshot số liệu ghi rõ trong KET_QUA_DEN_BAN_GIAO.md; web tiếp tục cập nhật đến hiện tại.

| Hạng mục | Kết quả |
| --- | --- |
| Unit/integration |23tests pass:20regression hiện có và3tests May1/warmup, API mới, migration/backup/restart |
| Kết quả độc lập |301lệnh đóng,195thắng gross, WR64,78%, Net_P+8,87%, MaxDD−4,53% tại snapshot |
| Nguồn |20coin Binance USD-M15m price + premium-index, SHA-256 từng dataset |
| Warmup |689nến trước01/05, không có lệnh/marks/PnL/forecast cohort trước mốc |
| Equity |Factor gốc/scheduler độc lập khớp trade times/PnL; cash+inventory khớp toàn bộ marks, sai số tối đa dưới1e-7USDT |
| Migration |Backup state cũ, dựng lại book/forecast/thống kê, bỏ giao dịch trước01/05, không phát lại alert lịch sử |
| Restart |Cùng profile không reset/đếm trùng; giữ forecast frozen; cache tải bù hole/partial candle |
| Live local |Backend v1.2 đã chạy và đồng bộ thật20coin; ready/current tại lúc kiểm tra |
| UI |Tổng thể/coin,5thẻ/5notification, WR trước phí, NetPnL sau10bps, Sharpe không ghi số ngày, timeline từ01/05 |
| CLI |replay mặc định May1; --legacy-reference tái hiện241lệnh gốc riêng |

Đã kiểm tra API v1.2 thật và sổ lệnh đã dựng từ01/05 trên local; báo cáo độc lập ở evidence/continuous/independent_verification.json. Số liệu tổng không lấy trung bình coin, không dùng số minh họa trong ảnh. State/log/config chạy thử local nằm ngoài repository.

Các tests dùng dữ liệu thật; một số lifecycle tests dịch timestamp/dãy toán học chỉ để kiểm tra bất biến, không đưa fixture đó vào số liệu sản phẩm. TestClient/httpx và pandas float_precision có cảnh báo deprecation, không có lỗi kiểm thử.

Snapshot241lệnh cũ giữ nguyên trong data/baseline/reference180 để audit; không còn là benchmark của profile sản phẩm hiện tại. ZIP/tag v1.1.0 không bị sửa. Gói v1.2 có mốc mới và giữ nguyên logic factor/vốn/phí.

Chưa chạy Docker hoặc tích hợp auth/gateway/reverse proxy MVP thật trong môi trường này. Chưa quan sát một signal live mới từ entry tới exit4h trọn vẹn; vòng đời đã được kiểm tra bằng replay/restart/giá thật. Forecast là conditional historical mean, không bảo đảm giá tương lai; hệ thống không đặt lệnh trên sàn.
