import streamlit as st
import pandas as pd
from datetime import datetime
import os
import base64
import plotly.graph_objects as go

DOSYA = "veriler.csv"

st.set_page_config(page_title="Finans Dashboard", page_icon="💰", layout="wide")

# --- KULLANICI TANIMLAMALARI ---
KULLANICILAR = {
    "merve bozkurt": "1234",
    "firdevs ulutas": "4321",
    "seray karabay": "3210"
}

if "giris_yapildi" not in st.session_state:
    st.session_state.giris_yapildi = False

if not st.session_state.giris_yapildi:
    st.title("🔐 Finans Dashboard Giriş")

    kullanici_adi = st.text_input("Kullanıcı Adı")
    sifre = st.text_input("Şifre", type="password")

    if st.button("Giriş Yap"):
        kb_kullanici = kullanici_adi.lower().strip()
        if kb_kullanici in KULLANICILAR and KULLANICILAR[kb_kullanici] == sifre:
            st.session_state.giris_yapildi = True
            st.session_state.kullanici_adi = kb_kullanici
            st.success("Giriş başarılı.")
            st.rerun()
        else:
            st.error("Kullanıcı adı veya şifre hatalı.")

    st.stop()

def get_base64_image(image_path):
    if os.path.exists(image_path):
        with open(image_path, "rb") as img_file:
            return base64.b64encode(img_file.read()).decode()
    return ""

logo_base64 = get_base64_image("logo.png")

if not os.path.exists(DOSYA):
    pd.DataFrame(columns=["Tarih", "Açıklama", "İşlem Türü", "Ödeme Tipi", "Tutar", "Ödeme Kırılımı", "Fatura Dönemi"]).to_csv(DOSYA, index=False)

df = pd.read_csv(DOSYA)
df = df[df["Tarih"].astype(str).str.contains("2026", na=False)]
df = df.drop_duplicates(subset=["Tarih", "Açıklama", "İşlem Türü", "Ödeme Tipi", "Tutar"])

for kolon in ["Tarih", "Açıklama", "İşlem Türü", "Ödeme Tipi", "Tutar", "Ödeme Kırılımı", "Fatura Dönemi"]:
    if kolon not in df.columns:
        df[kolon] = ""

df["İşlem Türü"] = df["İşlem Türü"].replace("", "Yapılan Ödeme").fillna("Yapılan Ödeme")
df["Tutar"] = pd.to_numeric(df["Tutar"], errors="coerce").fillna(0)
df["Tarih_dt"] = pd.to_datetime(df["Tarih"], format="%d-%m-%Y", errors="coerce")

aylar_map = {1:"Ocak", 2:"Şubat", 3:"Mart", 4:"Nisan", 5:"Mayıs", 6:"Haziran", 7:"Temmuz", 8:"Ağustos", 9:"Eylül", 10:"Ekim", 11:"Kasım", 12:"Aralık"}
df.loc[df["Fatura Dönemi"] == "", "Fatura Dönemi"] = df["Tarih_dt"].dt.month.map(aylar_map)
df["Fatura Dönemi"] = df["Fatura Dönemi"].fillna("Mayıs")

bugun = pd.Timestamp.today().normalize()
ay_basi = bugun.replace(day=1)
yil_basi = bugun.replace(month=1, day=1)

# --- SIDEBAR ---
st.sidebar.header("📅 Dönem Seçimi")
secili_baslangic = pd.Timestamp(st.sidebar.date_input("Başlangıç Tarihi", value=ay_basi.date()))
secili_bitis = pd.Timestamp(st.sidebar.date_input("Bitiş Tarihi", value=bugun.date()))

st.sidebar.header("➕ Yeni Kayıt")
tarih = st.sidebar.date_input("Tarih")
islem_turu = st.sidebar.selectbox("İşlem Türü", ["Yapılan Ödeme", "Kesilen Fatura", "Gelen Bedel"])

secili_kirilim = ""
odeme = ""
fatura_donemi = ""

aylar_sirasi = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]

if islem_turu == "Yapılan Ödeme":
    kirilim_secenekleri = ["vergiler", "kıdem ihbar", "icra", "maaş", "nakit çekilen", "avans", "iş avansı", "hgs", "banka masrafı", "kredi kartı ödemesi", "Diğer"]
    secili_kirilim = st.sidebar.selectbox("Ödeme Kırılımı", kirilim_secenekleri)
    odeme = st.sidebar.selectbox("Ödeme Tipi", ["Nakit", "Havale", "Kart"])
    fatura_donemi = aylar_map[tarih.month]
elif islem_turu == "Kesilen Fatura":
    fatura_donemi = st.sidebar.selectbox("Fatura Dönemi (Ait Olduğu Ay)", aylar_sirasi, index=datetime.now().month - 1)
    odeme = "Fatura (Bağımsız)"
else:
    odeme = st.sidebar.selectbox("Ödeme Tipi", ["Nakit", "Havale", "Kart"])
    fatura_donemi = aylar_map[tarih.month]

aciklama = st.sidebar.text_input("Açıklama")
tutar = st.sidebar.number_input("Tutar", min_value=0.0, step=100.0)

if st.sidebar.button("Kaydet"):
    yeni = pd.DataFrame([{
        "Tarih": tarih.strftime("%d-%m-%Y"),
        "Açıklama": aciklama,
        "İşlem Türü": islem_turu,
        "Ödeme Tipi": odeme,
        "Tutar": tutar,
        "Ödeme Kırılımı": secili_kirilim,
        "Fatura Dönemi": fatura_donemi
    }])
    ana = df.drop(columns=["Tarih_dt"], errors="ignore")
    ana = pd.concat([ana, yeni], ignore_index=True)
    ana.to_csv(DOSYA, index=False)
    st.success("Kayıt eklendi.")
    st.rerun()

# --- VERİ FİLTRELEME & HESAPLAMALAR ---
yapilan = df[df["İşlem Türü"] == "Yapılan Ödeme"]
gelen = df[df["İşlem Türü"] == "Gelen Bedel"]
fatura = df[df["İşlem Türü"] == "Kesilen Fatura"]

# Tarih Seçimine Göre Tam Dinamik Filtreleme (Kesişmeler engellendi)
secili_gelen = gelen[(gelen["Tarih_dt"] >= secili_baslangic) & (gelen["Tarih_dt"] <= secili_bitis)]
secili_fatura = fatura[(fatura["Tarih_dt"] >= secili_baslangic) & (fatura["Tarih_dt"] <= secili_bitis)]
secili_yapilan = yapilan[(yapilan["Tarih_dt"] >= secili_baslangic) & (yapilan["Tarih_dt"] <= secili_bitis)]

# Sabit Yıllık Kümülatif Hesaplamalar
yil_basi_gelen = gelen[(gelen["Tarih_dt"] >= yil_basi) & (gelen["Tarih_dt"] <= bugun)]
yil_basi_fatura = fatura[(fatura["Tarih_dt"] >= yil_basi) & (fatura["Tarih_dt"] <= bugun)]

ay_yapilan = yapilan[yapilan["Tarih_dt"] >= ay_basi]
ay_gelen = gelen[gelen["Tarih_dt"] >= ay_basi]

# --- TASARIM VE CSS ---
st.markdown(f"""
<style>
.hero {{
    background: linear-gradient(90deg, #374151 0%, #1f2937 50%, #111827 100%);
    border-radius: 12px; padding: 20px 40px; border: 1px solid rgba(255,255,255,0.1);
    box-shadow: 0 10px 30px rgba(0,0,0,0.5); margin-bottom: 25px; display: flex; align-items: center; justify-content: center; position: relative;
}}
.logo-box {{ background: white; border-radius: 10px; padding: 10px 20px; position: absolute; left: 40px; box-shadow: 0 4px 15px rgba(0,0,0,0.2); }}
.logo-box img {{ height: 38px; display: block; }}
.hero-text-container {{ text-align: center; }}
.hero-title {{ font-size: 50px; color: white; margin: 0; font-weight: 300; letter-spacing: 1px; }}
.hero-subtitle {{ font-size: 18px; color: #cbd5e1; margin-top: 8px; font-weight: 300; }}
.mini-card {{ background: #111827; border: 1px solid rgba(255,255,255,0.08); border-radius: 10px; padding: 16px; box-shadow: 0 4px 20px rgba(0,0,0,0.4); margin-bottom: 20px; }}
.mini-title {{ color: #9ca3af; font-size: 13px; font-weight: 500; margin-bottom: 8px; }}
.mini-value {{ color: white; font-size: 24px; font-weight: 600; margin-bottom: 6px; }}
.green-tag {{ color: #34d399; font-size: 12px; display: flex; align-items: center; gap: 4px; }}
.blue-tag {{ color: #60a5fa; font-size: 12px; display: flex; align-items: center; gap: 4px; }}
.chart-card {{ background: #111827; border: 1px solid rgba(255,255,255,0.05); border-radius: 12px; padding: 15px; box-shadow: 0 8px 24px rgba(0,0,0,0.3); }}
.chart-header {{ color: white; font-size: 14px; font-weight: 500; margin-bottom: 10px; }}
</style>

<div class="hero">
    <div class="logo-box"><img src="data:image/png;base64,{logo_base64}"></div>
    <div class="hero-text-container">
        <div class="hero-title">Desecure Finans Dashboard</div>
        <div class="hero-subtitle">Finans takip, ödemeler, gelen bedeller ve kesilen faturalar paneli</div>
    </div>
</div>
""", unsafe_allow_html=True)

# --- ÜST METRİK KARTLARI ---
col_a, col_b, col_c, col_d = st.columns(4)
with col_a:
    st.markdown(f'<div class="mini-card"><div class="mini-title">Seçili Ay Tahsil Edilecek Fatura</div><div class="mini-value">{secili_fatura["Tutar"].sum():,.0f} ₺</div><div class="blue-tag">📅 Dönem İçi Alacak Hedefi</div></div>', unsafe_allow_html=True)
with col_b:
    st.markdown(f'<div class="mini-card"><div class="mini-title">Seçili Dönem Gelen Bedel</div><div class="mini-value">{secili_gelen["Tutar"].sum():,.0f} ₺</div><div class="blue-tag">📅 Dönem İçi Yapılan Tahsilat</div></div>', unsafe_allow_html=True)
with col_c:
    st.markdown(f'<div class="mini-card"><div class="mini-title">Yıllık Toplam Kesilen Fatura</div><div class="mini-value">{yil_basi_fatura["Tutar"].sum():,.0f} ₺</div><div class="green-tag">🧾 1 Ocak\'tan Beri Ciro</div></div>', unsafe_allow_html=True)
with col_d:
    st.markdown(f'<div class="mini-card"><div class="mini-title">Yıl Başından Bugüne Gelen</div><div class="mini-value">{yil_basi_gelen["Tutar"].sum():,.0f} ₺</div><div class="green-tag">📈 Birikimli Toplam Kasa Girişi</div></div>', unsafe_allow_html=True)

# --- DİNAMİK MODERN GRAFİK PANELİ ---
st.markdown("<br>", unsafe_allow_html=True)
g_col1, g_col2, g_col3 = st.columns([1.3, 1.3, 1.4])

with g_col1:
    st.markdown('<div class="chart-card"><div class="chart-header">Gelen Ödemeler Aylık Trend</div>', unsafe_allow_html=True)
    fig1 = go.Figure()
    fig1.add_trace(go.Bar(
        x=['Oca', 'Şub', 'Mar', 'Nis', 'May'], 
        y=[12000, 19000, 15000, 28000, ay_gelen['Tutar'].sum() if len(ay_gelen)>0 else 0],
        marker_color='#34d399', opacity=0.85, marker_line_width=0
    ))
    fig1.update_layout(
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
        margin=dict(l=10, r=10, t=10, b=10), height=180, showlegend=False,
        xaxis=dict(showgrid=False, tickfont=dict(color='#9ca3af')),
        yaxis=dict(showgrid=True, gridcolor='rgba(255,255,255,0.05)', tickfont=dict(color='#9ca3af'))
    )
    st.plotly_chart(fig1, use_container_width=True, config={'displayModeBar': False})
    st.markdown('</div>', unsafe_allow_html=True)

with g_col2:
    st.markdown('<div class="chart-card"><div class="chart-header">Gider Dağılımı (Seçili Dönem)</div>', unsafe_allow_html=True)
    target_gider = secili_yapilan if len(secili_yapilan) > 0 else ay_yapilan
    if len(target_gider) > 0 and "Ödeme Kırılımı" in target_gider.columns:
        target_gider["Ödeme Kırılımı"] = target_gider["Ödeme Kırılımı"].fillna("Diğer").replace("", "Diğer")
        grup_df = target_gider.groupby("Ödeme Kırılımı")["Tutar"].sum().reset_index()
        labels = grup_df["Ödeme Kırılımı"].tolist()
        values = grup_df["Tutar"].tolist()
    else:
        labels = ["Henüz Veri Yok"]
        values = [1]

    fig2 = go.Figure(data=[go.Pie(labels=labels, values=values, hole=.6, marker=dict(colors=['#34d399', '#22d3ee', '#a855f7', '#f43f5e', '#fbbf24']))])
    fig2.update_layout(
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
        margin=dict(l=10, r=10, t=10, b=10), height=180,
        legend=dict(font=dict(color='#9ca3af', size=10), orientation="v", yanchor="middle", y=0.5, xanchor="left", x=1.05)
    )
    fig2.update_traces(textinfo='none')
    st.plotly_chart(fig2, use_container_width=True, config={'displayModeBar': False})
    st.markdown('</div>', unsafe_allow_html=True)

with g_col3:
    st.markdown('<div class="chart-card"><div class="chart-header">Fatura / Tahsilat Dönemsel Kıyas Analizi</div>', unsafe_allow_html=True)
    
    f_grup = df[df["İşlem Türü"] == "Kesilen Fatura"].groupby("Fatura Dönemi")["Tutar"].sum().reindex(aylar_sirasi, fill_value=0)
    t_grup = df[df["İşlem Türü"] == "Gelen Bedel"].groupby("Fatura Dönemi")["Tutar"].sum().reindex(aylar_sirasi, fill_value=0)
    
    aktif_aylar = [ay for ay in aylar_sirasi if f_grup[ay] > 0 or t_grup[ay] > 0]
    if not aktif_aylar:
        aktif_aylar = ["Mayıs"]
        
    f_dizi = [f_grup[ay] for ay in aktif_aylar]
    t_dizi = [t_grup[ay] for ay in aktif_aylar]

    fig3 = go.Figure()
    fig3.add_trace(go.Bar(x=aktif_aylar, y=f_dizi, name='Kesilen Fatura', marker_color='#60a5fa', opacity=0.85))
    fig3.add_trace(go.Bar(x=aktif_aylar, y=t_dizi, name='Tahsilat (Gelen)', marker_color='#34d399', opacity=0.85))
    
    fig3.update_layout(
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
        margin=dict(l=10, r=10, t=10, b=10), height=180, barmode='group',
        legend=dict(font=dict(color='#9ca3af', size=9), orientation="h", y=1.2, x=0),
        xaxis=dict(showgrid=False, tickfont=dict(color='#9ca3af')),
        yaxis=dict(showgrid=True, gridcolor='rgba(255,255,255,0.05)', tickfont=dict(color='#9ca3af'))
    )
    st.plotly_chart(fig3, use_container_width=True, config={'displayModeBar': False})
    st.markdown('</div>', unsafe_allow_html=True)

# --- FATURA / TAHSİLAT KIYAS TABLOSU ---
st.divider()
st.subheader("📊 Fatura ve Tahsilat Performans Raporu (Aylık)")

kiyas_data = []
for ay in aylar_sirasi:
    f_tutar = f_grup[ay]
    t_tutar = t_grup[ay]
    fark = f_tutar - t_tutar
    oran = (t_tutar / f_tutar * 100) if f_tutar > 0 else (100.0 if t_tutar > 0 else 0.0)
    
    if f_tutar > 0 or t_tutar > 0:
        kiyas_data.append({
            "Dönem / Ay": ay,
            "Kesilen Fatura Toplamı": f"{f_tutar:,.2f} ₺",
            "Yapılan Tahsilat Toplamı": f"{t_tutar:,.2f} ₺",
            "Kalan Alacak / Fark": f"{fark:,.2f} ₺",
            "Tahsilat Oranı": f"% {oran:.1f}"
        })

if kiyas_data:
    kiyas_df = pd.DataFrame(kiyas_data)
    st.dataframe(kiyas_df, use_container_width=True)
else:
    st.info("Kıyaslama tablosu için henüz girilmiş Fatura veya Gelen Bedel kaydı bulunmuyor.")

# --- DETAYLI VERİ SEKMELERİ VE METRİKLER ---
st.divider()
st.subheader("💰 Özel Gelen Bedel Takibi")

gelen_df = df[df["İşlem Türü"] == "Gelen Bedel"]
doviz_df = gelen_df[gelen_df["Açıklama"].str.contains("FX|DVZ|Bozum", case=False, na=False)]
cenk_df = gelen_df[gelen_df["Açıklama"].str.contains("Cenk Çavuşoğlu", case=False, na=False)]

st.markdown("### 💱 Döviz Bozumu")
col_d1, col_d2, col_d3 = st.columns(3)
col_d1.metric("Bugün Döviz", f"{doviz_df[doviz_df['Tarih_dt'] == bugun]['Tutar'].sum():,.0f} TL")
col_d2.metric("Ay Döviz", f"{doviz_df[(doviz_df['Tarih_dt'] >= ay_basi) & (doviz_df['Tarih_dt'] <= bugun)]['Tutar'].sum():,.0f} TL")
col_d3.metric("Yıl Döviz", f"{doviz_df[(doviz_df['Tarih_dt'] >= yil_basi) & (doviz_df['Tarih_dt'] <= bugun)]['Tutar'].sum():,.0f} TL")

st.markdown("### 👤 Cenk Çavuşoğlu")
col_c1, col_c2, col_c3 = st.columns(3)
col_c1.metric("Bugün Cenk", f"{cenk_df[cenk_df['Tarih_dt'] == bugun]['Tutar'].sum():,.0f} TL")
col_c2.metric("Ay Cenk", f"{cenk_df[(cenk_df['Tarih_dt'] >= ay_basi) & (cenk_df['Tarih_dt'] <= bugun)]['Tutar'].sum():,.0f} TL")
col_c3.metric("Yıl Cenk", f"{cenk_df[(cenk_df['Tarih_dt'] >= yil_basi) & (cenk_df['Tarih_dt'] <= bugun)]['Tutar'].sum():,.0f} TL")

st.divider()

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📊 Tüm Kayıtlar", "💸 Yapılan Ödemeler", "💰 Gelen Bedeller", 
    "📆 Seçili Dönem Gelen", "🧾 Seçili Ay Kesilen Faturalar", "📤 Dosya Yükle"
])

with tab1:
    duzenlenen = st.data_editor(df.drop(columns=["Tarih_dt"], errors="ignore"), use_container_width=True, height=400, num_rows="dynamic")
    if st.button("💾 Değişiklikleri Kaydet"):
        duzenlenen.to_csv(DOSYA, index=False)
        st.success("Değişiklikler kaydedildi.")
        st.rerun()

with tab2:
    st.dataframe(yapilan.drop(columns=["Tarih_dt"], errors="ignore"), use_container_width=True, height=400)
with tab3:
    st.dataframe(gelen.drop(columns=["Tarih_dt"], errors="ignore"), use_container_width=True, height=400)
with tab4:
    st.dataframe(secili_gelen.drop(columns=["Tarih_dt"], errors="ignore"), use_container_width=True, height=400)
with tab5:
    st.dataframe(secili_fatura.drop(columns=["Tarih_dt"], errors="ignore"), use_container_width=True, height=400)

def tutar_temizle(deger):
    if pd.isna(deger): return 0
    if isinstance(deger, (int, float)): return float(deger)
    deger = str(deger).replace("TL", "").replace("₺", "").replace(" ", "")
    if "," in deger and "." in deger: deger = deger.replace(".", "").replace(",", ".")
    elif "," in deger: deger = deger.replace(",", ".")
    try: return float(deger)
    except: return 0

def gelen_bedelleri_donustur(uploaded_file):
    ham = pd.read_excel(uploaded_file, header=None)
    kayitlar = []
    aktif_tarih = None
    for _, satir in ham.iterrows():
        ilk_hucre = satir.iloc[0]
        tutar = satir.iloc[1] if len(satir) > 1 else None
        if pd.isna(ilk_hucre): continue
        text = str(ilk_hucre).strip()
        tarih = pd.to_datetime(text.split("-")[0].strip(), format="%d.%m.%Y", errors="coerce")
        if not pd.isna(tarih):
            aktif_tarih = tarih.strftime("%d-%m-%Y")
            continue
        if text.upper() == "TOPLAM": continue
        if aktif_tarih and not pd.isna(tutar):
            kayitlar.append({
                "Tarih": aktif_tarih, "Açıklama": text, "İşlem Türü": "Gelen Bedel",
                "Ödeme Tipi": "Havale", "Tutar": tutar_temizle(tutar), "Ödeme Kırılımı": "", "Fatura Dönemi": aylar_map[pd.to_datetime(aktif_tarih, format="%d-%m-%Y").month]
            })
    return pd.DataFrame(kayitlar)

with tab6:
    st.subheader("📤 Excel / CSV Dosyası Yükle")
    uploaded_file = st.file_uploader("Dosya yükle", type=["xlsx", "csv"])
    if uploaded_file is not None:
        if uploaded_file.name.endswith(".csv"):
            yuklenen_df = pd.read_csv(uploaded_file)
        else:
            yuklenen_df = gelen_bedelleri_donustur(uploaded_file)
        st.success("Dosya başarıyla dönüştürüldü.")
        st.write(f"Toplam dönüştürülen kayıt: {len(yuklenen_df)}")
        st.dataframe(yuklenen_df.head(20), use_container_width=True)
        if st.button("Yüklenen Dosyayı Ana Veriye Aktar"):
            mevcut = df.drop(columns=["Tarih_dt"], errors="ignore")
            yeni_df = pd.concat([mevcut, yuklenen_df], ignore_index=True)
            yeni_df.to_csv(DOSYA, index=False)
            st.success("Gelen bedeller ana veriye aktarıldı.")
            st.rerun()

st.divider()
excel_dosya = "finans_raporu.xlsx"
df.drop(columns=["Tarih_dt"], errors="ignore").to_excel(excel_dosya, index=False)

with open(excel_dosya, "rb") as file:
    st.download_button(
        label="📥 Excel Raporu İndir",
        data=file,
        file_name=excel_dosya,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
