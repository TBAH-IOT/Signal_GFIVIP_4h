# Signal_GFIVIP_4h — bộ bàn giao MVP v1.1.0

Phiên bản này **tự chạy liên tục từ thời điểm bắt đầu backtest đến lúc triển khai**, rồi cập nhật tiếp khi đang chạy live. Không dừng ở snapshot241 lệnh ngày22/10. Tên tín hiệu trên API, thông báo và giao diện là **Signal_GFIVIP_4h**.

## Cách hoạt động khi import/triển khai

1. Backend nạp dữ liệu thật và snapshot mới nhất kèm trong ZIP.
2. Tự hỏi giờ Binance, phân trang tải **toàn bộ nến giá/premium15m còn thiếu** từ cache đến boundary hiện tại.
3. Tính lại danh mục liên tục từ **25/04/2026 16:15 UTC**, cùng bộ tham số/vốn/phí. Chỉ dùng nến đã đóng cho tín hiệu; nến hiện tại chỉ cung cấp open để vào/thoát/MTM.
4. Cập nhật đầy đủ sổ lệnh, WR gross/net, NetPnL, Max DD, Sharpe, đường vốn và5 thẻ gần nhất; không phát chuông hàng loạt cho các lệnh lịch sử vừa chạy bù.
5. Chuyển sang theo dõi live; mỗi boundary15m mới đều đồng bộ trước khi công bố stats. Giá thực tế cập nhật khoảng 5s.
6. Restart/mất mạng: tải bù và chạy bù các lệnh mô phỏng trong khoảng gián đoạn, rồi tiếp tục. Không reset vốn hoặc đếm trùng lệnh.

“Import lên web” cần có **Python backend đang chạy và truy cập được Binance**; chỉ copy file HTML/JS lên hosting tĩnh sẽ không tự chạy model. Bộ này có backend, API/SSE, giao diện tham chiếu và Docker để dev nối vào MVP hiện tại.

## Cấu hình đã kiểm thử

| Thuộc tính | Giá trị |
| --- | --- |
| Tên sản phẩm | Signal_GFIVIP_4h |
| Logic | LONG: MOM16:L + BASIS:L; rolling672/min168, quantile1%, onset |
| Giá / BASIS | Binance USD-M perpetual15m / close premium-index15m |
| Universe cố định | BTC, ETH, SOL, ZEC, BNB, XRP, NEAR, DOGE, UNI, SUI, ENA, LINK, AVAX, ADA, BCH, FIL, LTC, DOT, ARB, AAVE |
| Vốn | 10.000 USDT dùng chung; cố định500 USDT/lệnh, không vay |
| Chồng lệnh | Chặn trong cùng coin; các coin khác được mở đồng thời |
| Vào / thoát | Open sau nến tín hiệu / open sau đúng 4h |
| Tổng phí và slippage | **10 bps =0,1% tổng hai đầu**, không cộng thêm lần nữa |
| SL/TP/DCA | Không có trong logic này |

## Kết quả và dữ liệu bàn giao

Xem **[báo cáo đến mốc đóng gói](docs/KET_QUA_DEN_BAN_GIAO.md)**: số liệu tổng, từng coin,5lệnh cuối và timestamp cụ thể. Mốc này tăng tự động trên web khi backend chạy live; file báo cáo là snapshot tại lúc xuất gói.

Mẫu gốc25/04–22/10/2026 gồm 241 lệnh, WR gross69,29%, WR net66,39%, NetP+10,74%, DD−1,95% được giữ nguyên trong `data/baseline` để đối chiếu. **Không dùng241 lệnh làm số liệu hiện tại sau khi đã chạy bù.** Kết quả mở rộng có thể tốt/xấu hơn; không tối ưu lại ngưỡng hoặc loại coin thua để giữ bảng cũ.

Đã kèm nến thật20 coin từ đầu mẫu đến mốc xuất gói trong `data/continuous/`, SHA-256 manifest, sổ lệnh cập nhật và bằng chứng kiểm chứng độc lập trong `evidence/continuous/`.

## Chạy Windows

Python 3.13, pip >=22.3. Trong thư mục giải nén:

```powershell
.\install.ps1
.\start_live.ps1
```

Mở `http://127.0.0.1:8765`. Sau startup, giao diện có trạng thái đang đồng bộ/đã đồng bộ và **mốc dữ liệu thực tế**. Không cần CoinGlass hoặc API key Binance.

Lệnh Python tương đương:

```powershell
python -m venv --without-pip .venv
python -m pip --python .\.venv\Scripts\python.exe install -r requirements-test.lock
.\.venv\Scripts\python.exe -m mom_basis serve
```

`serve` mặc định **live**, tự catchup. `start_offline.ps1` hoặc `serve --mode offline` chỉ xem snapshot kèm ZIP, không gọi dữ liệu mới. Không chạy lại install cho mỗi lần khởi động.

## Chạy Linux / Docker

```bash
python3.13 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python -m mom_basis serve --host 0.0.0.0 --port 8765
```

Hoặc `docker compose up --build -d`. Đã cung cấp cấu hình; kiểm thử thực tế trên Windows/Python 3.13, chưa chạy Docker trong môi trường bàn giao. Chỉ một engine worker/SQLite state; dùng volume bền vững và gateway HTTPS của MVP.

## Lệnh hỗ trợ

```powershell
# Đồng bộ đến hiện tại rồi thoát, không phát thông báo lịch sử
.\.venv\Scripts\python.exe -m mom_basis sync

# Kiểm chứng riêng mẫu cũ241 lệnh; không dùng để giới hạn dữ liệu live
.\.venv\Scripts\python.exe -m mom_basis replay --out evidence

# Các kiểm thử causal replay, backfill/restart, API/SSE, vốn và phí
.\.venv\Scripts\python.exe -m pytest -q --basetemp .test_tmp
```

`sync --export data/continuous --report evidence/continuous` dành cho dev xuất snapshot bàn giao mới. Khi triển khai bình thường, không cần chạy sync bằng tay trước mỗi lần bật server.

## Luồng người dùng

- Chuông có badge theo user/session, chỉ5 tín hiệu mới nhất trên toàn20 coin. Backend vẫn giữ toàn bộ ledger/price cache để tính thống kê và restart.
- Thẻ: coin/LONG4h, entry reference, current/exit price, thời điểm vào/thoát, đường trung bình lịch sử và dải p10–p90, đường giá thực tế.
- Trước deadline: **[Đang mở]**; hết 4h: **[Đã kết thúc]**. Dữ liệu chưa đủ thì ghi đang chờ đồng bộ/giá thoát; chưa tính thắng/thua.
- Click tới thống kê coin; selector xem tổng20 coin. Chỉ lệnh đã quyết toán vào WR/NetPnL. DD/Sharpe từ MTM15m liên tục.
- Lệnh chạy bù là **BACKTEST**. Tín hiệu phát kịp thời khi service đang live có nhãn **LIVE**. PnL là mô phỏng theo mô hình, không phải PnL tài khoản thật; không đặt lệnh lên sàn.

Đường dự báo được cố định lúc phát tín hiệu, chỉ dùng lệnh lịch sử đã kết thúc trước thời điểm đó. Đây là trung bình lịch sử, không bảo đảm giá tương lai đi đúng đường vẽ; p10–p90 không phải SL/TP. Không sửa dự báo cũ để khớp kết quả sau này.

## Tài liệu cho dev/Claude

- [DEV_HANDOFF.md](docs/DEV_HANDOFF.md): kiến trúc, API/SSE, sync/auth/deploy.
- [MODEL_SPEC.md](docs/MODEL_SPEC.md): công thức, đơn vị, vốn, dự báo, chống look-ahead.
- [CLAUDE_HANDOFF_PROMPT.md](docs/CLAUDE_HANDOFF_PROMPT.md): prompt tích hợp vào repo MVP.
- [QA_REPORT.md](docs/QA_REPORT.md): phần đã kiểm chứng/phần cần nghiệm thu trên MVP thật.
- `docs/openapi.json`, `docs/api_examples.json`: API và payload thật.
- `evidence/ui_*.png`: ảnh desktop/mobile bằng dữ liệu thật.

Repo/auth của MVP chưa được cung cấp nên gói này chưa được ghép vào ứng dụng hiện tại. Dev dùng service này làm backend nội bộ, không cần đoán lại mô hình bằng frontend.
