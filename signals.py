"""Fear-RSI STOCK: advisory signals using completed Korean market bars."""
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo
import pandas as pd
import yfinance as yf

KST = ZoneInfo('Asia/Seoul')
WATCH_DEFAULT = {'005930':'삼성전자','000660':'SK하이닉스','035420':'NAVER','035720':'카카오','005380':'현대차','068270':'셀트리온','247540':'에코프로비엠','086520':'에코프로'}
# Market-wide scan uses a bounded, market-cap ranked universe, not every listed security.
FALLBACK = {
'005930':'삼성전자','000660':'SK하이닉스','035420':'NAVER','035720':'카카오','005380':'현대차','000270':'기아','068270':'셀트리온','105560':'KB금융','055550':'신한지주','012330':'현대모비스','207940':'삼성바이오로직스','006400':'삼성SDI','051910':'LG화학','373220':'LG에너지솔루션','005490':'POSCO홀딩스','028260':'삼성물산','003670':'포스코퓨처엠','034020':'두산에너빌리티','015760':'한국전력','009150':'삼성전기','017670':'SK텔레콤','066570':'LG전자','032830':'삼성생명','010130':'고려아연','086790':'하나금융지주','024110':'기업은행','267260':'HD현대일렉트릭','042700':'한미반도체','329180':'HD현대중공업','047050':'포스코인터내셔널','247540':'에코프로비엠','086520':'에코프로','196170':'알테오젠','028300':'HLB','058470':'리노공업','039030':'이오테크닉스','145020':'휴젤','214150':'클래시스','041510':'에스엠','035900':'JYP Ent.','122870':'와이지엔터테인먼트','293490':'카카오게임즈','263750':'펄어비스','112040':'위메이드','067160':'SOOP','078600':'대주전자재료','095340':'ISC','240810':'원익IPS','036930':'주성엔지니어링','403870':'HPSP'}

def now_kst(): return datetime.now(KST)
def suffix(code, market='KOSPI'): return f'{code}.KQ' if market == 'KOSDAQ' else f'{code}.KS'
def load_universe(limit=100):
    try:
        import FinanceDataReader as fdr
        listing = fdr.StockListing('KRX')
        cols = listing.columns
        codecol = next((x for x in ('Code','Symbol') if x in cols),None)
        namecol = next((x for x in ('Name','Company') if x in cols),None)
        marketcol = next((x for x in ('Market','MarketName') if x in cols),None)
        capcol = next((x for x in ('Marcap','MarketCap') if x in cols),None)
        if not codecol or not namecol or not marketcol or not capcol: raise ValueError('KRX 종목 목록 형식 변경')
        listing = listing[listing[marketcol].astype(str).str.upper().isin(['KOSPI','KOSDAQ'])].copy()
        listing[capcol] = pd.to_numeric(listing[capcol],errors='coerce')
        listing = listing.sort_values(capcol,ascending=False).head(limit)
        return [{'code':str(row[codecol]).zfill(6),'name':str(row[namecol]),'market':str(row[marketcol]).upper()} for _,row in listing.iterrows()], 'KRX 시가총액 상위'
    except Exception:
        return [{'code':c,'name':n,'market':'KOSDAQ' if c in {'247540','086520','196170','028300','058470','039030','145020','214150','041510','035900','122870','293490','263750','112040','067160','078600','095340','240810','036930','403870'} else 'KOSPI'} for c,n in list(FALLBACK.items())[:limit]], '기본 관심 종목 목록(종목 목록 조회 실패)'

def get_history(ticker, interval='1d', period='6mo'):
    raw = yf.Ticker(ticker).history(period=period, interval=interval, auto_adjust=True, raise_errors=False)
    if raw.empty: raise ValueError(f'{ticker} 가격 데이터 없음')
    if raw.index.tz is None: raise ValueError('가격 데이터 시간대 확인 불가')
    raw = raw.tz_convert(KST)
    return raw[['Open','High','Low','Close','Volume']].dropna(subset=['Close']).copy()

def completed_daily(df, now=None):
    now = now or now_kst()
    # Yahoo daily labels represent trading date, not 09:00 timestamp.
    return df.loc[(df.index.date < now.date()) | ((df.index.date == now.date()) & (now.time() >= time(15,35)))].copy()

def completed_hourly(df, now=None):
    now = now or now_kst()
    out=[]
    for idx,row in df.iterrows():
        local=idx.to_pydatetime()
        start=local.time()
        if not (time(9)<=start<time(15,30)): continue
        end = min(local+timedelta(hours=1), local.replace(hour=15,minute=30,second=0,microsecond=0))
        if end <= now: out.append(idx)
    return df.loc[out].copy()

def make_four_hour(hourly):
    # Korean session is 6.5 hours: 09:00–13:00 and 13:00–15:30.
    if hourly.empty: return hourly.copy()
    records=[]
    for date,day in hourly.groupby(hourly.index.date):
        for hour,minute,finish_h,finish_m in ((9,0,13,0),(13,0,15,30)):
            start=pd.Timestamp(datetime.combine(date,time(hour,minute)),tz=KST)
            finish=pd.Timestamp(datetime.combine(date,time(finish_h,finish_m)),tz=KST)
            chunk=day.loc[(day.index>=start)&(day.index<finish)]
            # Need the final 1h/30m candle in the block to ensure completion.
            required=finish-timedelta(hours=1) if finish_h==13 else finish-timedelta(minutes=30)
            if chunk.empty or chunk.index.max()<required: continue
            records.append((start,{'Open':chunk['Open'].iloc[0],'High':chunk['High'].max(),'Low':chunk['Low'].min(),'Close':chunk['Close'].iloc[-1],'Volume':chunk['Volume'].sum()}))
    if not records:return pd.DataFrame(columns=hourly.columns,index=pd.DatetimeIndex([],tz=KST))
    return pd.DataFrame([v for _,v in records],index=pd.DatetimeIndex([t for t,_ in records]))

def rsi(close,period=14):
    d=close.astype(float).diff(); gain=d.clip(lower=0);loss=-d.clip(upper=0)
    ag=gain.ewm(alpha=1/period,adjust=False,min_periods=period).mean()
    al=loss.ewm(alpha=1/period,adjust=False,min_periods=period).mean()
    val=100-100/(1+ag/al.replace(0,float('nan')))
    return val.mask((al==0)&(ag>0),100).mask((ag==0)&(al>0),0).mask((ag==0)&(al==0),50)

def market_mood():
    # Explicitly a proxy, not a Korean Fear & Greed index.
    kospi=completed_daily(get_history('^KS11','1d','3mo'))
    if len(kospi)<25: raise ValueError('코스피 지수 데이터 부족')
    krsi=float(rsi(kospi['Close']).iloc[-1]);vix=None
    try:
        vix_df=completed_daily(get_history('^VIX','1d','1mo'))
        vix=float(vix_df['Close'].iloc[-1])
    except Exception:pass
    fear=(krsi<=40) or (vix is not None and vix>=20)
    greed=(krsi>=65) and (vix is None or vix<=20)
    return {'kospi_rsi':round(krsi,1),'vix':round(vix,1) if vix is not None else None,'fear':fear,'greed':greed,'date':str(kospi.index[-1].date())}

def signal(df,mood):
    if len(df)<25: return {'direction':'데이터 부족','rsi':None,'price':None,'time':None}
    series=rsi(df['Close']);last=float(series.iloc[-1]);prev=float(series.iloc[-2]);price=float(df['Close'].iloc[-1]);stamp=df.index[-1].strftime('%Y-%m-%d %H:%M')
    direction='매수' if mood['fear'] and last<=40 and last>prev else ('매도' if mood['greed'] and last>=60 and last<prev else '없음')
    return {'direction':direction,'rsi':round(last,1),'price':price,'time':stamp}

def summarize(frames):
    a,b,c=(frames[k]['direction'] for k in ('1시간','4시간','1일'))
    if a==b and a in ('매수','매도'):return f'강한 {a}',f'1시간봉·4시간봉 동시 {a}'+(' · 일봉 일치' if c==a else '')
    active=[(k,v['direction']) for k,v in frames.items() if v['direction'] in ('매수','매도')]
    if len({v for _,v in active})>1:return '신호 엇갈림','시간봉 간 방향이 다름'
    if active:return f'{active[0][1]} 후보',' · '.join(f'{k} {v}' for k,v in active)
    return '신호 없음','매수·매도 조건 미충족'

def daily_summary(df,mood):
    df=completed_daily(df)
    if len(df)<35: raise ValueError('일봉 부족')
    last=float(df['Close'].iloc[-1]); high=float(df['High'].tail(30).max()); drop=(last/high-1)*100 if high else 0
    ma5=float(df['Close'].tail(5).mean());ma20=float(df['Close'].tail(20).mean())
    trend='상승' if ma5>ma20*1.005 else ('하락' if ma5<ma20*.995 else '보합')
    return {'drop30':round(drop,1),'trend':trend,'daily':signal(df,mood),'price':last,'time':df.index[-1].strftime('%Y-%m-%d')}

def analyze_stock(item,mood,need_intraday=True):
    ticker=suffix(item['code'],item['market']); daily=get_history(ticker,'1d','6mo');ds=daily_summary(daily,mood)
    frames={'1일':ds['daily']}
    if need_intraday:
        hourly=completed_hourly(get_history(ticker,'60m','60d'))
        four=make_four_hour(hourly)
        frames={'1시간':signal(hourly,mood),'4시간':signal(four,mood),'1일':ds['daily']}
        label,reason=summarize(frames)
    else:
        label='일봉 매수 후보' if ds['daily']['direction']=='매수' else ('일봉 매도 후보' if ds['daily']['direction']=='매도' else '신호 없음')
        reason='일봉 기준 1차 탐색 (강한 매수 판정 아님)'
    return {**item,'label':label,'reason':reason,'frames':frames,'drop30':ds['drop30'],'trend':ds['trend'],'price':ds['price'],'date':ds['time'],'url':f'https://finance.naver.com/item/main.naver?code={item["code"]}'}
