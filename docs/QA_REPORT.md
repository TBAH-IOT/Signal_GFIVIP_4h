# Kiểm thử Signal_GFIVIP_4h v1.3.0 — 22/11/2026

Profile mới từ **01/05/2026 00:00UTC**. Snapshot số liệu ghi rõ trong KET_QUA_DEN_BAN_GIAO.md; web tiếp tục cập nhật đến hiện tại.

| Hạng mục | Kết quả |
| --- | --- |
| Unit/integration |27tests pass:23tests profile/regression và4tests mới cho archive, navigation, OHLC/marker/net labels, mốc thoát dự kiến/current OHLC |
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

Snapshot241lệnh cũ giữ nguyên trong data/baseline/reference180 để audit; không còn là benchmark của profile sản phẩm hiện tại. ZIP/tag v1.1.0 không bị sửa. Gói v1.3 dùng cùng mốc01/05 của v1.2 và giữ nguyên logic factor/vốn/phí.

Chưa chạy Docker hoặc tích hợp auth/gateway/reverse proxy MVP thật trong môi trường này. Chưa quan sát một signal live mới từ entry tới exit4h trọn vẹn; vòng đời đã được kiểm tra bằng replay/restart/giá thật. Forecast là conditional historical mean, không bảo đảm giá tương lai; hệ thống không đặt lệnh trên sàn.

## Kiểm tra giao diện v1.3

Đã dùng Cua trên backend local thật: ban đầu chỉ5thẻ ngang và không tự chọn lệnh; click thẻ từ tab hiệu suất và click chuông đều mở đúng ID trong Chi tiết lệnh; previous/next đi tới AAVE15/16 rồi quay16/16, gồm lệnh ngoài latest5; entry/exit khớp OHLC thực; kết quả sau phí có nền xanh/đỏ. Tab hiệu suất tổng/từng coin và timeline01/05 vẫn khớp API. Giao diện nhỏ được kiểm tra tại viewport thực tế434px,37nến và không tràn ngang. Mã JS được node --check, script smoke_ui.py được cập nhật cho flow mới.

Nhánh lệnh mở được kiểm tra qua một service QA riêng dùng prefix entry lịch sử thật (ENA06/05/2026), không thêm lệnh giả vào sản phẩm: đúng4h, một biểu tượng nến mờ, không có OHLC ở thời điểm tương lai. Service fixture đã dừng sau kiểm tra. Xem evidence/trade_explorer_v1_3 và pytest_results_v1_3.xml. Không diễn giải ảnh replay thành tín hiệu live hiện tại; chưa quan sát một lệnh live mới trọn4h trong phiên này.
