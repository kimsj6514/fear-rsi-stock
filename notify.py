"""Scheduled Telegram notification; sends only when the stock signal changes."""
import csv,json,os
from pathlib import Path
import requests
from signals import WATCH_DEFAULT,load_universe,market_mood,analyze_stock
STATE=Path('stock_alert_state.json'); HISTORY=Path('stock_signal_history.csv')
def main():
    token=os.environ.get('TELEGRAM_BOT_TOKEN');chat=os.environ.get('TELEGRAM_CHAT_ID')
    if not token or not chat:raise RuntimeError('텔레그램 Secrets 설정 필요')
    old=json.loads(STATE.read_text(encoding='utf-8')) if STATE.exists() else {}; new=dict(old)
    mood=market_mood();universe,source=load_universe(80); bycode={x['code']:x for x in universe}
    for code,name in WATCH_DEFAULT.items():bycode.setdefault(code,{'code':code,'name':name,'market':'KOSDAQ' if code in ('247540','086520') else 'KOSPI'})
    watch=[x.strip().zfill(6) for x in (os.environ.get('WATCH_CODES') or '005930,000660,035420,247540').split(',') if x.strip()]
    # Watchlist is intraday; scan is bounded daily-only. Full-market scan is not claimed.
    selected={}
    for code in watch:
        if code in bycode:selected[code]=(bycode[code],True)
    failures=[];messages=[]
    for item in universe:
        if item['code'] not in selected:selected[item['code']]=(item,False)
    for code,(item,detail) in selected.items():
        try:
            r=analyze_stock(item,mood,detail)
            current=r['label'] if '매수' in r['label'] or '매도' in r['label'] else '없음'
            key=f'{code}:{"watch" if detail else "scan"}'
            if current!='없음' and current!=old.get(key,'없음'):
                frames='\n'.join(f"{k}: {v['direction']} · RSI {v['rsi']}" for k,v in r['frames'].items())
                msg=(f"📊 Fear-RSI STOCK | {r['name']} ({code})\n{r['label']}\n{r['reason']}\n"
                     f"기준 종가 {r['price']:,.0f}원 ({r['date']})\n30거래일 고점 대비 {r['drop30']:+.1f}% · 일봉 {r['trend']}\n"
                     f"코스피 RSI {mood['kospi_rsi']} · VIX {mood['vix']}\n{frames}\n{r['url']}\n참고 신호 / 자동매매 없음")
                response=requests.post(f'https://api.telegram.org/bot{token}/sendMessage',json={'chat_id':chat,'text':msg,'disable_web_page_preview':True},timeout=20)
                response.raise_for_status()
                if not response.json().get('ok'):raise RuntimeError('Telegram sendMessage 실패')
                messages.append({'code':code,'name':r['name'],'signal':current,'price':r['price'],'date':r['date'],'drop30':r['drop30'],'trend':r['trend']})
                print('Sent:',key,current)
            new[key]=current
        except Exception as e:failures.append(f'{code}: {e}')
    STATE.write_text(json.dumps(new,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    if messages:
        with HISTORY.open('a',newline='',encoding='utf-8-sig') as f:
            writer=csv.DictWriter(f,fieldnames=list(messages[0]));
            if f.tell()==0:writer.writeheader()
            writer.writerows(messages)
    print(f'Checked {len(selected)} / sent {len(messages)} / failures {len(failures)} / source {source}')
    if failures:
        print('Failures:', '; '.join(failures[:10]))
        if len(failures)==len(selected):raise RuntimeError('모든 종목 조회 실패')
if __name__=='__main__':main()
