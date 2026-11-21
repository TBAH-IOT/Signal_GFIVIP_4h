# Signal_GFIVIP_4h — công thức và chính sách liên tục

## Danh tính / đơn vị

Tên public: **Signal_GFIVIP_4h**. Logic nội bộ vẫn `MOM16:L+BASIS:L`, LONG, horizon4h. Đổi tên hiển thị không đổi tham số hoặc ID lịch sử.

Timestamps UTC Unix milliseconds; giá USDT/coin; MOM/BASIS/return/WR/PnL% là decimal. `0.001 =0,1%=10 bps`. Không nhân100 trước khi tính toán; chỉ nhân100 khi hiển thị.

Universe và thứ tự ưu tiên cố định: BTC,ETH,SOL,ZEC,BNB,XRP,NEAR,DOGE,UNI,SUI,ENA,LINK,AVAX,ADA,BCH,FIL,LTC,DOT,ARB,AAVE. Bắt đầu vốn/lệnh/marks/thống kê tại **01/05/2026 00:00 UTC**. Tải689nến warmup từ23/04/2026 19:45UTC để tính factor/onset; warmup không tạo lệnh hoặc PnL, không carry vị thế trước mẫu. spec_hash giữ danh tính quy tắc toán học; profile_id nhận diện mốc bắt đầu/warmup của v1.2.

## Factor và trigger

Với `C[t]` là close nến 15m đã đóng:

```text
MOM16[t] = C[t] / C[t−16] − 1
BASIS[t] = close premium index Binance USD-M của cùng nến 15m
Q01_x[t] = rolling quantile_0.01(x[t−671..t]), min168 hợp lệ
Q99_x[t] = rolling quantile_0.99(x[t−671..t]), min168 hợp lệ

active[t] = MOM16[t] <= Q01_MOM16[t]
            AND BASIS[t] <= Q01_BASIS[t]
            AND Q99_MOM16[t] > Q01_MOM16[t]
            AND Q99_BASIS[t] > Q01_BASIS[t]

trigger[t] = active[t] AND NOT active[t−1]
```

672 nến=7ngày,16 nến=4h, quantile nội suy tuyến tính pandas; code dùng `1−0.99` đúng phép tính bản gốc. Lấy onset của hai điều kiện đồng thời, không nhận mọi nến đangởL. L chỉ thấp tương đối, không nhất thiết âm.

BASIS ở đây **chỉ là close `/fapi/v1/premiumIndexKlines`**, dimensionless. Không thay bằng funding, endpoint `/futures/data/basis`, futures−spot hay mark/index ratio. Không forward-fill dữ liệu thiếu.

## Thời gian và danh mục

```text
entry_time = open_time[t] + 15 phút
exit_time  = entry_time + 16×15 phút
entry_price = open(entry_time)
exit_price  = open(exit_time)
```

Mỗi lệnh500 USDT từ cash chung ban đầu10.000 USDT. Lợi nhuận giữ lại nhưng budget vẫn500, không tăng theo equity. Cùng coin đang mở thì bỏ onset mới; coin khác được mở nếu đủ cash. Thoát/giải phóng tiền trước entry cùng timestamp. Nếu nhiều coin cùng entry, xử lý theo thứ tự universe đã công bố.

Lệnh cuối cửa sổ chưa đủ4h vẫn mở và giữ vốn; lần cập nhật sau tiếp tục vị thế đó. Không bỏ những lệnh này vì thiếu future label. Các quyết định chỉ dùng thông tin đã có tại entry; giá thoát chỉ được giải phóng thành cash khi đến đúng deadline. Không vay, không DCA, không SL/TP, không đóng sớm theo forecast.

Mỗi replay chạy từ đầu mẫu đến boundary mới nhất, dùng cache liên tục; không reset rolling/cash tại ngày22/10 hay lúc restart. Đủ20 coin cùng một timeline mới commitbook. Giá/premium thiếu thì giữ snapshot đã commit, báoerror/retry thay vì làm số liệu tạm cho ít coin hơn.

Tại thời gian hiện tại `T=floor(BinanceServerTime/15m)×15m`, chỉ dùng nến trướcT cho factor. Dòng nếnT đang chạy chỉ dùng **open đã biết** cho entry/exit/MTM. Thay high/low/close/basis dòng hiện tại không được đổi tín hiệu hoặc forecast.

## Phí và slippage

```text
b = 500 USDT
c = 10 / 10000 = 0.001   (tổng cả hai đầu)
n = b / (1 + c/2)        = 499.7501249375 USDT notional
q = n / entry_price
r_gross = exit_price / entry_price − 1
PnL_gross = n × r_gross
cost_total = n × c       = 0.4997501249 USDT/lệnh
PnL_net = PnL_gross − cost_total
cash_entry = cash_before − b
cash_exit = cash_after_entry + b + PnL_net
```

Đúng mô hình chi phí của241 lệnh gốc; không trừ thêm slippage0,1% một lần nữa, không biến10 bps tổng thành10 bps/mỗiđầu. Đây là chi phí giả định trên entry notional, không phải statement phí/funding thực tế của tài khoản người dùng.

## Backfill và live notice

Historical reconstruction dùng open tại thời điểm tín hiệu trong lịch sử để backtest cả giai đoạn chưa chạy service hoặc downtime. Đây là lệnh mô phỏng, không diễn giải thành fill tài khoản hay alert đã gửi trước đây.

- `notification_live=false`: BACKTEST/backfill, có trong toàn bộ thống kê và latest5 nhưng không spamchuông/unread.
- `notification_live=true`: tín hiệu mới ở boundary hiện tại, được worker phát hiện trong 120s khi live; có `detected_ms` và `latency_ms`, phát `signal.opened` một lần.
- Trigger tới muộn vẫn có thể được reconstruct vào virtual backtest khi dữ liệu đủ, nhưng không phát alert cũ như vừa xảy ra.

Do đó stats hiển thị là hiệu suất mô hình liên tục từ đầu mẫu; không gọi tất cả các lệnh là lệnh user đã nhận/đã khớp. Giá open tham chiếu có thể khác giá lúc người dùng nhận thông báo.

## Đường dự báo trung bình4h

Tại entry `T_s`, chỉ dùng lệnh trong profile bắt đầu01/05/2026 đã hoàn tất với `exit_i<=T_s`. Ưu tiên cùng coin nếu có >=5 mẫu; dưới 5 dùng pooled20 coin và trả rõscope/N. Dùng lệnh được portfolio nhận, không gồm các onset bị chặn bởi overlap/cash. Các coin có tương quan, không xem các mẫu gộp là độc lập thống kê.

```text
r_i(k) = open_i(entry_i + k×15m) / entry_price_i − 1, k=0..16
mean_r(k) = average_i[r_i(k)]
forecast_s(k) = entry_price_s × (1 + mean_r(k))
p10_s(k) = entry_price_s × (1 + quantile_0.10_i[r_i(k)])
p90_s(k) = entry_price_s × (1 + quantile_0.90_i[r_i(k)])
P_up_history = count(r_i(16)>0) / N
```

17 điểm0..4h, chỉ dùng past matured paths. `sample_count/scope/as_of_ms/latest_training_exit_ms/frozen=true` được lưu. Không có mẫu thì `available=false`, không vẽ đường giả. Mỗi forecast đã phát theo signal ID giữ nguyên khi restart trong cùng profile; khi chuyển từ profile25/04 sang01/05 phải backup và dựng lại cohort/forecast, chỉ thêm actual path/kết quả và dùng lệnh mới đãđóng cho các forecast sau.

Mean là conditional historical mean, không bảo đảm đường giá tương lai. P_up là tần suất gross lịch sử, không phải winrate net đã calibration cho lệnh mới. p10–p90 là dải quantile tại từng thời điểm, không phải confidence interval cho mean hoặc cam kết cả đường giá nằm trong dải80%. SL/TP/R:R=null vì chưa có quy tắc được kiểm thử.

Backfilled forecast cũng dùng đúng tập đã kết thúc trước entry lịch sử; không lấy tất cả lệnh hiện tại để dự báo ngược cho lệnh đầu tiên.

## Thống kê liên tục

```text
N_closed = số lệnh có giá thoát thực tại deadline
WR_gross = count(PnL_gross>0) / N_closed
WR_net = count(PnL_net>0) / N_closed
Net_P = sum(PnL_net_closed) / initial_capital
E(u) = cash(u) + sum(quantity_open × open_price_at_u)
DD(u) = E(u) / max(E(0)..E(u)) − 1
Max_DD = min_u DD(u)
PF_net = sum(positive NetPnL) / abs(sum(negative NetPnL))
```

PnL tổng trên thẻ chỉ là lãi đã đóng; lệnh chưa quyết toán không tính thắng/thua. DD dùng **open mỗi 15m**, đúng chuẩn bản gốc, không đổi sang drawdown intrabar. Equity MTM được dựng liên tục suốt giai đoạn chạy bù, không chỉ thêm các NetPnL khi đóng rồi gọi đó là DD.

Sharpe dùng daily returns từ equity cuối ngàyUTC(mốc23:45open), chỉ lấy ngày đủ96 marks và ngày trước cũng đủ:

```text
r_day[d] = E_last_day[d] / E_last_day[d−1] − 1
Sharpe = mean(r_day) / sample_std(r_day) × sqrt(365)
```

Risk-free0, không annualize theo số lệnh. Không đủ mẫu/variance thì null. Vì v1.1 đã dựng đủ lịch sử liên tục, không còn khoảng trống giả giữa snapshot cũ và ngày bật service. Không tự gán zero-return cho dữ liệu chưa tải xong.

Tổng danh mục chia vốn10.000 USDT. Từng coin chia mốc500 USDT để thể hiện attribution, không phải một tài khoản riêng bị khóa500. Không cộng/trung bình WR hoặc DD các coin để ra tổng.

API `data_start_ms/data_as_of_ms` là khoảng số liệu thực đã commit; `updated_at_ms` là thời gian tính/đọc. Chỉ `data_current=true` khi ready và as_of bằng boundary Binance hiện tại. Snapshot241 lệnh gốc giữ nguyên cho audit; số hiện tại lấy ledger liên tục, không hard-code241.
