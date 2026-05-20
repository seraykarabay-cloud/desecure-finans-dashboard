
import base64
import hashlib
import hmac
import os
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import plotly.graph_objects as go

APP_TITLE = "Desecure Finans Dashboard"
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
    # Demo amaçlıdır. Canlı kullanımda bu bilgileri .streamlit/secrets.toml içine taşıyın.
    # [users]
    # "merve bozkurt" = "sha256_hash"
    "merve bozkurt": hashlib.sha256("1234".encode()).hexdigest(),
    "firdevs ulutas": hashlib.sha256("4321".encode()).hexdigest(),
    "seray karabay": hashlib.sha256("3210".encode()).hexdigest(),
}


st.set_page_config(page_title=APP_TITLE, page_icon="💰", layout="wide")


def load_users() -> dict[str, str]:
    """Kullanıcıları secrets.toml içinden okur; yoksa demo kullanıcıları kullanır."""
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

    st.title("🔐 Finans Dashboard Giriş")
    with st.form("login_form"):
        username = st.text_input("Kullanıcı adı")
        password = st.text_input("Şifre", type="password")
        submitted = st.form_submit_button("Giriş Yap", use_container_width=True)

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
    html, body, [class*="css"] { font-family: 'Inter', sans-serif !important; }
    .stApp { background: radial-gradient(circle at top left, #172554 0%, #020617 44%, #020617 100%); }
    .hero { background: linear-gradient(135deg, rgba(59,130,246,.16), rgba(15,23,42,.82), rgba(168,85,247,.16));
            border: 1px solid rgba(255,255,255,.10); border-radius: 28px; padding: 34px 42px; margin-bottom: 26px;
            box-shadow: 0 24px 80px rgba(0,0,0,.38); }
    .hero h1 { color: #f8fafc; font-size: 42px; margin: 0; font-weight: 800; letter-spacing: -.04em; }
    .hero p { color: #cbd5e1; margin: 8px 0 0; }
    .metric-card { background: rgba(15,23,42,.72); border: 1px solid rgba(255,255,255,.08); border-radius: 22px;
                   padding: 20px 22px; box-shadow: 0 16px 48px rgba(0,0,0,.28); }
    .metric-title { color:#94a3b8; font-size:12px; text-transform:uppercase; font-weight:700; letter-spacing:.08em; }
    .metric-value { color:#f8fafc; font-size:28px; font-weight:800; margin-top:8px; }
    .soft-card { background: rgba(15,23,42,.62); border: 1px solid rgba(255,255,255,.08); border-radius: 22px; padding: 18px; }
    h1, h2, h3 { color:#e2e8f0 !important; }
    </style>
    """, unsafe_allow_html=True)


def metric_card(title: str, value: float, note: str) -> None:
    st.markdown(
        f"""<div class="metric-card">
            <div class="metric-title">{title}</div>
            <div class="metric-value">{money(value)}</div>
            <div style="color:#93c5fd;font-size:12px;margin-top:6px">{note}</div>
        </div>""",
        unsafe_allow_html=True,
    )


def add_record_form(df: pd.DataFrame) -> None:
    st.sidebar.header("➕ Yeni Kayıt")
    with st.sidebar.form("new_record", clear_on_submit=True):
        date = st.date_input("Tarih")
        transaction_type = st.selectbox("İşlem Türü", ["Yapılan Ödeme", "Kesilen Fatura", "Gelen Bedel"])
        description = st.text_input("Açıklama")
        amount = st.number_input("Tutar", min_value=0.0, step=100.0)

        if transaction_type == "Yapılan Ödeme":
            payment_type = st.selectbox("Ödeme Tipi", ["Nakit", "Havale", "Kart"])
            breakdown = detect_breakdown(description)
            invoice_period = MONTHS[date.month]
        elif transaction_type == "Kesilen Fatura":
            payment_type = "Fatura (Bağımsız)"
            breakdown = ""
            invoice_period = st.selectbox("Fatura Dönemi", MONTH_ORDER, index=date.month - 1)
        else:
            payment_type = st.selectbox("Ödeme Tipi", ["Nakit", "Havale", "Kart"])
            breakdown = ""
            invoice_period = MONTHS[date.month]

        if st.form_submit_button("Kaydet", use_container_width=True):
            if not description.strip() or amount <= 0:
                st.warning("Açıklama ve tutar zorunludur.")
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
            st.success("Kayıt eklendi.")
            st.rerun()


def make_bar(x, y, name=None):
    fig = go.Figure()
    fig.add_trace(go.Bar(x=x, y=y, name=name))
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", height=240,
        margin=dict(l=12, r=12, t=18, b=12),
        font=dict(color="#cbd5e1"), xaxis=dict(showgrid=False),
        yaxis=dict(gridcolor="rgba(255,255,255,.08)")
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
    logo_html = f'<img src="data:image/png;base64,{logo}" style="height:42px;margin-bottom:10px">' if logo else ""
    st.markdown(f"""<div class="hero">{logo_html}<h1>{APP_TITLE}</h1>
                    <p>Modern finans takip · tahsilat performansı · ödeme kırılımı · Excel aktarımı</p></div>""",
                unsafe_allow_html=True)

    st.sidebar.header("📅 Dönem Seçimi")
    start_date = pd.Timestamp(st.sidebar.date_input("Başlangıç Tarihi", value=month_start.date()))
    end_date = pd.Timestamp(st.sidebar.date_input("Bitiş Tarihi", value=today.date()))
    add_record_form(df)

    outgoing = df[df["İşlem Türü"] == "Yapılan Ödeme"].copy()
    incoming_all = df[df["İşlem Türü"] == "Gelen Bedel"].copy()
    invoices = df[df["İşlem Türü"] == "Kesilen Fatura"].copy()
    outgoing["Ödeme Analiz Kırılımı"] = outgoing["Açıklama"].apply(detect_breakdown)

    special_pattern = r"Cenk Çavuşoğlu|FX|DVZ|Bozum"
    special_mask = incoming_all["Açıklama"].astype(str).str.contains(special_pattern, case=False, na=False)
    incoming = incoming_all[~special_mask].copy()
    incoming_special = incoming_all[special_mask].copy()

    selected_incoming = incoming[(incoming["Tarih_dt"] >= start_date) & (incoming["Tarih_dt"] <= end_date)]
    selected_invoices = invoices[(invoices["Tarih_dt"] >= start_date) & (invoices["Tarih_dt"] <= end_date)]
    selected_outgoing = outgoing[(outgoing["Tarih_dt"] >= start_date) & (outgoing["Tarih_dt"] <= end_date)]

    c1, c2, c3, c4 = st.columns(4)
    with c1: metric_card("Dönem Kesilen Fatura", selected_invoices["Tutar"].sum(), "Alacak hedefi")
    with c2: metric_card("Dönem Gelen Bedel", selected_incoming["Tutar"].sum(), "Özel kayıtlar hariç")
    with c3: metric_card("Dönem Yapılan Ödeme", selected_outgoing["Tutar"].sum(), "Seçili dönem gideri")
    with c4: metric_card("Yıllık Gelen Bedel", incoming[(incoming["Tarih_dt"] >= year_start) & (incoming["Tarih_dt"] <= today)]["Tutar"].sum(), "Birikimli tahsilat")

    g1, g2 = st.columns(2)
    with g1:
        st.subheader("📈 Aylık Tahsilat")
        monthly_incoming = incoming.groupby("Fatura Dönemi")["Tutar"].sum().reindex(MONTH_ORDER, fill_value=0)
        active_months = [m for m in MONTH_ORDER if monthly_incoming[m] > 0] or [MONTHS[today.month]]
        st.plotly_chart(make_bar(active_months, [monthly_incoming[m] for m in active_months]), use_container_width=True)
    with g2:
        st.subheader("💸 Ödeme Kırılımı")
        breakdown = selected_outgoing.groupby("Ödeme Analiz Kırılımı")["Tutar"].sum().sort_values(ascending=False)
        if breakdown.empty:
            st.info("Seçili dönem için ödeme kaydı yok.")
        else:
            fig = go.Figure(data=[go.Pie(labels=breakdown.index, values=breakdown.values, hole=.58)])
            fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", height=240, font=dict(color="#cbd5e1"))
            st.plotly_chart(fig, use_container_width=True)

    st.divider()
    st.subheader("📊 Fatura / Tahsilat Performansı")
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

    tabs = st.tabs(["📊 Tüm Kayıtlar", "💸 Ödemeler", "💰 Gelen Bedeller", "🧾 Faturalar", "📤 Dosya Yükle"])
    with tabs[0]:
        edited = st.data_editor(df.drop(columns=["Tarih_dt"], errors="ignore"), use_container_width=True, height=420, num_rows="dynamic", hide_index=True)
        if st.button("💾 Tablo Değişikliklerini Kaydet", type="primary"):
            save_data(edited)
            st.success("Değişiklikler kaydedildi.")
            st.rerun()
    with tabs[1]:
        st.dataframe(outgoing.drop(columns=["Tarih_dt"], errors="ignore"), use_container_width=True, height=420, hide_index=True)
    with tabs[2]:
        st.caption("Cenk Çavuşoğlu ve FX/DVZ/Bozum kayıtları ana tahsilat toplamına dahil edilmez.")
        st.dataframe(incoming.drop(columns=["Tarih_dt"], errors="ignore"), use_container_width=True, height=420, hide_index=True)
    with tabs[3]:
        st.dataframe(invoices.drop(columns=["Tarih_dt"], errors="ignore"), use_container_width=True, height=420, hide_index=True)
    with tabs[4]:
        upload_type = st.selectbox("Yüklenecek dosya türü", ["Yapılan Ödemeler", "Gelen Bedeller", "CSV Hazır Veri"])
        uploaded = st.file_uploader("Dosya yükle", type=["xlsx", "csv"])
        if uploaded:
            if upload_type == "CSV Hazır Veri":
                uploaded_df = pd.read_csv(uploaded)
            elif upload_type == "Yapılan Ödemeler":
                uploaded_df = parse_outgoing_payments(uploaded)
            else:
                uploaded_df = parse_incoming_payments(uploaded)

            st.success(f"{len(uploaded_df)} kayıt dönüştürüldü.")
            st.dataframe(uploaded_df.head(100), use_container_width=True, hide_index=True)
            if st.button("Yüklenen Dosyayı Ana Veriye Aktar"):
                save_data(pd.concat([df.drop(columns=["Tarih_dt"], errors="ignore"), uploaded_df], ignore_index=True))
                st.success("Veriler ana dosyaya aktarıldı.")
                st.rerun()

    st.divider()
    export_file = "finans_raporu.xlsx"
    df.drop(columns=["Tarih_dt"], errors="ignore").to_excel(export_file, index=False)
    with open(export_file, "rb") as file:
        st.download_button("📥 Excel Raporu İndir", file, file_name=export_file, mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


if __name__ == "__main__":
    main()
st.markdown("""
<style>
.tech-bg {
    background: linear-gradient(135deg, #071827, #0b1120);
    padding: 28px;
    border-radius: 22px;
    border: 1px solid rgba(0, 255, 255, 0.15);
    box-shadow: 0 0 35px rgba(0, 255, 255, 0.08);
}

.tech-card {
    background: rgba(15, 23, 42, 0.92);
    border: 1px solid rgba(56, 189, 248, 0.20);
    border-radius: 18px;
    padding: 22px;
    box-shadow: 0 0 25px rgba(236, 72, 153, 0.12);
}

.tech-title {
    color: #93c5fd;
    font-size: 14px;
    letter-spacing: 1px;
    text-transform: uppercase;
}

.tech-value {
    color: #f8fafc;
    font-size: 34px;
    font-weight: 700;
}

.tech-sub {
    color: #22d3ee;
    font-size: 13px;
}
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="tech-bg">', unsafe_allow_html=True)

st.markdown("## 🛰️ DESecure Finansal Kontrol Paneli")
st.caption("Teknik finans izleme ekranı | Gelen bedeller, yapılan ödemeler, nakit akışı ve fatura analizi")

k1, k2, k3 = st.columns(3)

with k1:
    st.markdown(f"""
    <div class="tech-card">
        <div class="tech-title">Gelen Bedeller</div>
        <div class="tech-value">{ay_gelen['Tutar'].sum():,.0f} TL</div>
        <div class="tech-sub">Seçili / aylık dönem</div>
    </div>
    """, unsafe_allow_html=True)

with k2:
    st.markdown(f"""
    <div class="tech-card">
        <div class="tech-title">Yapılan Ödemeler</div>
        <div class="tech-value">{ay_yapilan['Tutar'].sum():,.0f} TL</div>
        <div class="tech-sub">Operasyonel çıkışlar</div>
    </div>
    """, unsafe_allow_html=True)

with k3:
    st.markdown(f"""
    <div class="tech-card">
        <div class="tech-title">Net Nakit Etkisi</div>
        <div class="tech-value">{(ay_gelen['Tutar'].sum() - ay_yapilan['Tutar'].sum()):,.0f} TL</div>
        <div class="tech-sub">Gelen - yapılan ödeme</div>
    </div>
    """, unsafe_allow_html=True)

st.write("")

c1, c2 = st.columns([1.2, 1])

with c1:
    chart_df = df.dropna(subset=["Tarih_dt"]).copy()
    chart_df = chart_df.groupby(["Tarih_dt", "İşlem Türü"])["Tutar"].sum().reset_index()

    fig = go.Figure()

    for tur in chart_df["İşlem Türü"].unique():
        temp = chart_df[chart_df["İşlem Türü"] == tur]
        fig.add_trace(go.Scatter(
            x=temp["Tarih_dt"],
            y=temp["Tutar"],
            mode="lines+markers",
            name=tur,
            line=dict(width=3),
            fill="tozeroy"
        ))

    fig.update_layout(
        title="Nakit Akışı",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(15,23,42,0.65)",
        font=dict(color="#e5e7eb"),
        height=360,
        margin=dict(l=20, r=20, t=50, b=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )

    st.plotly_chart(fig, use_container_width=True)

with c2:
    dagilim = df.groupby("İşlem Türü")["Tutar"].sum().reset_index()

    fig2 = go.Figure(data=[go.Pie(
        labels=dagilim["İşlem Türü"],
        values=dagilim["Tutar"],
        hole=0.55
    )])

    fig2.update_layout(
        title="İşlem Dağılımı",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(15,23,42,0.65)",
        font=dict(color="#e5e7eb"),
        height=360,
        margin=dict(l=20, r=20, t=50, b=20),
        legend=dict(font=dict(color="#e5e7eb"))
    )

    st.plotly_chart(fig2, use_container_width=True)

st.markdown('</div>', unsafe_allow_html=True)
