import streamlit as st
from signals import WATCH_DEFAULT, load_universe, market_mood, analyze_stock
st.set_page_config(page_title='Fear-RSI STOCK',page_icon='📊',layout='wide')
st.title('📊 Fear-RSI STOCK')
st.caption('한국 주식 매수·매도 참고 신호 | 자동 주문 없음 | 확정봉 기준')
@st.cache_data(ttl=3600,show_spinner=False)
def universe(n):return load_universe(n)
@st.cache_data(ttl=900,show_spinner=False)
def mood_cached():return market_mood()
@st.cache_data(ttl=1200,show_spinner=False)
def stock_cached(code,name,market,detail,mood_tuple):
    mood=dict(mood_tuple)
    return analyze_stock({'code':code,'name':name,'market':market},mood,detail)
with st.sidebar:
    limit=st.slider('자동 탐색 대상 상위 종목 수',30,200,80,10)
    watch=st.text_input('관심 종목 코드 (쉼표 구분)','005930,000660,035420,247540')
    if st.button('🔄 새로고침'):
        st.cache_data.clear();st.rerun()
    st.caption('시장 심리: 코스피 RSI 및 VIX(미국 변동성 지표)를 참고하는 대체 지표입니다. 한국 공포탐욕지수 자체가 아닙니다.')
    st.caption('자동 탐색은 시가총액 상위 일부 종목의 일봉 1차 탐색입니다. 코스피·코스닥 전체 종목 전수조사는 아닙니다.')
try:mood=mood_cached()
except Exception as e:st.error(f'시장 지표 조회 실패: {e}');st.stop()
a,b,c=st.columns(3)
a.metric('코스피 RSI(14)',mood['kospi_rsi']);b.metric('VIX',mood['vix'] if mood['vix'] is not None else '조회 불가');c.metric('시장 상태','공포' if mood['fear'] else ('탐욕' if mood['greed'] else '중립'))
st.caption(f"시장 기준 데이터: {mood['date']} | 매수: 시장 공포 + RSI ≤40에서 반등 | 매도: 시장 탐욕 + RSI ≥60에서 둔화")
items,source=universe(limit)
bycode={x['code']:x for x in items}
for code,name in WATCH_DEFAULT.items():
    if code not in bycode:
        bycode[code]={'code':code,'name':name,'market':'KOSDAQ' if code in ('247540','086520') else 'KOSPI'}
mt=tuple(mood.items())
st.subheader('⭐ 관심 종목 (1시간·4시간·일봉)')
for code in dict.fromkeys(x.strip().zfill(6) for x in watch.split(',') if x.strip()):
    if not (len(code)==6 and code.isdigit()):st.warning(f'잘못된 종목 코드: {code}');continue
    item=bycode.get(code,{'code':code,'name':code,'market':'KOSPI'})
    try:r=stock_cached(item['code'],item['name'],item['market'],True,mt)
    except Exception as e:st.warning(f'{code} 데이터 확인 불가: {e}');continue
    with st.container(border=True):
        st.markdown(f"**{r['name']} ({code}) — {r['label']}**")
        st.write(f"{r['reason']} | 30거래일 고점 대비 {r['drop30']:+.1f}% | 일봉 추세 {r['trend']}")
        cols=st.columns(3)
        for col,(frame,info) in zip(cols,r['frames'].items()):
            with col:st.metric(frame,info['direction'],f"RSI {info['rsi']}" if info['rsi'] is not None else '자료 부족');st.caption(info['time'] or '미확인')
        st.link_button('종목 차트 보기',r['url'])
st.subheader('🔎 코스피·코스닥 매수 후보 자동 탐색')
st.caption(f'{source} {len(items)}개 대상 · 일봉 1차 스캔 · 상세 1시간/4시간 검증은 관심 종목에서 확인')
if st.button('일봉 매수 후보 탐색 실행',type='primary'):
    found=[];errors=0
    progress=st.progress(0)
    for i,item in enumerate(items):
        try:
            r=stock_cached(item['code'],item['name'],item['market'],False,mt)
            if '매수' in r['label']:found.append(r)
        except Exception:errors+=1
        progress.progress((i+1)/len(items))
    if found:
        st.dataframe([{'종목':r['name'],'코드':r['code'],'시장':r['market'],'일봉 신호':r['label'],'30일 고점 대비':f"{r['drop30']:+.1f}%",'일봉 추세':r['trend'],'종가':f"{r['price']:,.0f}"} for r in found],hide_index=True,use_container_width=True)
    else:st.info('이번 탐색에서 일봉 매수 후보를 찾지 못했습니다.')
    st.caption(f'검색 완료 {len(items)}개 중 조회 실패 {errors}개. 조회 실패 종목은 신호 없음으로 판단하지 않습니다.')
st.info('주식 데이터는 제공처 사정에 따라 지연·누락될 수 있습니다. 4시간봉은 한국 정규장을 09~13시/13~15:30으로 나눈 사용자 정의 봉입니다. 시장 지표는 투자 판단 참고용입니다.')
