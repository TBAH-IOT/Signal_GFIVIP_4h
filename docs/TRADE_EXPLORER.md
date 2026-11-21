# Dải thẻ và chi tiết lệnh — v1.3.0

## Luồng hiển thị

Trang ban đầu chỉ có dải5thẻ nằm ngang, có nút cuộn trái/phải; chưa chọn thẻ thì toàn bộ vùng chi tiết/hiệu suất được ẩn. Thẻ hiển thị entry, current/exit, dự báo TB lịch sử và **PnL sau phí của lệnh đã quyết toán**. Ô PnL dương có nền xanh nhẹ; âm có nền đỏ nhẹ. Lệnh đang mở chưa được gán kết quả.

Click thẻ hoặc chuông luôn mở **tab Chi tiết lệnh của đúng ID vừa bấm**, kể cả trước đó đang xem Hiệu suất. Không thay bằng lệnh mới nhất của cùng coin. Cạnh tab có tên coin đang xem. Các request tự refresh không được ghi đè lựa chọn đang tải của người dùng.

Hai tab: **Chi tiết lệnh** / **Hiệu suất mô hình**. Tab hiệu suất giữ bộ chọn **Tổng thể** hoặc **Coin đang xem**; winrate trước phí, Net_P sau phí, DD, Sharpe, equity từ01/05/2026 như v1.2. Bản cập nhật này không thay ngưỡng/vốn/phí/holding/portfolio hay kết quả backtest.

## PnL và nhãn kết quả

```text
PnL_%_thẻ = net_pnl_USDT / order_budget_USDT × 100
order_budget = 500 USDT
TP   nếu net_pnl > 0
SL   nếu net_pnl < 0
Hòa vốn nếu net_pnl = 0
```

TP/SL **là nhãn kết quả sau phí tại điểm đóng theo thời gian**, không phải lệnh bracket hoặc ngưỡng giá TP/SL được chạm trong4h. `exit_reason=TIME_4H`; stop_loss/take_profit vẫn null. Entry01:00UTC thì giờ thoát05:00UTC. Không thêm đóng sớm, không thay fill bằng high/low candle để gọi là TP hoặc SL.

Lệnh đang mở có đường dọc nét đứt, nhãn giờ thoát và **biểu tượng nến mờ ở vùng chú thích phía trên đồ thị giá**. Biểu tượng chỉ đánh dấu thời gian; không gán OHLC/giá tương lai. Khi có exit open thật, chuyển sang dấu giá thoát và TP/SL/Hòa vốn tương ứng.

## API

| Endpoint | Nội dung |
| --- | --- |
| GET /api/notifications | Vẫn tối đa5notification mới nhất |
| GET /api/trades?coin=AAVE&limit=50&offset=0 | Lịch sử coin, phân trang newest-first; total/items/offset/limit |
| GET /api/trades/{id} | Bất kỳ lệnh nào trong ledger, không giới hạn latest5 |
| GET /api/signals/{id} | Giữ API cũ chỉ cho latest5 để tương thích |

`/api/trades/{id}` trả về `trade`, `navigation`, `chart`, `server_time_ms`.

- `trade`: dữ liệu đã lưu, forecast frozen, quote/stale/status, `return_on_budget`, `result_tag`, `exit_reason`, `exit_label`.
- `navigation`: `coin`, `position` (1=oldest), `total`, `previous_id` (cũ hơn), `next_id` (mới hơn). Hai mũi tên đi qua toàn bộ ledger của đúng coin, không chỉ5notification. Boundary trả null và khóa nút; nút Mới nhất lấy trang đầu limit1.
- `chart`: `interval_ms=900000`, `start_ms/end_ms`, `candles[]` chứa time_ms/open/high/low/close/closed; entry_marker và exit_marker.
- `exit_marker.kind`: REALIZED khi đã có exit_price thật; SCHEDULED khi chưa có. `price=null` cho mốc dự kiến.

Chart lấy OHLC thật từ history_bars:32nến trước entry,16nến giữ lệnh và tối đa8nến sau exit. Trên màn hình nhỏ, frontend thu gọn phần context để nến dễ đọc. Không dựng OHLC từ đường mean forecast hoặc nội suy các điểm open. Nếu thiếu nến, trả chất lượng thiếu dữ liệu và chờ đồng bộ.

Worker cập nhật current OHLC khoảng5s cho các coin có lệnh mở, từ public price klines; chỉ cập nhật hàng `is_closed=0`. Closed factor bars giữ nguyên. SSE quotes làm frontend tải lại chi tiết lệnh mở; không thay forecast đã frozen. Dự báo mean có checkbox và nét đứt màu riêng, không trộn vào nến thật.

Đọc lịch sử không đánh dấu notification cũ đã đọc. Click latest5 mới gọi read endpoint; nếu notification vừa bị đẩy khỏi latest5 thì bỏ qua404, vẫn xem được lệnh qua archive. Chỉ readstate theo user được đổi, không đặt lệnh sàn.

## Kiểm thử

27pytest tests gồm các regression cũ và4cases mới: phân trang/lịch sử ngoài latest5, đi hết chuỗi previous/next cùng coin, OHLC/marker khớp fills/nhãn net sau phí, mốc thoát dự kiến/cập nhật current candle không sửa closed bars. UI được kiểm tra qua Cua trên backend local thật; nhánh đang mở dùng replay entry lịch sử riêng, không chèn lệnh giả vào sản phẩm. Xem evidence/trade_explorer_v1_3.
