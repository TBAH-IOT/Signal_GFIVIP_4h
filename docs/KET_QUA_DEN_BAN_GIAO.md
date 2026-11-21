# Signal_GFIVIP_4h: kết quả liên tục đến mốc đóng gói

Bắt đầu: **01/05/2026 00:00 UTC**. Đồng bộ đến open **21/11/2026 16:30 UTC**, tương ứng dữ liệu tín hiệu đã đóng đến boundary này. Nến đang chạy chỉ được dùng giá open, không dùng close/basis tương lai.

20 coin, vốn chung10.000USDT, cố định500USDT/lệnh, giữ4h, không overlap trong cùng coin; tổng phí và slippage10bps hai đầu. Không đổi ngưỡng hoặc lọc lại coin theo kết quả mở rộng.

## Tổng danh mục

| Phạm vi | Lệnh đóng | Lệnh mở | Winrate trước phí | Net_P sau phí | Max DD | Net PnL USDT |
| --- | --- | --- | --- | --- | --- | --- |
| TOTAL | 301 | 0 | 64.78% | +8.87% | -4.53% | +886.51 |

Sharpe ngày UTC: **2.40**. Cash khả dụng tại mốc dữ liệu: **10886.51 USDT**.

Profile v1.2 bắt đầu vốn và lệnh tại01/05/2026 00:00UTC. Có689nến warmup trước đó để tính factor; không đưa warmup vào số lệnh/PnL/DD/Sharpe hoặc tập forecast. Snapshot241lệnh từ25/04 của v1.1 chỉ còn là dữ liệu audit riêng, không trộn vào profile này. Các lệnh chạy bù là mô phỏng theo dữ liệu thật, không phải fill tài khoản hoặc thông báo đã gửi trong quá khứ.

## Từng coin

| Phạm vi | Lệnh đóng | Lệnh mở | Winrate trước phí | Net_P sau phí | Max DD | Net PnL USDT |
| --- | --- | --- | --- | --- | --- | --- |
| BTC | 12 | 0 | 58.33% | +12.04% | -2.74% | +60.22 |
| ETH | 14 | 0 | 71.43% | +6.44% | -4.01% | +32.21 |
| SOL | 16 | 0 | 68.75% | +4.81% | -4.25% | +24.07 |
| ZEC | 14 | 0 | 57.14% | +4.35% | -13.95% | +21.74 |
| BNB | 22 | 0 | 68.18% | +4.59% | -7.10% | +22.96 |
| XRP | 12 | 0 | 66.67% | +2.34% | -6.37% | +11.68 |
| NEAR | 9 | 0 | 44.44% | -7.34% | -14.56% | -36.70 |
| DOGE | 20 | 0 | 65.00% | +9.14% | -5.20% | +45.70 |
| UNI | 16 | 0 | 62.50% | +19.49% | -4.98% | +97.47 |
| SUI | 14 | 0 | 78.57% | +17.74% | -5.87% | +88.72 |
| ENA | 14 | 0 | 50.00% | -4.10% | -20.90% | -20.52 |
| LINK | 18 | 0 | 72.22% | +19.34% | -7.22% | +96.68 |
| AVAX | 20 | 0 | 60.00% | +8.49% | -7.09% | +42.43 |
| ADA | 15 | 0 | 73.33% | +11.37% | -4.71% | +56.83 |
| BCH | 14 | 0 | 50.00% | +0.53% | -9.28% | +2.63 |
| FIL | 17 | 0 | 58.82% | +12.35% | -5.76% | +61.74 |
| LTC | 9 | 0 | 77.78% | +22.29% | -3.57% | +111.45 |
| DOT | 19 | 0 | 73.68% | +20.80% | -4.65% | +104.00 |
| ARB | 10 | 0 | 70.00% | +7.30% | -4.20% | +36.48 |
| AAVE | 16 | 0 | 62.50% | +5.35% | -10.07% | +26.73 |

Net_P/MaxDD từng coin dùng mốc500USDT để thể hiện đóng góp; tổng danh mục dùng10.000USDT, không cộng/trung bình các chỉ số coin để ra tổng.

## Năm lệnh gần nhất

| Coin | Vào UTC | Hết hạn UTC | Trạng thái | Net PnL USDT |
| --- | --- | --- | --- | --- |
| LTC | 21/11/2026 04:15 | 21/11/2026 08:15 | Đã kết thúc | +9.72 |
| AAVE | 21/11/2026 04:15 | 21/11/2026 08:15 | Đã kết thúc | +13.56 |
| ENA | 21/11/2026 04:15 | 21/11/2026 08:15 | Đã kết thúc | +9.47 |
| LINK | 21/11/2026 04:15 | 21/11/2026 08:15 | Đã kết thúc | +13.84 |
| FIL | 21/11/2026 04:15 | 21/11/2026 08:15 | Đã kết thúc | +8.70 |

## Khi triển khai sau mốc này

Chạy `python -m mom_basis serve` (mặc định live). Backend tự lấy Binance server time, tải toàn bộ nến giá/premium15m còn thiếu cùng warmup trước01/05, dựng sổ từ01/05/2026 và cập nhật stats/5thẻ gần nhất. Tiếp tục theo dõi mỗi nến15m và quote khoảng5s; restart chạy bù, không phát chuông hàng loạt cho lịch sử. Nâng từ profile cũ sẽ tạo SQLite backup trước khi dựng lại sổ/forecast/thống kê.

Mốc trong báo cáo/ZIP là snapshot bàn giao. Mốc trên web tiếp tục tăng tự động khi Python backend chạy và có kết nối Binance. File tĩnh frontend một mình không thay thế backend xử lý mô hình.
