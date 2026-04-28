import streamlit as st
import pandas as pd
import yfinance as yf
import os
import json
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, date, timedelta
import pytz
import plotly.graph_objects as go
import numpy as np

# ──────────────────────────────────────────
# [1] 환경 설정 및 정밀 CSS (앱 모드 최적화)
# ──────────────────────────────────────────
KST = pytz.timezone('Asia/Seoul')
st.set_page_config(page_title="Master Commander", layout="wide", page_icon="🏹")

# 진짜 앱처럼 보이게 만드는 메타 태그 및 CSS (번역 방지 추가)
st.markdown("""
    <head>
        <meta name="google" content="notranslate">
        <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    </head>
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Pretendard:wght@400;600;700&display=swap');
    
    /* 전체 번역 방지 클래스 강제 적용 */
    html, body {
        -webkit-text-size-adjust: none;
        touch-action: manipulation;
    }
    </style>
    """, unsafe_allow_html=True)

# ──────────────────────────────────────────
# [2] 스타크 API 브릿지 로직 (구글 시트 연동)
# ──────────────────────────────────────────
BRIDGE_URL = "https://script.google.com/macros/s/AKfycbwDi_eLCw9O-_QfTA4SbRBV03oZnDa0uucCHNwrnXPMzyfB_NsXPliCqFRnULDv4ljj/exec"

def load_data():
    """브릿지를 통해 구글 시트 데이터를 가져옴"""
    try:
        res = requests.get(BRIDGE_URL, timeout=10)
        data = res.json()
        # 시트 데이터(리스트)를 딕셔너리로 변환
        p_dict = {"purchase_prices": {}}
        for i, row in enumerate(data):
            if i == 0: continue # 헤더 스킵
            ticker = row[0]
            if ticker in ["SCHD", "QQQM", "QLD", "TQQQ", "SGOV"]:
                p_dict[ticker] = float(row[1])
                p_dict["purchase_prices"][ticker] = float(row[2])
            elif ticker == "CASH": p_dict["CASH_USD"] = float(row[1])
            elif ticker == "REALIZED": p_dict["REALIZED_PROFIT_USD"] = float(row[1])
            elif ticker == "DIVIDEND": p_dict["ACCUMULATED_DIV_USD"] = float(row[1])
        return p_dict
    except:
        return {"SCHD":0, "QQQM":0, "QLD":0, "TQQQ":0, "SGOV":0, "CASH_USD":10000, "REALIZED_PROFIT_USD":0, "ACCUMULATED_DIV_USD":0, "purchase_prices":{}}

def save_data(new_p):
    """브릿지를 통해 데이터를 구글 시트에 전송"""
    rows = [["Ticker", "Quantity", "AvgCost", "ManualPrice", "RealizedProfit", "AccumulatedDiv", "Cash"]]
    for t in ["SCHD", "QQQM", "QLD", "TQQQ", "SGOV"]:
        rows.append([t, new_p[t], new_p["purchase_prices"].get(t,0), 0, 0, 0, 0])
    rows.append(["CASH", new_p.get("CASH_USD", 0), 0, 0, 0, 0, 0])
    rows.append(["REALIZED", new_p.get("REALIZED_PROFIT_USD", 0), 0, 0, 0, 0, 0])
    rows.append(["DIVIDEND", new_p.get("ACCUMULATED_DIV_USD", 0), 0, 0, 0, 0, 0])
    
    try:
        requests.post(BRIDGE_URL, data=json.dumps(rows), timeout=10)
        st.cache_data.clear()
        return True
    except:
        return False

# ──────────────────────────────────────────
# [3] 시장 데이터 및 분석
# ──────────────────────────────────────────

@st.cache_data(ttl=3600)
def get_big3_report():
    report = []
    try:
        for kw in ["미국 금리", "나스닥 실적", "지정학 리스크"]:
            url = f"https://news.google.com/rss/search?q={kw}&hl=ko&gl=KR&ceid=KR:ko"
            r = requests.get(url, timeout=5)
            root = ET.fromstring(r.content)
            item = root.find('.//item')
            if item is not None: report.append(item.find('title').text.split(' - ')[0])
    except: pass
    while len(report) < 3: report.append("데이터 수집 중입니다.")
    return report

@st.cache_data(ttl=30)
def fetch_market():
    tickers = {"QLD":"QLD", "TQQQ":"TQQQ", "SCHD":"SCHD", "QQQM":"QQQM", "SGOV":"SGOV", "USD/KRW":"USDKRW=X", "VIX":"^VIX", "VOO":"VOO"}
    res = {}
    for name, sym in tickers.items():
        try:
            t = yf.Ticker(sym)
            h = t.history(period="5d")
            res[name] = {"price": h['Close'].iloc[-1], "hist": t.history(period="1y") if name in ["QLD", "VOO"] else None}
        except: res[name] = {"price": 0}
    return res

# ──────────────────────────────────────────
# [4] 데이터 초기화
# ──────────────────────────────────────────

m = fetch_market()
p = load_data()
usdkrw = m.get('USD/KRW', {}).get('price', 1420)

h_q = m.get('QLD', {}).get('hist', pd.DataFrame())
curr_q = m.get('QLD', {}).get('price', 0)
if not h_q.empty:
    delta = h_q['Close'].diff()
    rsi = (100 - (100 / (1 + delta.where(lambda x:x>0, 0).rolling(14).mean() / (-delta.where(lambda x:x<0, 0)).rolling(14).mean()))).iloc[-1]
    ma200 = h_q['Close'].rolling(200).mean().iloc[-1]
    drop_from_peak = (curr_q / h_q['Close'].tail(20).max() - 1) * 100
else: rsi, ma200, drop_from_peak = 50, 0, 0

stock_val_usd = sum(p.get(t, 0) * m.get(t, {}).get("price", 0) for t in ["SCHD", "QQQM", "QLD", "TQQQ", "SGOV"])
total_assets_usd = stock_val_usd + p.get("CASH_USD", 0)
total_krw = total_assets_usd * usdkrw
total_purchase_usd = p.get("CASH_USD", 0)
for t in ["SCHD", "QQQM", "QLD", "TQQQ", "SGOV"]: total_purchase_usd += p.get(t, 0) * p.get("purchase_prices", {}).get(t, 0)
roi_pct = (total_assets_usd / total_purchase_usd - 1) * 100 if total_purchase_usd > 0 else 0

# ──────────────────────────────────────────
# [5] UI 구성 (탭 방식)
# ──────────────────────────────────────────

st.title("🏹 Master Commander v20.0 Cloud")
tabs = st.tabs(["📊 대시보드", "📡 빅3 리포트", "⚖️ 세금 & 수정"])

with tabs[0]:
    # 상단 카드
    c1, c2, c3, c4 = st.columns(4)
    with c1: st.markdown(f"""<div class="mpop-card"><div style="color:#64748B; font-size:12px;">총 평가자산</div><div style="font-size:24px; font-weight:bold;">{total_krw/10000:,.0f} 만원</div><div style="color:#94A3B8; font-size:12px;">${total_assets_usd:,.2f}</div></div>""", unsafe_allow_html=True)
    with c2: 
        tg = p.get("REALIZED_PROFIT_USD", 0) + p.get("ACCUMULATED_DIV_USD", 0)
        st.markdown(f"""<div class="mpop-card"><div style="color:#64748B; font-size:12px;">누적 수익</div><div style="font-size:20px; font-weight:bold; color:#EF4444;">${tg:,.1f}</div><div style="color:#718096; font-size:12px;">약 {tg*usdkrw/10000:,.0f}만원</div></div>""", unsafe_allow_html=True)
    with c3: st.markdown(f"""<div class="mpop-card"><div style="color:#64748B; font-size:12px;">총 투자 ROI</div><div style="font-size:24px; font-weight:bold; color:{'#EF4444' if roi_pct>=0 else '#3B82F6'};">{"▲" if roi_pct>=0 else "▼"} {abs(roi_pct):.2f}%</div></div>""", unsafe_allow_html=True)
    with c4:
        s_l, s_c = ("매수 금지", "#EF4444") if rsi > 70 else ("분할 매수", "#10B981") if rsi < 45 else ("관망 대기", "#3B82F6")
        st.markdown(f"""<div class="mpop-card" style="background-color:{s_c}; color:white;"><div style="font-size:20px; font-weight:bold;">{s_l}</div><div style="font-size:11px;">RSI {rsi:.1f} | 1억 달성 {total_krw/1000000:.1f}%</div></div>""", unsafe_allow_html=True)

    st.divider()
    # 잔고 표
    st.subheader("📋 실시간 보유잔고 상세 (Cloud Sync)")
    col_rat = [1, 1.2, 1.2, 1.2, 1, 1.2, 1.5]
    t_h = st.columns(col_rat)
    for col, l in zip(t_h, ["종목", "수량", "평단 ($)", "현재가 ($)", "수익률", "평가손익 ($)", "평가금액 ($)"]):
        col.markdown(f"<div class='table-header'>{l}</div>", unsafe_allow_html=True)

    for t in ["SCHD", "QQQM", "QLD", "TQQQ", "SGOV"]:
        cp = m.get(t, {}).get("price", 0)
        qty, avg = p.get(t, 0), p.get("purchase_prices", {}).get(t, 0)
        row = st.columns(col_rat)
        row[0].markdown(f"<div style='margin-top:15px;' class='stock-label'>{t}</div>", unsafe_allow_html=True)
        row[1].markdown(f"<div class='center-val'>{qty:.2f}</div>", unsafe_allow_html=True)
        row[2].markdown(f"<div class='center-val'>${avg:,.4f}</div>", unsafe_allow_html=True)
        row[3].markdown(f"<div class='center-val' style='font-weight:700;'>${cp:.4f}</div>", unsafe_allow_html=True)
        if qty > 0 and avg > 0:
            pct, amt, val = (cp/avg-1)*100, (cp-avg)*qty, cp*qty
            cls = "plus" if pct>=0 else "minus"
            row[4].markdown(f"<div class='{cls}' style='margin-top:15px;'>{abs(pct):.1f}%</div>", unsafe_allow_html=True)
            row[5].markdown(f"<div class='{cls}' style='margin-top:15px;'>${amt:,.2f}</div>", unsafe_allow_html=True)
            row[6].markdown(f"<div style='margin-top:15px; text-align:center; font-weight:700;'>${val:,.2f}</div>", unsafe_allow_html=True)
        else:
            for i in [4, 5, 6]: row[i].markdown("<div style='margin-top:15px; text-align:center; color:#CBD5E0;'>-</div>", unsafe_allow_html=True)

with tabs[1]:
    st.subheader("📊 오늘의 마켓 인텔리전스 : Big 3")
    big3 = get_big3_report()
    st.markdown(f"""<div class="report-card"><h3>📋 핵심 이슈 요약</h3><ul style="font-size:16px; line-height:2.2;"><li>🔥 <b>거시경제:</b> {big3[0]}</li><li>🏢 <b>기업실적:</b> {big3[1]}</li><li>🌍 <b>대외변수:</b> {big3[2]}</li></ul></div>""", unsafe_allow_html=True)

with tabs[2]:
    st.subheader("⚖️ 데이터 수정 및 세금 전략")
    real_krw = p.get("REALIZED_PROFIT_USD", 0) * usdkrw
    st.error(f"예상 양도소득세: **{max(0, real_krw - 2500000)*0.22/10000:,.1f} 만원**")
    
    st.divider()
    u_f = p.copy()
    for t in ["SCHD", "QQQM", "QLD", "TQQQ", "SGOV"]:
        st.markdown(f"**{t}**")
        cx1, cx2 = st.columns(2)
        u_f[t] = cx1.number_input(f"QTY {t}", value=float(p.get(t,0)), key=f"cl_q_{t}")
        u_f["purchase_prices"][t] = cx2.number_input(f"AVG {t}", value=float(p.get("purchase_prices", {}).get(t, 0)), key=f"cl_a_{t}", format="%.4f")
    
    cy1, cy2, cy3 = st.columns(3)
    u_f["CASH_USD"] = cy1.number_input("CASH ($)", value=float(p.get("CASH_USD", 0)), key="cl_cash")
    u_f["REALIZED_PROFIT_USD"] = cy2.number_input("REALIZED ($)", value=float(p.get("REALIZED_PROFIT_USD", 0)), key="cl_realized")
    u_f["ACCUMULATED_DIV_USD"] = cy3.number_input("DIVIDEND ($)", value=float(p.get("ACCUMULATED_DIV_USD", 0)), key="cl_div")
    
    if st.button("💾 구글 시트에 최종 저장", type="primary", use_container_width=True):
        if save_data(u_f): st.success("클라우드 동기화 완료!"); st.rerun()
        else: st.error("동기화 실패. 브릿지 URL을 확인하세요.")

st.caption(f"Master Commander v20.0 | Cloud Sync Mode | 갱신: {datetime.now(KST).strftime('%H:%M:%S')}")
