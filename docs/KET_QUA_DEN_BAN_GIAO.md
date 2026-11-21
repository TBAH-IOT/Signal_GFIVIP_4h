# Signal_GFIVIP_4h: kết quả liên tục đến mốc đóng gói

Bắt đầu: **25/04/2026 16:15 UTC**. Đồng bộ đến open **21/11/2026 14:00 UTC**, tương ứng dữ liệu tín hiệu đã đóng đến boundary này. Nến đang chạy chỉ được dùng giá open, không dùng close/basis tương lai.

20 coin, vốn chung10.000 USDT, cố định500 USDT/lệnh, giữ 4h, không overlap trong cùng coin; tổng phí và slippage10 bps hai đầu. Không đổi ngưỡng hoặc lọc lại coin theo kết quả mở rộng.

## Tổng danh mục

| Phạm vi | Lệnh đóng | Lệnh mở | WR gross | WR net | Net_P | Max DD | Net PnL USDT |
| --- | --- | --- | --- | --- | --- | --- | --- |
| TOTAL | 308 | 0 | 63.64% | 61.04% | +8.45% | -4.55% | +845.29 |

Sharpe ngày UTC: **2.23**. Cash khả dụng tại mốc dữ liệu: **10845.29 USDT**.

Bản gốc241 lệnh là snapshot so sánh đến22/10/2026, Net_P+10,74%, Max DD−1,95%. Bản liên tục có thêm **67 lệnh** sau mẫu đó. Các lệnh chạy bù là lệnh mô phỏng theo dữ liệu thật, không phải lệnh đã khớp tài khoản người dùng hoặc thông báo từng được gửi trong quá khứ.

## Từng coin

| Phạm vi | Lệnh đóng | Lệnh mở | WR gross | WR net | Net_P | Max DD | Net PnL USDT |
| --- | --- | --- | --- | --- | --- | --- | --- |
| BTC | 12 | 0 | 58.33% | 58.33% | +12.04% | -2.74% | +60.22 |
| ETH | 15 | 0 | 73.33% | 73.33% | +7.88% | -3.95% | +39.39 |
| SOL | 16 | 0 | 68.75% | 50.00% | +4.81% | -4.25% | +24.07 |
| ZEC | 14 | 0 | 57.14% | 57.14% | +4.35% | -13.95% | +21.74 |
| BNB | 22 | 0 | 68.18% | 68.18% | +4.59% | -7.10% | +22.96 |
| XRP | 12 | 0 | 66.67% | 50.00% | +2.34% | -6.37% | +11.68 |
| NEAR | 9 | 0 | 44.44% | 44.44% | -7.34% | -14.56% | -36.70 |
| DOGE | 21 | 0 | 61.90% | 61.90% | +7.07% | -5.29% | +35.37 |
| UNI | 16 | 0 | 62.50% | 62.50% | +19.49% | -4.98% | +97.47 |
| SUI | 14 | 0 | 78.57% | 78.57% | +17.74% | -5.87% | +88.72 |
| ENA | 14 | 0 | 50.00% | 50.00% | -4.10% | -20.90% | -20.52 |
| LINK | 18 | 0 | 72.22% | 72.22% | +19.34% | -7.22% | +96.68 |
| AVAX | 20 | 0 | 60.00% | 60.00% | +8.49% | -7.09% | +42.43 |
| ADA | 16 | 0 | 68.75% | 68.75% | +10.28% | -4.76% | +51.41 |
| BCH | 14 | 0 | 50.00% | 42.86% | +0.53% | -9.28% | +2.63 |
| FIL | 18 | 0 | 55.56% | 50.00% | +9.31% | -5.91% | +46.56 |
| LTC | 10 | 0 | 70.00% | 70.00% | +21.18% | -3.61% | +105.88 |
| DOT | 20 | 0 | 70.00% | 70.00% | +20.12% | -4.68% | +100.59 |
| ARB | 11 | 0 | 63.64% | 54.55% | +5.60% | -4.26% | +27.99 |
| AAVE | 16 | 0 | 62.50% | 62.50% | +5.35% | -10.07% | +26.73 |

Net_P/Max DD từng coin dùng mốc500 USDT để thể hiện đóng góp; tổng danh mục dùng10.000 USDT, không cộng/trung bình các chỉ số coin để ra tổng.

## Năm lệnh gần nhất

| Coin | Vào UTC | Hết hạn UTC | Trạng thái | Net PnL USDT |
| --- | --- | --- | --- | --- |
| LTC | 21/11/2026 04:15 | 21/11/2026 08:15 | Đã kết thúc | +9.72 |
| AAVE | 21/11/2026 04:15 | 21/11/2026 08:15 | Đã kết thúc | +13.56 |
| ENA | 21/11/2026 04:15 | 21/11/2026 08:15 | Đã kết thúc | +9.47 |
| LINK | 21/11/2026 04:15 | 21/11/2026 08:15 | Đã kết thúc | +13.84 |
| FIL | 21/11/2026 04:15 | 21/11/2026 08:15 | Đã kết thúc | +8.70 |

## Khi triển khai sau mốc này

Chạy `python -m mom_basis serve` (mặc định live). Backend tự lấy Binance server time, tải tất cả nến giá/premium15m còn thiếu bằng phân trang, chạy lại sổ liên tục từ25/04/2026 và cập nhật stats/5 thẻ gần nhất. Sau khi đã đồng bộ, chuyển sang theo dõi mỗi nến 15m và quote khoảng 5s. Restart cũng chạy bù mọi lệnh mô phỏng đã bỏ lỡ; không phát chuông hàng loạt cho lịch sử.

Mốc trong báo cáo/ZIP là snapshot bàn giao. Mốc trên web tiếp tục tăng tự động khi Python backend chạy và có kết nối Binance. File tĩnh frontend một mình không thay thế backend xử lý mô hình.
