# Kiểm thử Signal_GFIVIP_4h v1.1 — 21/11/2026

| Hạng mục | Đã kiểm tra |
| --- | --- |
| Mẫu gốc |241 lệnh/284 quyết định/17.268 mốc equity vàcash khớp hoàn toàn |
| Bản mở rộng |Dữ liệu thật liên tục20 coin từ25/04/2026 đến mốc ghi ở `KET_QUA_DEN_BAN_GIAO.md` |
| Đối chiếu độc lập |Dùng hàm factor gốc + scheduler khác; IDs/times/PnL khớp; equity=cash+inventory từng mốc |
| 241 lệnh ban đầu |Giữ nguyên giá/return/PnL, không viết lại để làm đẹp kết quả |
| Non-overlap/vốn/cost |Không chồng trong cùng coin, không vay, 500/lệnh, tổng10 bps, đúng 4h |
| Unit/integration |20 tests pass: gồm7 tests mới cho full replay, seam đang mở, restart, causal forecast, current candle exclusion, backfill im lặng/live notify, pagination/hole recovery và commit atomic |
| Public API/worker |Thực sự tải price/premium và đồng bộ; worker2chu kỳ; health/as_of/quotes có lưu bằng chứng |
| Browser |Đúng tên mới,5 card/5 notification, click mở đúng coin, tổng theo snapshot mới, mobile không tràn ngang, không JavaScript error |
| Export |OpenAPI, payload thật, snapshot20 coin vàmanifestSHA-256; ZIP được giải nén chạy độc lập |

Số liệu hiện tại và timestamp lấy từ `evidence/continuous/summary.json`; bảng gốc241 lệnh chỉ là đối chiếu. Báo cáo independent verification ghi số mốc, sai số equity tối đa và các invariant cụ thể, không chỉ xác nhận con số tổng.

Tests dùng giá thật từ file local. Một số unit test thay timestamp hoặc dùng dãy toán học để kiểm tra vòng đời; không đưa fixture giả vào dataset/số liệu sản phẩm. Dependency test có một cảnh báo deprecation từ Starlette TestClient/httpx, không có test fail; không ảnh hưởng runtime đọc Binance.

Kiểm thử trên Windows/Python 3.13, requirements đã pin. Repo/auth/gateway MVP và Docker chưa được kiểm thử trong môi trường deploy vì chưa có repo/infra đó. Chưa chờ một signal live mới chạy đủ4h trong phiên này; vòng đời đã được kiểm tra bằng replay/restart/giá thật theo nến.

Kết quả backtest là virtual execution theo open và10 bps giả định; không phải PnL user-account. Các lệnh reconstruct trong downtime không được diễn giải là thông báo đã gửi hoặc giao dịch đã khớp trước đây. Forecast mean cố định theo thông tin quá khứ, không bảo đảm diễn biến tương lai.

## Cập nhật giao diện trên main — 21/11/2026

Đã bỏ ô winrate sau phí; còn 5 ô thống kê, với Net PnL vẫn sau tổng chi phí 10 bps. Danh mục mô hình giữ cố định 20 coin. Bộ chọn báo cáo có đúng hai lựa chọn: tổng thể chiến thuật (mặc định) và coin vừa bấm từ thẻ/chuông; chưa bấm thì lựa chọn coin bị khóa.

Đã chạy lại 20 tests, đều pass. Kiểm tra Chrome/Playwright trên API dữ liệu thật: 5 thẻ và 5 thông báo; chọn coin từ chuông và từ thẻ khác; chuyển tổng thể/coin khớp API; refresh giữ coin đang xem; không còn ô winrate sau phí; không tràn ngang ở màn hình 390px; không có JavaScript error. Backend local live đã đồng bộ thành công price/premium và quote cho đủ 20 coin, `history.phase=ready`/`data_current=true` tại lúc kiểm tra. Chưa quan sát thêm một tín hiệu live mới trọn 4h trong lần cập nhật UI này.

ZIP/tag `v1.1.0` vẫn là bản phát hành gốc; các thay đổi trên nằm ở source nhánh main. State, log, ảnh kiểm tra và script riêng để mở bản xem local được lưu ngoài repository.
