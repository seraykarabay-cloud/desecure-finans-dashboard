import base64
import hashlib
import hmac
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

APP_TITLE = "DESecure Finansal Kontrol Paneli"
DATA_FILE = Path("veriler.csv")
LOGO_FILE = Path("logo.png")
COLUMNS = ["Tarih", "Açıklama", "İşlem Türü", "Ödeme Tipi", "Tutar", "Ödeme Kırılımı", "Fatura Dönemi"]

MONTHS = {
    1: "Ocak", 2: "Şubat", 3: "Mart", 4: "Nisan", 5: "Mayıs", 6: "Haziran",
    7: "Temmuz", 8: "Ağustos", 9: "Eylül", 10: "Ekim", 11: "Kasım", 12: "Aralık"
}
MONTH_ORDER = list(MONTHS.values())

PAYMENT_BREAKDOWN_RULES = {
    "Maaş": ["maaş", "maas"],
    "Vergi": ["vergi", "kdv", "muhtasar", "damga vergisi", "damga"],
    "İş Avansı": ["iş avansı", "is avansi"],
    "Avans": ["avans"],
    "İcra": ["icra"],
    "BES": ["bes"],
    "Abonelik": ["telekom", "turkcell", "ttnet", "ttmobil", "abonelik", "esernet", "deski", "maski", "doğalgaz", "dogalgaz"],
    "Kira": ["kira"],
    "Aidat": ["aidat"],
    "HGS": ["hgs"],
    "Nakit Çekilen": ["nakit çekilen", "nakit cekilen", "nakit cekim"],
    "Cenk Çavuşoğlu": ["cenk çavuşoğlu", "cenk cavusoglu"],
    "Banka Masraf / Komisyon": ["eft", "havale", "masraf", "mektup komisyonu", "komisyon", "mektup"],
}

DEFAULT_USERS = {
    "merve bozkurt": hashlib.sha256("1234".encode()).hexdigest(),
    "firdevs ulutas": hashlib.sha256("4321".encode()).hexdigest(),
    "seray karabay": hashlib.sha256("3210".encode()).hexdigest(),
}

st.set_page_config(page_title=APP_TITLE, page_icon="🛰️", layout="wide")

def load_users() -> dict[str, str]:
    try:
        users = dict(st.secrets.get("users", {}))
        return {k.lower().strip(): v for k, v in users.items()} or DEFAULT_USERS
    except Exception:
        return DEFAULT_USERS

def check_password(username: str, password: str) -> bool:
    stored_hash = load_users().get(username.lower().strip())
    if not stored_hash:
        return False
    given_hash = hashlib.sha256(password.encode()).hexdigest()
    return hmac.compare_digest(stored_hash, given_hash)

def require_login() -> None:
    if st.session_state.get("logged_in"):
        return

    render_css()
    st.markdown('<div style="height: 60px;"></div>', unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 1.5, 1])
    with col2:
        st.markdown("""
        <div class="hero" style="text-align: center; padding: 40px 20px;">
            <span style="font-size: 50px;">🔐</span>
            <h2 style="margin-top:10px; color:#fff !important;">Finans Dashboard Giriş</h2>
            <p style="color:#94a3b8;">Lütfen sistem yöneticinizden aldığınız bilgilerle giriş yapın.</p>
        </div>
        """, unsafe_allow_html=True)
        
        with st.form("login_form"):
            username = st.text_input("Kullanıcı Adı")
            password = st.text_input("Şifre", type="password")
            submitted = st.form_submit_button("Sisteme Giriş Yap", use_container_width=True)

        if submitted:
            if check_password(username, password):
                st.session_state.logged_in = True
                st.session_state.username = username.lower().strip()
                st.rerun()
            st.error("Kullanıcı adı veya şifre hatalı.")
    st.stop()

def money(value: float) -> str:
    return f"{value:,.0f} ₺".replace(",", ".")

def get_base64_image(path: Path) -> str:
    if path.exists():
        return base64.b64encode(path.read_bytes()).decode()
    return ""

def clean_amount(value) -> float:
    if pd.isna(value):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).replace("TL", "").replace("₺", "").replace(" ", "")
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".")
    elif "," in text:
        text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return 0.0

def detect_breakdown(description: str) -> str:
    text = str(description).lower().strip()
    for label, keywords in PAYMENT_BREAKDOWN_RULES.items():
        if any(keyword in text for keyword in keywords):
            return label
    return "Cari"

def ensure_data_file() -> None:
    if not DATA_FILE.exists():
        pd.DataFrame(columns=COLUMNS).to_csv(DATA_FILE, index=False)

@st.cache_data(show_spinner=False)
def read_data(path: str, mtime: float) -> pd.DataFrame:
    df = pd.read_csv(path)
    for col in COLUMNS:
        if col not in df.columns:
            df[col] = ""
    df = df[COLUMNS]
    df["Tutar"] = pd.to_numeric(df["Tutar"].apply(clean_amount), errors="coerce").fillna(0)
    df["Tarih_dt"] = pd.to_datetime(df["Tarih"], format="%d-%m-%Y", errors="coerce")
    df["İşlem Türü"] = df["İşlem Türü"].replace("", "Yapılan Ödeme").fillna("Yapılan Ödeme")
    df.loc[df["Fatura Dönemi"].astype(str).str.strip() == "", "Fatura Dönemi"] = df["Tarih_dt"].dt.month.map(MONTHS)
    df["Fatura Dönemi"] = df["Fatura Dönemi"].fillna(df["Tarih_dt"].dt.month.map(MONTHS))
    return df.drop_duplicates(subset=["Tarih", "Açıklama", "İşlem Türü", "Ödeme Tipi", "Tutar"])

def save_data(df: pd.DataFrame) -> None:
    df.drop(columns=["Tarih_dt"], errors="ignore")[COLUMNS].to_csv(DATA_FILE, index=False)
    read_data.clear()

def parse_incoming_payments(uploaded_file) -> pd.DataFrame:
    try:
        raw = pd.read_excel(uploaded_file, header=None)
    except Exception as exc:
        st.error(f"Excel okunurken hata oluştu: {exc}")
        return pd.DataFrame(columns=COLUMNS)

    records, active_date = [], None
    for _, row in raw.iterrows():
        first_cell = row.iloc[0]
        amount_raw = row.iloc[1] if len(row) > 1 else None
        if pd.isna(first_cell):
            continue

        text = str(first_cell).strip()
        parsed_date = pd.to_datetime(text.split("-")[0].strip(), format="%d.%m.%Y", errors="coerce")

        if not pd.isna(parsed_date):
            active_date = parsed_date
            continue
        if text.upper() == "TOPLAM":
            continue
        if active_date is not None and not pd.isna(amount_raw):
            records.append({
                "Tarih": active_date.strftime("%d-%m-%Y"),
                "Açıklama": text,
                "İşlem Türü": "Gelen Bedel",
                "Ödeme Tipi": "Havale",
                "Tutar": clean_amount(amount_raw),
                "Ödeme Kırılımı": "",
                "Fatura Dönemi": MONTHS[active_date.month],
            })
    return pd.DataFrame(records, columns=COLUMNS)

def parse_outgoing_payments(uploaded_file) -> pd.DataFrame:
    try:
        raw = pd.read_excel(uploaded_file)
    except Exception as exc:
        st.error(f"Excel dosyası okunurken hata oluştu: {exc}")
        return pd.DataFrame(columns=COLUMNS)

    amount_col = next((c for c in raw.columns if "tutar" in str(c).lower()), raw.columns[2] if len(raw.columns) >= 3 else None)
    description_col = raw.columns[3] if len(raw.columns) >= 4 else raw.columns[0]
    today = pd.Timestamp.today()

    records = []
    for _, row in raw.iterrows():
        description = str(row.get(description_col, "")).strip()
        if not description or description.lower() in {"aciklama", "açıklama", "toplam", "general total"}:
            continue

        amount = clean_amount(row.get(amount_col, 0))
        if amount <= 0:
            continue

        records.append({
            "Tarih": today.strftime("%d-%m-%Y"),
            "Açıklama": description,
            "İşlem Türü": "Yapılan Ödeme",
            "Ödeme Tipi": "Havale",
            "Tutar": amount,
            "Ödeme Kırılımı": detect_breakdown(description),
            "Fatura Dönemi": MONTHS[today.month],
        })
    return pd.DataFrame(records, columns=COLUMNS)

def render_css() -> None:
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif !important;
    }

    .stApp {
        background:
            radial-gradient(circle at top left, rgba(236,72,153,.12), transparent 35%),
            radial-gradient(circle at bottom right, rgba(34,211,238,.10), transparent 35%),
            linear-gradient(135deg, #0b1329 0%, #080d1a 50%, #030712 100%);
    }

    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #091124, #030712) !important;
        border-right: 1px solid rgba(255, 255, 255, 0.05) !important;
    }

    .hero {
        background: linear-gradient(135deg, rgba(17, 24, 39, 0.85), rgba(31, 41, 55, 0.65));
        border: 1px solid rgba(34, 211, 238, 0.25);
        border-radius: 20px;
        padding: 32px;
        margin-bottom: 28px;
        box-shadow: 0 10px 30px rgba(0, 0, 0, 0.25), 0 0 40px rgba(34, 211, 238, 0.05);
        backdrop-filter: blur(10px);
    }

    .hero h1 {
        color: #ffffff;
        font-size: 38px;
        margin: 0;
        font-weight: 800;
        letter-spacing: -0.02em;
    }

    .metric-card {
        background: linear-gradient(145deg, rgba(17, 24, 39, 0.9), rgba(15, 23, 42, 0.6));
        border: 1px solid rgba(255, 255, 255, 0.06);
        border-radius: 16px;
        padding: 24px;
        min-height: 140px;
        box-shadow: 0 8px 24px rgba(0, 0, 0, 0.2);
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        position: relative;
        overflow: hidden;
    }
    
    .metric-card:hover {
        transform: translateY(-4px);
        border-color: rgba(34, 211, 238, 0.4);
        box-shadow: 0 12px 30px rgba(34, 211, 238, 0.12);
    }

    .metric-card::before {
        content: '';
        position: absolute;
        top: 0; left: 0; width: 4px; height: 100%;
        background: linear-gradient(to bottom, #22d3ee, #ec4899);
    }

    .metric-title {
        color: #94a3b8;
        font-size: 13px;
        text-transform: uppercase;
        font-weight: 700;
        letter-spacing: .06em;
    }

    .metric-value {
        color: #ffffff;
        font-size: 32px;
        font-weight: 800;
        margin-top: 12px;
        letter-spacing: -0.01em;
    }

    .stTabs [data-baseweb="tab"] {
        color: #94a3b8 !important;
        font-weight: 600 !important;
        border-bottom: 2px solid transparent !important;
        padding: 10px 16px !important;
    }

    .stTabs [data-baseweb="tab"][aria-selected="true"] {
        color: #22d3ee !important;
        border-bottom-color: #22d3ee !important;
    }

    h1, h2, h3, h4 {
        color: #f1f5f9 !important;
        font-weight: 700 !important;
    }
    </style>
    """, unsafe_allow_html=True)


def metric_card(title: str, value: float, note: str) -> None:
    st.markdown(
        f"""<div class="metric-card">
            <div class="metric-title">{title}</div>
            <div class="metric-value">{money(value)}</div>
            <div style="color:#64748b; font-size:12px; margin-top:10px; font-weight:500;">💡 {note}</div>
        </div>""",
        unsafe_allow_html=True,
    )


def add_record_form(df: pd.DataFrame) -> None:
    st.sidebar.markdown('<div style="margin-top:20px;"></div>', unsafe_allow_html=True)
    st.sidebar.header("➕ Yeni Kayıt Ekle")
    with st.sidebar.form("new_record", clear_on_submit=True):
        date = st.date_input("İşlem Tarihi")
        transaction_type = st.selectbox("İşlem Türü", ["Yapılan Ödeme", "Kesilen Fatura", "Gelen Bedel"])
        description = st.text_input("Açıklama / Firma Adı")
        amount = st.number_input("Tutar (₺)", min_value=0.0, step=500.0)

        if transaction_type == "Yapılan Ödeme":
            payment_type = st.selectbox("Ödeme Tipi", ["Havale", "Nakit", "Kart"])
            breakdown = detect_breakdown(description)
            invoice_period = MONTHS[date.month]
        elif transaction_type == "Kesilen Fatura":
            payment_type = "Fatura (Bağımsız)"
            breakdown = ""
            invoice_period = st.selectbox("Fatura Dönemi", MONTH_ORDER, index=date.month - 1)
        else:
            payment_type = st.selectbox("Ödeme Tipi", ["Havale", "Nakit", "Kart"])
            breakdown = ""
            invoice_period = MONTHS[date.month]

        st.markdown('<div style="height: 10px;"></div>', unsafe_allow_html=True)
        if st.form_submit_button("Kaydı Güvenle Ekle", use_container_width=True):
            if not description.strip() or amount <= 0:
                st.warning("Lütfen açıklama girin ve tutarı sıfırdan büyük yazın.")
                return

            new_row = pd.DataFrame([{
                "Tarih": date.strftime("%d-%m-%Y"),
                "Açıklama": description.strip(),
                "İşlem Türü": transaction_type,
                "Ödeme Tipi": payment_type,
                "Tutar": amount,
                "Ödeme Kırılımı": breakdown,
                "Fatura Dönemi": invoice_period,
            }])
            save_data(pd.concat([df.drop(columns=["Tarih_dt"], errors="ignore"), new_row], ignore_index=True))
            st.success("Kayıt başarıyla işlendi.")
            st.rerun()


def make_bar(x, y, name=None):
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=x, y=y, name=name,
        marker=dict(
            color='#22d3ee',
            line=dict(color='rgba(34,211,238,0.6)', width=1)
        ),
        hovertemplate='%{x}: <b>%{y:,.0f} ₺</b><extra></extra>'
    ))
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", height=260,
        margin=dict(l=10, r=10, t=15, b=10),
        font=dict(color="#94a3b8", family="Inter"), 
        xaxis=dict(showgrid=False, tickfont=dict(size=11)),
        yaxis=dict(gridcolor="rgba(255,255,255,.05)", tickfont=dict(size=11))
    )
    return fig


def main() -> None:
    require_login()
    ensure_data_file()

    df = read_data(str(DATA_FILE), DATA_FILE.stat().st_mtime)
    today = pd.Timestamp.today().normalize()
    month_start = today.replace(day=1)
    year_start = today.replace(month=1, day=1)

    render_css()
    logo = get_base64_image(LOGO_FILE)
    logo_html = f'<img src="data:image/png;base64,{logo}" style="height:48px; margin-bottom:12px;">' if logo else ""
    
    st.markdown(f"""
    <div class="hero">
        {logo_html}
        <h1>🛰️ {APP_TITLE}</h1>
        <p style="margin-bottom:0; color:#94a3b8; font-size:14px; font-weight: 500; margin-top:8px;">
            Teknik finans izleme ekranı | Gelen bedeller, yapılan ödemeler, nakit akışı ve fatura analizi
        </p>
    </div>""", unsafe_allow_html=True)

    st.sidebar.header("📅 Tarih Filtresi")
    start_date = pd.Timestamp(st.sidebar.date_input("Başlangıç", value=month_start.date()))
    end_date = pd.Timestamp(st.sidebar.date_input("Bitiş", value=today.date()))
    add_record_form(df)

    outgoing = df[df["İşlem Türü"] == "Yapılan Ödeme"].copy()
    incoming_all = df[df["İşlem Türü"] == "Gelen Bedel"].copy()
    invoices = df[df["İşlem Türü"] == "Kesilen Fatura"].copy()
    outgoing["Ödeme Analiz Kırılımı"] = outgoing["Açıklama"].apply(detect_breakdown)

    special_pattern = r"Cenk Çavuşoğlu|FX|DVZ|Bozum"
    special_mask = incoming_all["Açıklama"].astype(str).str.contains(special_pattern, case=False, na=False)
    incoming = incoming_all[~special_mask].copy()

    selected_incoming = incoming[(incoming["Tarih_dt"] >= start_date) & (incoming["Tarih_dt"] <= end_date)]
    selected_invoices = invoices[(invoices["Tarih_dt"] >= start_date) & (invoices["Tarih_dt"] <= end_date)]
    selected_outgoing = outgoing[(outgoing["Tarih_dt"] >= start_date) & (outgoing["Tarih_dt"] <= end_date)]

    # Güvenli Dinamik Metrik Kartları Yapısı
    c1, c2, c3, c4 = st.columns(4)
    with c1: 
        metric_card("Seçili Dönem Fatura", selected_invoices["Tutar"].sum(), "Toplam alacak hedefi")
    with c2: 
        metric_card("Seçili Dönem Tahsilat", selected_incoming["Tutar"].sum(), "Özel kayıtlar filtrelenmiştir")
    with c3: 
        metric_card("Seçili Dönem Gider", selected_outgoing["Tutar"].sum(), "Yapılan kurum dışı ödemeler")
    with c4: 
        yillik_tahsilat = incoming[(incoming["Tarih_dt"] >= year_start) & (incoming["Tarih_dt"] <= today)]["Tutar"].sum()
        metric_card("Yıllık Akümüle Tahsilat", yillik_tahsilat, "1 Ocak'tan itibaren net giriş")

    st.markdown('<div style="height: 25px;"></div>', unsafe_allow_html=True)

    # Grafikler Alanı
    g1, g2 = st.columns(2)
    with g1:
        st.markdown("### 📈 Aylık Tahsilat Dağılımı")
        st.markdown('<div style="height: 10px;"></div>', unsafe_allow_html=True)
        monthly_incoming = incoming.groupby("Fatura Dönemi")["Tutar"].sum().reindex(MONTH_ORDER, fill_value=0)
        active_months = [m for m in MONTH_ORDER if monthly_incoming[m] > 0] or [MONTHS[today.month]]
        st.plotly_chart(make_bar(active_months, [monthly_incoming[m] for m in active_months]), use_container_width=True)
    with g2:
        st.markdown("### 💸 Gider Dağılım Kırılımı")
        st.markdown('<div style="height: 10px;"></div>', unsafe_allow_html=True)
        breakdown = selected_outgoing.groupby("Ödeme Analiz Kırılımı")["Tutar"].sum().sort_values(ascending=False)
        if breakdown.empty:
            st.info("Seçili tarih aralığında yansıyacak bir gider kaydı bulunamadı.")
        else:
            fig = go.Figure(data=[go.Pie(
                labels=breakdown.index, 
                values=breakdown.values, 
                hole=.55,
                marker=dict(colors=['#22d3ee', '#ec4899', '#a855f7', '#3b82f6', '#10b981', '#f59e0b']),
                textinfo='percent+label'
            )])
            fig.update_layout(
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", height=260, 
                margin=dict(l=10, r=10, t=10, b=10),
                font=dict(color="#94a3b8", family="Inter"),
                showlegend=False
            )
            st.plotly_chart(fig, use_container_width=True)

    st.markdown('<div style="height: 20px;"></div>', unsafe_allow_html=True)
    st.divider()
    
    # Performans Tablosu Alanı
    st.markdown("### 📊 Fatura / Tahsilat Karşılaştırma Performansı")
    invoice_group = invoices.groupby("Fatura Dönemi")["Tutar"].sum().reindex(MONTH_ORDER, fill_value=0)
    incoming_group = incoming.groupby("Fatura Dönemi")["Tutar"].sum().reindex(MONTH_ORDER, fill_value=0)
    comparison = []
    for month in MONTH_ORDER:
        invoice_total, incoming_total = invoice_group[month], incoming_group[month]
        if invoice_total > 0 or incoming_total > 0:
            rate = incoming_total / invoice_total * 100 if invoice_total else 100
            comparison.append({
                "Dönem": month,
                "Kesilen Fatura": money(invoice_total),
                "Tahsilat": money(incoming_total),
                "Kalan / Fark": money(invoice_total - incoming_total),
                "Tahsilat Oranı": f"% {rate:.1f}",
            })
    st.dataframe(pd.DataFrame(comparison), use_container_width=True, hide_index=True)

    st.markdown('<div style="height: 20px;"></div>', unsafe_allow_html=True)

    # Detay Sekmeleri
    tabs = st.tabs(["📋 Tüm Veri Seti (Düzenlenebilir)", "💸 Yapılan Ödemeler", "💰 Gelen Bedeller", "🧾 Faturalar", "📤 Veri Aktarım Alanı"])
    with tabs[0]:
        st.caption("💡 Tablo üzerinde doğrudan değişiklik yapabilir, satır ekleyip silebilirsiniz. İşlem bitince aşağıdaki kaydet butonuna basın.")
        edited = st.data_editor(df.drop(columns=["Tarih_dt"], errors="ignore"), use_container_width=True, height=380, num_rows="dynamic", hide_index=True)
        if st.button("💾 Tablo Değişikliklerini Veritabanına Yaz", type="primary"):
            save_data(edited)
            st.success("Tüm değişiklikler başarıyla yerel CSV dosyasına kaydedildi.")
            st.rerun()
    with tabs[1]:
        st.dataframe(outgoing.drop(columns=["Tarih_dt"], errors="ignore"), use_container_width=True, height=380, hide_index=True)
    with tabs[2]:
        st.caption("ℹ️ Bilgi: Cenk Çavuşoğlu ve FX/DVZ/Bozum kayıtları filtrelenmiş net listeyi görmektesiniz.")
        st.dataframe(incoming.drop(columns=["Tarih_dt"], errors="ignore"), use_container_width=True, height=380, hide_index=True)
    with tabs[3]:
        st.dataframe(invoices.drop(columns=["Tarih_dt"], errors="ignore"), use_container_width=True, height=380, hide_index=True)
    with tabs[4]:
        st.markdown("#### 📂 Toplu Dosya Entegrasyonu")
        c_up1, c_up2 = st.columns([1, 2])
        with c_up1:
            upload_type = st.selectbox("Yüklenecek Kaynak Tipi", ["Yapılan Ödemeler", "Gelen Bedeller", "CSV Hazır Veri"])
        with c_up2:
            uploaded = st.file_uploader("Dosyanızı buraya sürükleyin veya seçin", type=["xlsx", "csv"])
            
        if uploaded:
            if upload_type == "CSV Hazır Veri":
                uploaded_df = pd.read_csv(uploaded)
            elif upload_type == "Yapılan Ödemeler":
                uploaded_df = parse_outgoing_payments(uploaded)
            else:
                uploaded_df = parse_incoming_payments(uploaded)

            st.success(f"Dönüştürme Başarılı! {len(uploaded_df)} yeni kayıt saptandı. Önizleme aşağıdadır:")
            st.dataframe(uploaded_df.head(15), use_container_width=True, hide_index=True)
            if st.button("⚡ Önizlenen Verileri Ana Sisteme Entegre Et", type="secondary"):
                save_data(pd.concat([df.drop(columns=["Tarih_dt"], errors="ignore"), uploaded_df], ignore_index=True))
                st.success("Tüm yeni kayıtlar ana dosyaya eklenmiştir.")
                st.rerun()

    st.markdown('<div style="height: 10px;"></div>', unsafe_allow_html=True)
    st.divider()
    
    export_file = "finans_raporu.xlsx"
    df.drop(columns=["Tarih_dt"], errors="ignore").to_excel(export_file, index=False)
    with open(export_file, "rb") as file:
        st.download_button(
            label="📥 Güncel Finans Raporunu Excel Olarak İndir",
            data=file,
            file_name=export_file,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )

if __name__ == "__main__":
    main()
