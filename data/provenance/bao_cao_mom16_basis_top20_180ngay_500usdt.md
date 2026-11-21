# MOM16:L + BASIS:L: 20 coin, mẫu 180 ngày, 500 USDT/lệnh

Chỉ mẫu nghiên cứu ban đầu: **25/04/2026 16:15 đến 22/10/2026 13:00 UTC**, khoảng 180 ngày. Nến 15m, vốn đầu **10.000 USDT**, tổng phí và slippage **10 bps hai đầu**.

Không mở thêm vị thế khi **cùng coin** đang có lệnh. Coin khác được giao dịch đồng thời, giống quy tắc tạo 60 lệnh top5 trước đây. Mỗi lệnh mua một lần dùng cố định 500 USDT gồm chi phí đầu vào; mua tại open sau nến tín hiệu và bán tại open sau đúng 4h. Không DCA hoặc stop loss trong bảng này.

Vốn dùng chung 10.000 USDT, chỉ tái sử dụng tiền sau khi thoát. Không cố định 500 USDT tiền mặt vào từng coin sau lỗ vì ngân sách vào lệnh lần này là cố định 500. Tín hiệu bị bỏ nếu tiền khả dụng không đủ. Khi nhiều coin cùng xuất hiện, xử lý theo thứ tự danh sách 20 coin đã công bố, không chọn bằng return tương lai.

## Kết quả tổng hợp

| Coin | Lệnh | WR trước phí | WR sau phí | Net_P | Max DD | Lãi net USDT |
| --- | --- | --- | --- | --- | --- | --- |
| TOTAL | 241 | 69.29% | 66.39% | 10.74% | -1.95% | 1073.69 |

Gross PnL **+1194.13 USDT**; chi phí **120.44 USDT**; Net PnL **+1073.69 USDT**. Vốn cuối **11073.69 USDT**.

Có 284 onset đủ giá thực thi; bỏ 43 vì cùng coin đang có lệnh; bỏ 0 vì thiếu tiền. Tối đa 14 vị thế mở đồng thời, tương đương 7000 USDT ngân sách vào đang hoạt động. Không tự cấp thêm vốn hoặc vay tiền.

## Từng coin

| Coin | Lệnh | WR trước phí | WR sau phí | Net_P | Max DD | Lãi net USDT |
| --- | --- | --- | --- | --- | --- | --- |
| BTC | 9 | 55.56% | 55.56% | 6.83% | -1.04% | 34.17 |
| ETH | 13 | 84.62% | 84.62% | 11.23% | -3.26% | 56.17 |
| SOL | 13 | 76.92% | 53.85% | 7.93% | -3.71% | 39.63 |
| ZEC | 10 | 70.00% | 70.00% | 9.46% | -13.95% | 47.29 |
| BNB | 15 | 73.33% | 73.33% | 4.42% | -4.44% | 22.11 |
| XRP | 10 | 70.00% | 60.00% | 7.22% | -4.96% | 36.10 |
| NEAR | 5 | 60.00% | 60.00% | -1.35% | -9.25% | -6.75 |
| DOGE | 17 | 70.59% | 70.59% | 10.51% | -5.03% | 52.56 |
| UNI | 15 | 66.67% | 66.67% | 23.03% | -4.55% | 115.17 |
| SUI | 10 | 90.00% | 90.00% | 19.63% | -4.80% | 98.13 |
| ENA | 10 | 50.00% | 50.00% | -1.83% | -13.32% | -9.15 |
| LINK | 14 | 78.57% | 78.57% | 23.26% | -2.56% | 116.28 |
| AVAX | 16 | 68.75% | 68.75% | 13.93% | -4.52% | 69.66 |
| ADA | 12 | 75.00% | 75.00% | 10.92% | -2.21% | 54.60 |
| BCH | 10 | 50.00% | 40.00% | -0.12% | -9.28% | -0.60 |
| FIL | 16 | 56.25% | 50.00% | 10.07% | -4.95% | 50.35 |
| LTC | 8 | 75.00% | 75.00% | 22.25% | -3.35% | 111.27 |
| DOT | 18 | 72.22% | 72.22% | 21.34% | -4.68% | 106.70 |
| ARB | 8 | 62.50% | 50.00% | 6.91% | -3.33% | 34.56 |
| AAVE | 12 | 66.67% | 66.67% | 9.09% | -5.98% | 45.44 |

Net_P/Max DD từng coin dùng mốc quy ước 500 USDT để thể hiện đóng góp riêng, không phải tài khoản tiền mặt bị khóa riêng cho coin đó. Max DD danh mục tính từ equity tổng mark-to-market tại open mỗi 15m.

## Bảng tín hiệu trước khi bỏ overlap trong coin

| Coin | Event | P_up | Mean 4h | Edge sau 10 bps |
| --- | --- | --- | --- | --- |
| TOTAL | 284 | 70.77% | 1.06% | 96.46 |

Đây là return close-to-close theo toàn bộ event, không phải số lệnh thực thi. Mô phỏng danh mục ở trên dùng next-open và loại overlap trong coin. Các coin có tương quan, các event không được coi là quan sát độc lập.

## Chạy lại

```powershell
python D:\Live_Trade\backtest_mom16_basis_top20_180d_500usdt.py
```

Kết quả chi tiết, ledger và equity: `D:\Live_Trade\mom16_basis_top20_180d_500usdt_results`.
Dữ liệu local Binance thật đã có sẵn, không gọi API. Tất cả 20 coin đã niêm yết trước cửa sổ này. Không tối ưu lại ngưỡng hoặc loại coin thua sau khi xem kết quả.
