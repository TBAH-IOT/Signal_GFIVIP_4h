# Tích hợp Signal_GFIVIP_4h v1.1.0

## Thay đổi bắt buộc so với v1.0

v1.0 chỉ có snapshot241 lệnh và theo dõi từ lúc bật service. **v1.1 thay thế chính sách đó bằng backtest liên tục từ25/04/2026 đến hiện tại**, kể cả khoảng trước triển khai/downtime. Không dùng lại hướng dẫn “không chạy bù các lệnh” của v1.0.

Tên public là `Signal_GFIVIP_4h`; `signal_name` có trong model/signal/health/stats/event. Strategy `model_id` và hash tham số toán học vẫn giữ để không đổi ID lịch sử chỉ vì đổi tên hiển thị. Ngưỡng, phí, vốn, horizon và non-overlap không thay đổi.

## Kiến trúc chạy thật

```text
Public Binance REST (15m price + premium + server time + ticker)
        ↓
HistoryCache: nến thật, phân trang, persist, kiểm tra thiếu dữ liệu
        ↓
calculate_book: causal replay TỪ ĐẦU mẫu, một ledger liên tục
        ↓
apply_book: commit đồng thời trades / cash / equity / per-coin stats / latest5
        ↓
REST + SSE → frontend của MVP / web tham chiếu
```

`mom_basis/continuous.py` là kernel production v1.1. `feed.Worker` tự đồng bộ lần đầu và mỗi boundary mới; `serve`/`create_app` mặc định live. Các hàm legacy v1 trong Store và `replay.py` phục vụ tương thích/đối chiếu241 lệnh, không phải đường xử lý live mới.

Lần đầu backend có thể cần vài giây để nạp cache/snapshot. Sau đó `history_status.phase` chuyển downloading → replaying → ready; lỗi dữ liệu/mạng giữ snapshot đã commit và chuyển error, retry. Giao diện không gọi đó là cập nhật đến hiện tại nếu `data_current=false`.

Mỗi lần restart bắt buộc tải đủ mọi bar còn thiếu và dựng lại đầy đủ virtual portfolio, không chỉ nạp689nến gần nhất. Cache giá/premium và ledger được lưu lâu dài, không prune xuống14ngày. Chỉ notification bị giới hạn5.

## Các quy tắc không được đổi

- Start cố định25/04/2026 16:15 UTC; không biến thành rolling180ngày hoặc tự nối về2022.
- Universe20 cố định trong `model.py`. Không tự thay top20 hôm nay.
- Tín hiệu dùng close/premium của nến 15m đã đóng; current candle chỉ cho **open đã biết** để định giá vào/thoát/MTM.
- Thuật toán xử lý thoát và giải phóng vốn trước các entry cùng timestamp; thứ tự coin cố định. Chặn overlap trong cùng coin.
- Vốn10.000 USDT dùng chung, 500/lệnh, phí+slippage10 bps tổng hai đầu; không SL/TP/DCA.
- Lệnh ở4h cuối chưa hết hạn vẫn nằm trong book với trạng thái mở; không bỏ đi rồi quên nối vào lần sync sau.
- Không cập nhật từng coin vào thống kê tổng một cách rời rạc: phải đủ dữ liệu tất cả20 coin và commit cùng một `as_of_ms`.
- Cấm dùng close/basis của nến hiện tại để chọn tín hiệu. Cấm tính forecast bằng lệnh chưa kết thúc vào thời điểm phát tín hiệu đó.

## Snapshot, live và notification

ZIP có dữ liệu thật cập nhật đến mốc ghi trong manifest/report. Lần deploy tương lai tự tải phần thiếu, không cần dev sửa ngày kết thúc hoặc chạy một notebook riêng.

Các lệnh lịch sử vừa reconstruct có `origin=backfill`, `notification_live=false`; mẫu gốc có thể giữ `origin=backtest`. Những lệnh này cập nhật toàn bộ stats và5 thẻ mới nhất nhưng **không phát `signal.opened` hàng loạt** và không tạo unread giả.

Tín hiệu mới ở boundary hiện tại được phát hiện kịp trong 120s khi worker đang hoạt động mới có `origin=forward_paper`, `notification_live=true`; phát chuông và badge. Đây vẫn là theo dõi giá tham chiếu, không phải lệnh sàn.

Forecast dưới cùng ID đã công bố giữ nguyên; kết quả/actual path được bổ sung. Restart và sync lặp cùng timestamp không nhân số lệnh hoặc thông báo.

## REST API

| Method | Endpoint | Công dụng |
| --- | --- | --- |
| GET | `/api/model` | Signal name, strategy ID/hash, tham số |
| GET | `/api/health` | Worker, sync phase, progress, `data_as_of_ms`, `data_current` |
| GET | `/api/notifications` | 5 thẻ mới nhất và unread theo session/user |
| POST | `/api/notifications/{id}/read` | Đọc thông báo, idempotent |
| GET | `/api/signals/{id}` | Chi tiết một trong5 thẻ đang giữ; cũ hơn trả404 |
| GET | `/api/stats` | Stats/equity toàn20 coin |
| GET | `/api/stats?coin=BTC` | Stats/equity BTC |
| GET | `/api/stats?chart_points=20000` | Giới hạn điểm vẽ; metrics vẫn dùng toàn bộ marks |
| GET | `/api/events` | SSE tự reconnect bằng Last-Event-ID |

`data_start_ms`, `data_as_of_ms` là mốc thật của số liệu; `updated_at_ms` chỉ là thời gian đọc/tính API, không thay thế mốc dữ liệu. WR/returns dùng decimal; tiền USDT; timestamp Unix milliseconds UTC. Percent chỉ nhân100 ở frontend. API contract/sample được xuất từ ứng dụng, có trong docs.

## SSE

| Event | Frontend làm gì |
| --- | --- |
| `snapshot` | Tải lại notifications/stats/health sau kết nối/reconnect |
| `history.updated` | Đã commit lịch sử mới, tải lại stats và5 thẻ; không toast lịch sử |
| `signal.opened` | Tín hiệu live mới, chuông/unread/toast + tải stats |
| `signal.ended` | Kết quả lệnh đã có giá thoát thật, tải stats |
| `stats.updated` | Tải lại các chỉ số/đường vốn |
| `quotes` | Cập nhật giá/actual line; không sửa forecast frozen |

Tắt buffering/cache ở proxy SSE, giữ timeout>=60s; event log hữu hạn, reconnect luôn đọc snapshot chuẩn. Frontend có polling15s cho trạng thái/health và fallback. Quote khoảng 5s, không tuyên bố tick-by-tick; stale>20s phải thể hiện gián đoạn. Tại deadline đổi nhãn đã kết thúc theo đồng hồ đã đồng bộ server ngay cả nếu dữ liệu settlement chưa sẵn sàng.

## Ánh xạ UI hai hình yêu cầu

Thẻ chứa `signal_name`, coin/LONG4h, entry reference, current/exit price, entry/exit time, `forecast.points[].mean_price` nét đứt, p10/p90, `sample_count`, `scope`, actual path/quote. Không điền số vào stop_loss/take_profit/R:R đang null vì mô hình chưa backtest các rule đó.

Click tới stats coin được bấm; có selector tổng20 coin. Hiển thị n_trades đóng, open_trades, WR gross/net, NetPnL%/USDT, Max DD, Sharpe và equity. Tổng dùng10.000 USDT; từng coin là attribution trên500 USDT, không phải tài khoản bị khóa vốn riêng. Nhãn BACKTEST/LIVE lấy `notification_live`, không đoán chỉ bằng ngày hoặc trạng thái mở.

## Auth và deploy

Demo có cookie HMAC HttpOnly/SameSite=Lax để tách đã đọc/chưa đọc theo browser. Khi vào MVP, nối `request.state.user_id` với account đã xác thực từ backend/gateway tin cậy; không nhận user ID do client tùy ý gửi. REST và SSE phải dùng cùng identity, ưu tiên reverse proxy cùng origin. Dùng Secure cookie sau HTTPS.

Chạy Python backend độc lập, Docker hoặc process manager của hệ thống. Frontend tĩnh không tự tải lại dữ liệu/tính mô hình nếu backend không chạy. Không có API key hoặc đặt lệnh lên sàn.

Một writer/SQLite state, khóa worker chống chạy hai process. Giữ volume cả DB/WAL/session.key. Backup bằng SQLite backup API hoặc dừng service, không chỉ copy riêng SQLite đang ghi. Nếu mở nhiều replica, tách singleton engine và chuyển locking/persistence sang hạ tầng tương ứng, không nhân engine theo số web worker.

Khi nâng từ state v1, lịch sử được dựng lại theo chính sách liên tục. Nếu từng có forward ledger v1, hệ thống lưu SQLite backup `legacy_v1_before_continuous.sqlite3` trước khi migrate. Giữ báo cáo241 lệnh gốc để audit; không sửa file baseline cho trùng số liệu hiện tại.

## Nghiệm thu

1. Chạy replay mẫu gốc, phải khớp241 lệnh và17.268 mốc equity.
2. Chạy pytest và `scripts/verify_continuous.py` trên data đến hiện tại: scheduler dùng factor cũ, cash+inventory độc lập, nguyên241 lệnh cũ, đúng non-overlap và cutoff.
3. Cold start từ ZIP mới: tải bù đến Binance hiện tại, history ready/data_currenttrue,20 coin cùng mốc.
4. Restart sau downtime: stats tăng theo lệnh lịch sử thật, không mất open position/đếm trùng/phát chuông hàng loạt.
5. Test auth và read state theo2 user, limit5, routing coin/tổng, API/SSE proxy, stale/reconnect.

Chưa được cung cấp repo/auth MVP nên cần dev kiểm tra tích hợp thực tế. Docker đã có cấu hình nhưng chưa chạy trong môi trường bàn giao. Không tuyên bố đã quan sát một lệnh live thật từ đầu đến hết 4h trong phiên này; vòng đời được kiểm tra bằng replay/fixtures thật và recovery tests.

## Tài liệu nguồn

[Binance USD-M market data: price/premium klines, server time, ticker](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data), [FastAPI StreamingResponse](https://fastapi.tiangolo.com/advanced/custom-response/).

`premiumIndexKlines` khác endpoint `/futures/data/basis`; không hoán đổi hai nguồn mà giữ nguyên model.
