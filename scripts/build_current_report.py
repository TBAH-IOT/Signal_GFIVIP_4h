from pathlib import Path
import json
import sys
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from mom_basis.model import SIGNAL_NAME
from mom_basis.store import Store

state=Path(sys.argv[1]) if len(sys.argv)>1 else ROOT/'state_handoff_v1_1'
s=Store(state/'model.sqlite3')
total=s.metrics();trades=s.trades()
rows=[]
for coin in __import__('mom_basis.model',fromlist=['COINS']).COINS:
    r=s.metrics(coin)
    rows.append(r)
def pc(v):return '—' if v is None else f'{v*100:+.2f}%'
def dt(v):return pd.Timestamp(v,unit='ms',tz='UTC').strftime('%d/%m/%Y %H:%M')
def table(stats):
    lines=['| Phạm vi | Lệnh đóng | Lệnh mở | WR gross | WR net | Net_P | Max DD | Net PnL USDT |',
           '| --- | --- | --- | --- | --- | --- | --- | --- |']
    for r in stats:lines.append(f"| {r['coin']} | {r['n_trades']} | {r['open_trades']} | {pc(r['gross_winrate']).lstrip('+')} | {pc(r['net_winrate']).lstrip('+')} | {pc(r['net_profit'])} | {pc(r['max_drawdown'])} | {r['net_pnl']:+.2f} |")
    return '\n'.join(lines)
last=sorted(trades,key=lambda t:(t['entry_ms'],t['id']))[-5:][::-1]
body=[f'# {SIGNAL_NAME}: kết quả liên tục đến mốc đóng gói','',
    f"Bắt đầu: **{dt(total['data_start_ms'])} UTC**. Đồng bộ đến open **{dt(total['data_as_of_ms'])} UTC**, tương ứng dữ liệu tín hiệu đã đóng đến boundary này. Nến đang chạy chỉ được dùng giá open, không dùng close/basis tương lai.",'',
    '20 coin, vốn chung10.000USDT, cố định500USDT/lệnh, giữ4h, không overlap trong cùng coin; tổng phí và slippage10bps hai đầu. Không đổi ngưỡng hoặc lọc lại coin theo kết quả mở rộng.','',
    '## Tổng danh mục','',table([total]),'',f"Sharpe ngày UTC: **{total['sharpe_ratio']:.2f}**. Cash khả dụng tại mốc dữ liệu: **{s.meta('cash'):.2f} USDT**.",'',
    f"Bản gốc241lệnh là snapshot so sánh đến22/10/2026, Net_P+10,74%, MaxDD−1,95%. Bản liên tục có thêm **{len(trades)-241} lệnh** sau mẫu đó. Các lệnh chạy bù là lệnh mô phỏng theo dữ liệu thật, không phải lệnh đã khớp tài khoản người dùng hoặc thông báo từng được gửi trong quá khứ.",'',
    '## Từng coin','',table(rows),'',
    'Net_P/MaxDD từng coin dùng mốc500USDT để thể hiện đóng góp; tổng danh mục dùng10.000USDT, không cộng/trung bình các chỉ số coin để ra tổng.','',
    '## Năm lệnh gần nhất','',
    '| Coin | Vào UTC | Hết hạn UTC | Trạng thái | Net PnL USDT |','| --- | --- | --- | --- | --- |']
for t in last:body.append(f"| {t['coin']} | {dt(t['entry_ms'])} | {dt(t['exit_ms'])} | {'Đã kết thúc' if t['exit_price'] is not None else 'Đang mở'} | {'—' if t['net_pnl'] is None else format(t['net_pnl'],'+.2f')} |")
body+=['','## Khi triển khai sau mốc này','',
       'Chạy `python -m mom_basis serve` (mặc định live). Backend tự lấy Binance server time, tải tất cả nến giá/premium15m còn thiếu bằng phân trang, chạy lại sổ liên tục từ25/04/2026 và cập nhật stats/5thẻ gần nhất. Sau khi đã đồng bộ, chuyển sang theo dõi mỗi nến15m và quote khoảng5s. Restart cũng chạy bù mọi lệnh mô phỏng đã bỏ lỡ; không phát chuông hàng loạt cho lịch sử.','',
       'Mốc trong báo cáo/ZIP là snapshot bàn giao. Mốc trên web tiếp tục tăng tự động khi Python backend chạy và có kết nối Binance. File tĩnh frontend một mình không thay thế backend xử lý mô hình.','']
(ROOT/'docs'/'KET_QUA_DEN_BAN_GIAO.md').write_text('\n'.join(body),encoding='utf-8')
out=ROOT/'evidence'/'continuous'
out.mkdir(exist_ok=True)
clean_total={k:v for k,v in total.items() if k!='equity_curve'}
(out/'summary.json').write_text(json.dumps(clean_total,ensure_ascii=False,indent=2),encoding='utf-8')
pd.DataFrame([{k:v for k,v in r.items() if k not in ['equity_curve','history','baseline']} for r in rows]).to_csv(out/'per_coin.csv',index=False)
pd.DataFrame(trades).to_csv(out/'trades.csv',index=False)
print(f"{SIGNAL_NAME}: {total['n_trades']} closed, {total['open_trades']} open; Net_P {total['net_profit']:+.2%}; DD {total['max_drawdown']:.2%}; through {dt(total['data_as_of_ms'])} UTC")
