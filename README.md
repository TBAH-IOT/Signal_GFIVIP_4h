# Signal_GFIVIP_4h — MVP v1.3.0

Profile được chốt: **20 coin, backtest/vốn/lệnh/forecast/thống kê từ 01/05/2026 00:00 UTC đến hiện tại**. Timeline bắt đầu đúng 01/05/2026; không còn khoảng trục từ tháng 1. Đây là đổi mốc tính thật trong engine, không chỉ đổi nhãn đồ thị.

**Mới ở v1.3:** trang ban đầu chỉ có dải5thẻ nhỏ nằm ngang. Click thẻ/chuông mở đúng lệnh, biểu đồ nến thật với entry/exit, mũi tên duyệt toàn bộ lịch sử cùng coin và hai tab Chi tiết lệnh / Hiệu suất mô hình. PnL lệnh đóng có nền xanh/đỏ nhẹ; TP/SL là nhãn kết quả sau phí tại điểm đóng4h. Lệnh mở có mốc giờ thoát và nến mờ tượng trưng thời gian, không tạo giá tương lai. Xem [TRADE_EXPLORER.md](docs/TRADE_EXPLORER.md).

Backend tự tải bù nến Binance còn thiếu và dựng lại sổ từ mốc cố định này khi deploy/restart, sau đó theo dõi các nến 15m mới. Chỉ cần Python backend hoạt động và có Internet; không cần CoinGlass/API key Binance. Frontend tĩnh một mình không chạy được model.

## Cấu hình

| Thuộc tính | Giá trị |
| --- | --- |
| Tên | Signal_GFIVIP_4h |
| Logic | LONG: MOM16:L + BASIS:L, rolling672/min168, đuôi thấp1%, onset |
| Giá / BASIS | Binance USD-M 15m price / close premium-index15m |
| Coin cố định | BTC, ETH, SOL, ZEC, BNB, XRP, NEAR, DOGE, UNI, SUI, ENA, LINK, AVAX, ADA, BCH, FIL, LTC, DOT, ARB, AAVE |
| Mốc vốn và lệnh | 01/05/2026 00:00 UTC; không carry vị thế trước mốc |
| Warmup | 689 nến trước mốc, từ23/04/2026 19:45 UTC; chỉ tính factor |
| Vốn | Chung10.000 USDT; cố định500 USDT/lệnh, không vay |
| Non-overlap | Chặn trong cùng coin; các coin khác được mở đồng thời |
| Vào / thoát | Open sau nến tín hiệu / open đúng4h sau entry |
| Phí và slippage | **10 bps =0,1% tổng cả hai đầu** |
| SL/TP/DCA | Không có |

Warmup không nằm trong số lệnh, PnL, DD, Sharpe hoặc cohort forecast. Mọi quyết định dùng nến đã đóng; nến hiện tại chỉ cung cấp open. TP/SL trên giao diện không thêm ngưỡng giá đóng sớm. Chỉ lệnh đã kết thúc4h vào winrate/PnL; lệnh chưa đủ hạn vẫn giữ trong book.

## Chạy trên Windows

Python3.13, pip>=22.3. Trong thư mục giải nén:

```powershell
.\install.ps1
.\start_live.ps1
```

Mở http://127.0.0.1:8765. `serve` mặc định live; giao diện hiện mốc dữ liệu thực và trạng thái đồng bộ. `start_offline.ps1` chỉ xem snapshot, không tải dữ liệu mới.

```powershell
# Cấu hình hiện tại từ01/05; kiểm tra snapshot không gọi mạng
.\.venv\Scripts\python.exe -m mom_basis replay

# Tải bù đến Binance hiện tại rồi thoát
.\.venv\Scripts\python.exe -m mom_basis sync

# Chỉ audit mẫu cũ241lệnh từ25/04, không dùng cho số liệu sản phẩm
.\.venv\Scripts\python.exe -m mom_basis replay --legacy-reference

.\.venv\Scripts\python.exe -m pytest -q --basetemp .test_tmp
```

Linux: cài requirements.lock vào venv và chạy `python -m mom_basis serve --host 0.0.0.0 --port 8765`. Có Dockerfile/compose; đã kiểm thử Windows, chưa chạy Docker. Một worker/SQLite state, lưu volume bền vững; tích hợp gateway HTTPS/auth của MVP.

## Giao diện và API

- Chỉ5 thẻ/notification mới nhất toàn20coin nằm trên một dải ngang. Chưa chọn thẻ thì vùng chi tiết/hiệu suất được ẩn. Ledger/price cache đầy đủ vẫn lưu; mũi tên trong chi tiết đi qua toàn bộ lịch sử của coin đang xem.
- Thẻ có entry/exit/current price, trạng thái Đang mở/Đã kết thúc, đường forecast mean/p10–p90 frozen và đường giá thực.
- Click thẻ/chuông luôn mở **Chi tiết lệnh** của đúng ID vừa chọn. Cạnh đó có tab **Hiệu suất mô hình**, bộ chọn **Tổng thể** / **Coin đang xem · [tên coin]**. Không chọn số lượng coin.
- Hiển thị winrate trước phí, Net PnL sau phí, Max DD, Sharpe, equity. Bỏ ô winrate sau phí và số ngày quan sát dưới Sharpe; API vẫn giữ các trường tương ứng để đối chiếu.
- Timeline và caption từ01/05, tự cập nhật đến mốc nến mới. Trục có vạch tháng/lưới nét đứt và nhãn giãn theo chiều rộng.
- Backfill cập nhật thống kê/thẻ nhưng không gửi alert cũ. Chỉ tín hiệu mới phát hiện kịp boundary hiện tại mới có LIVE/unread.

Forecast là trung bình lịch sử của lệnh đã hoàn tất trong profile trước lúc phát tín hiệu, không bảo đảm giá tương lai. Hệ thống theo dõi mô phỏng, không đặt lệnh lên sàn.

## Nâng cấp từ bản cũ

Giữ state directory cũ và chạy v1.3: engine nhận diện `profile_id` thay đổi, nạp thêm warmup, tạo SQLite backup `before_profile_*.sqlite3`, rồi thay sổ lệnh/marks/forecast/thống kê theo mốc01/05 trong một transaction. Không trộn PnL hoặc dự báo từ profile25/04. Rebuild lịch sử không phát chuông hàng loạt; restart sau đó không reset/đếm trùng.

Nâng từv1.2 với cùng profile01/05 không reset ledger/forecast; v1.3 bổ sung UI và API archive, không đổi chiến thuật.

Model ID/spec_hash tiếp tục nhận diện quy tắc toán học không đổi; `profile_id` nhận diện riêng ngày bắt đầu và warmup. Dev cần đối chiếu cả hai. Snapshot241lệnh gốc trong data/baseline và data/reference180 được giữ làm audit; không phải số liệu hiện tại. ZIP/tag v1.1.0 giữ nguyên bản cũ; dùng source main hoặc gói v1.3.0 cho giao diện mới và profile01/05.

## Kết quả và tài liệu

Xem [kết quả đóng gói](docs/KET_QUA_DEN_BAN_GIAO.md): tổng danh mục, từng coin,5lệnh cuối và timestamp. Dữ liệu thật20coin kèm SHA-256 ở data/continuous; bằng chứng ở evidence/continuous. Sau triển khai, số liệu web tiếp tục tự cập nhật, không bị khóa theo file báo cáo.

- [MODEL_SPEC.md](docs/MODEL_SPEC.md): công thức, đơn vị, vốn, forecast.
- [DEV_HANDOFF.md](docs/DEV_HANDOFF.md): API/SSE, migration, auth/deploy.
- [CLAUDE_HANDOFF_PROMPT.md](docs/CLAUDE_HANDOFF_PROMPT.md): prompt tích hợp.
- [QA_REPORT.md](docs/QA_REPORT.md): kiểm thử và giới hạn đã xác minh.
- docs/openapi.json và docs/api_examples.json: schema/payload thật.
