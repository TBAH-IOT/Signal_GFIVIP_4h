# Prompt tích hợp Signal_GFIVIP_4h v1.1

Copy nội dung dưới cho Claude cùng repo MVP và gói đã giải nén:

---

Hãy tích hợp **Signal_GFIVIP_4h** vào MVP hiện tại. Đọc README, docs/MODEL_SPEC.md, DEV_HANDOFF.md, OpenAPI và code mom_basis/continuous.py trước. Khảo sát stack/auth/component/router hiện có rồi tích hợp thật, không chỉ viết kế hoạch. Giữ Python như service nội bộ nếu phù hợp; không cần chuyển model sang JavaScript.

Yêu cầu:

1. Tên hiển thị, chuông, detail và API public là Signal_GFIVIP_4h. Strategy là MOM16:L+BASIS:L,20 coin cố định, nến 15m đã đóng, LONG giữ 4h, vốn chung10.000 USDT/500mỗi lệnh, non-overlap trong cùng coin, tổng phí+slippage10 bps hai đầu. Không thêm SL/TP/DCA.
2. **Bắt buộc tự đồng bộ toàn bộ lịch sử từ25/04/2026 16:15 UTC đến thời điểm deploy**, không chỉ seed241 lệnh22/10 rồi chạy từ lúc bật. Backend serve mặc định live. Giữ cache/pagination, replay toàn bộ portfolio liên tục và commit stats/20 coin cùng as_of. Restart/mất mạng cũng phải chạy bù các lệnh mô phỏng bị lỡ. Không reset ngày bắt đầu/cash/warmup hoặc dùng current unclosed close để chọn tín hiệu.
3. UI có progress syncing/downloading/replaying/ready/error, mốc dữ liệu thực `data_as_of_ms`; không dùng thời gian response để ghi “đã cập nhật hiện tại” khi history chưa đủ.
4. Chuông/unread theo user đã xác thực, chỉ5 signal mới nhất. Lệnh backfill chỉ cập nhật thẻ và stats, không phát chuông hàng loạt. Tín hiệu live mới phát signal.opened, idempotency theo ID engine. Giữ ledger đầy đủ ở backend.
5. Thẻ giống bố cục tham chiếu: tên signal, coin/LONG4h, [Đang mở]/[Đã kết thúc], entry reference, current/exit price, vào/thoát, forecast mean nét đứt/p10p90/actual price tách màu, cohort/N. Không vẽ dự báo tùy ý hoặc điền SL/TP/R:R null. Forecast theo ID phải frozen, không sửa cho khớp thực tế sau này.
6. Danh mục luôn cố định 20 coin, không có chọn số lượng coin. Click thẻ/chuông tới stats coin vừa bấm. Bộ chọn **Báo cáo số liệu** chỉ có **Tổng thể chiến thuật · 20 coin** (mặc định) và **Coin đang xem · [coin vừa bấm]**; chưa bấm tín hiệu thì lựa chọn coin bị khóa. Giữ coin này khi chuyển qua lại hai báo cáo và khi refresh/SSE cập nhật. Hiển thị n_closed/open, **WR trước phí**, NetPnL%/USDT **sau phí**, DD, Sharpe, equity; bỏ ô winrate sau phí trên UI. API vẫn có net_winrate/net_wins để tương thích. Từ đầu backtest đến as_of thật, không hard-code241 hoặc bảng minh họa trong ảnh. Vốn tổng10k, attribution từngcoin500 phải ghi đúng.
7. Nối SSE snapshot/history.updated/signal.opened/signal.ended/stats.updated/quotes, reconnect/poll fallback, stale state và pending settlement. User auth từ gateway/backend tin cậy; không dùng ID tự khai. Một engine worker/SQLite state bền vững, không tạo engine trên từng frontend client hoặc mỗi web replica.
8. Đây là tín hiệu + theo dõi mô phỏng. Không gắn tài khoản/API key hay đặt lệnh thật lên sàn.

Kiểm thử trước khi merge/deploy: mẫu gốc241 lệnh vẫn đúng+10,74%/DD−1,95%; bản liên tục khớp báo cáo mới theo timestamp; pytest pass, checksum/data không thiếu, cold start→đồng bộ đến hiện tại, restart→không mất/nhân vị thế, backfill→không spamchuông,2 userreadstate tách biệt, frontend/REST/SSE proxy hoạt động. Báo rõ phần đã chạy và phần còn cần môi trường deploy. Không đổi ngưỡng/loại coin để giữ số liệu đẹp của mẫu cũ.
