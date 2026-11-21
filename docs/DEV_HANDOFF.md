# Tích hợp Signal_GFIVIP_4h v1.3.0

## Profile bắt buộc

Vốn/lệnh/thống kê/forecast từ **01/05/2026 00:00 UTC**. Warmup689 nến từ23/04/2026 19:45 UTC chỉ để tính MOM/quantile/onset. Danh mục20coin cố định, 15m, LONG giữ4h, chung10.000USDT/500mỗi lệnh, non-overlap trong cùng coin, tổng phí+slippage10bps hai đầu. Không SL/TP/DCA; không lấy dữ liệu nến chưa đóng để trigger.

`model.py` chứa BACKTEST_START_MS, HISTORY_START_MS, PROFILE_ID. `spec_hash` nhận diện quy tắc toán học; `profile_id` bổ sung mốc bắt đầu/warmup. Không chỉ đổi ngày ở HTML hoặc cắt các lệnh từ sổ25/04: phải replay từ vốn gốc, không carry vị thế trước01/05. Cohort forecast chỉ gồm lệnh profile mới đã hoàn tất trước entry; freeze trong cùng profile.

## Engine và đồng bộ

Public Binance REST → HistoryCache → calculate_book → apply_book → SQLite → REST/SSE → frontend. Nạp snapshot thật kèm gói; tải bù toàn bộ phần thiếu từ warmup đến boundary Binance mới nhất. Cache kiểm tra hole/NaN, không nội suy hoặc forward-fill. Cần đủ20coin cùng timeline trước atomic commit; lỗi/độ trễ đầu nến giữ snapshot đã commit và retry, không gọi dữ liệu cũ là current.

`calculate_book` tính factor trên cả warmup, bỏ entry trước01/05, khởi tạo vốn10k tại mốc đó, chỉ tạo marks/coin_marks từ01/05. Thoát trước entry cùng thời điểm; priority coin cố định. Lệnh cuối mẫu chưa đủ4h vẫn mở và giữ vốn. Current candle chỉ đóng góp OPEN cho entry/exit/MTM.

## Migration và restart

Một worker/state, khóa ProcessLock. Trước đổi profile, backup SQLite bằng backup API sang `before_profile_*.sqlite3`. Cache cũ vẫn được dùng và bổ sung warmup/giá thiếu. Migration thay toàn bộ trades, paths, marks, coin_marks, decisions, notifications/read state và event cũ trong transaction; tạo history.updated/stats.updated cho profile mới. Không giữ forecast từ profile cũ chỉ vì signal ID trùng; không phát signal.opened cho lịch sử rebuild. Từ lần sau, cùng profile chỉ cập nhật phần mới, giữ forecast frozen và kiểm tra ledger cũ không biến mất.

Ngày deploy tương lai tự catchup; không hard-code ngày cuối/số lệnh. Nếu mất mạng, giữ cache/ledger và hiển thị gián đoạn, restart chạy bù. Không tạo engine riêng cho mỗi frontend client hoặc web replica. Nhiều replica cần singleton engine và persistence/locking thích hợp.

## REST và SSE

| Endpoint | Vai trò |
| --- | --- |
| GET /api/model | Quy tắc, profile_id, backtest_start_ms, history_start_ms, warmup_bars |
| GET /api/health | version/profile, phase, data_as_of_ms, data_current, stale/worker |
| GET /api/notifications |5 tín hiệu mới nhất, unread riêng user/session |
| POST /api/notifications/{id}/read | Đánh dấu đã đọc |
| GET /api/signals/{id} | Chi tiết tín hiệu thuộc latest5 |
| GET /api/trades?coin=BTC&limit=50&offset=0 | Lịch sử coin có phân trang; không giới hạn latest5 |
| GET /api/trades/{id} | Chi tiết archive, OHLC thật, entry/exit và navigation previous/next |
| GET /api/stats[?coin=BTC] | Tổng/từng coin, chỉ số và equity_curve |
| GET /api/events | SSE, Last-Event-ID/reconnect, snapshot bắt buộc |

SSE: snapshot, history.updated, signal.opened, signal.ended, stats.updated, quotes. Dùng data_start_ms/data_as_of_ms cho khoảng dữ liệu; updated_at_ms chỉ là lúc tính/đọc. Proxy tắt buffering/cache SSE, timeout đủ dài; giữ snapshot/poll fallback. Quote khoảng5s, stale>20s. Sau deadline4h đổi Đã kết thúc, nếu chưa có exit open thì pending settlement, chưa đếm WR.

API percent/return là decimal, tiền USDT, timestamp milliseconds UTC. Tổng vốn10k, attribution từng coin chia500; không cộng/trung bình WR/DD coin để ra tổng. WR/PnL chỉ lệnh đóng; DD/Sharpe từ equity MTM15m, Sharpe theo ngàyUTC/sqrt365/riskfree0. API vẫn có net_winrate/net_wins/số quan sát; UI chỉ hiện WR trước phí và chú thích Sharpe Theo ngày UTC.

## UI và auth

Danh mục20coin cố định. Trang đầu chỉ có dải5thẻ nhỏ nằm ngang và PnL sau phí cho lệnh đã đóng, nền xanh/đỏ nhẹ. Chỉ sau click thẻ/chuông mới hiện vùng bên dưới, luôn mở Chi tiết lệnh của đúng ID được bấm. Mũi tên đi qua toàn bộ ledger cùng coin; latest5 chỉ là giới hạn thông báo. Tab Hiệu suất mô hình giữ selector Tổng thể / Coin đang xem. Trục/caption/đường vốn vẫn từ01/05. Xem TRADE_EXPLORER.md cho payload, màu, markup và các quy tắc UI.

Thẻ và chi tiết giữ frozen historical mean. Biểu đồ chi tiết dùng OHLC thật từ cache, entry/exit open đúng4h. Kết quả dương sau phí gắn TP, âm gắn SL, zero gắn Hòa vốn; đây là result_tag, không phải bracket order. exit_reason luôn TIME_4H; stop_loss/take_profit/R:R vẫn null. Lệnh đang mở chỉ có đường dọc/nến mờ đánh dấu giờ thoát, không gán OHLC tương lai. Current OHLC của coin đang mở cập nhật từ price klines khoảng5s, không sửa closed factor bars. Backfill là BACKTEST, alert kịp lúc mới là LIVE. Theo dõi mô phỏng, không có broker execution.

Cookie HMAC demo chỉ tách read state theo browser. Tích hợp account MVP vào request.state.user_id từ gateway/backend đã xác thực, không nhận ID tự khai. REST/SSE cùng origin/identity, Secure cookie sau HTTPS. Giữ DB/WAL/session.key bền vững; backup bằng SQLite API hoặc dừng writer. Docker cung cấp nhưng chưa kiểm thử deploy tại môi trường này.

## Nghiệm thu

1. CLI replay mặc định phải là profile01/05; --legacy-reference chỉ audit241lệnh cũ.
2. Pytest: regression gốc, May1/warmup, migrationbackup, restart/idempotency/forecast causal, API/latest5/readstate.
3. verify_continuous.py: factor gốc + scheduler độc lập, equity=cash+inventory, không vay/chồng coin, không lệnh trước01/05.
4. Cold start gói mới và nâng từ state cũ ra cùng kết quả, không alert lịch sử.
5. UI desktop/mobile: ngày đầu01/05, tổng/coin khớp API, realtime/reconnect/proxy/auth trên MVP thật.

Chưa quan sát một lệnh live mới trọn4h trong phiên bàn giao; vòng đời được kiểm tra bằng replay/giá thật/recovery tests. Chưa có môi trường gateway/auth MVP để nghiệm thu tích hợp ngoài service này.
