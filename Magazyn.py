import streamlit as st
from supabase import create_client, Client
import pandas as pd
import datetime

# --- KONFIGURACJA STRONY ---
st.set_page_config(page_title="Magazyn w Chmurze PRO", layout="centered")
st.title("📦 System WMS - Logistyka")

# --- POŁĄCZENIE Z BAZĄ DANYCH ---
try:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    supabase: Client = create_client(url, key)
except Exception as e:
    st.error("Błąd połączenia z bazą. Sprawdź sekrety!")
    st.stop()

# --- FUNKCJE POMOCNICZE (LOGIKA BIZNESOWA) ---

def add_log(opis_zdarzenia):
    """Zapisuje zdarzenia w historii"""
    try:
        supabase.table('historia').insert({"opis": opis_zdarzenia}).execute()
    except Exception as e:
        print(f"Nie udało się zapisać logu: {e}")

def get_categories():
    response = supabase.table('kategorie').select("*").execute()
    return pd.DataFrame(response.data)

def get_inventory_merged():
    """Pobiera stan magazynu i łączy z kategoriami"""
    response_magazyn = supabase.table('magazyn').select("*").execute()
    df_magazyn = pd.DataFrame(response_magazyn.data)
    df_kategorie = get_categories()
    
    if df_magazyn.empty:
        return pd.DataFrame()

    if 'cena' not in df_magazyn.columns:
        df_magazyn['cena'] = 0.0

    if not df_kategorie.empty and 'kategoria_id' in df_magazyn.columns:
        df_kategorie = df_kategorie.rename(columns={'nazwa': 'kategoria_nazwa', 'id': 'kat_id'})
        df_merged = pd.merge(
            df_magazyn, 
            df_kategorie, 
            left_on='kategoria_id', 
            right_on='kat_id', 
            how='left'
        )
        return df_merged
    return df_magazyn

def add_or_update_item(nazwa, ilosc, cena, kategoria_id, kategoria_nazwa):
    existing = supabase.table('magazyn').select("*").eq('nazwa', nazwa).execute()
    
    if existing.data:
        item_id = existing.data[0]['id']
        old_qty = existing.data[0]['ilosc']
        new_total_qty = old_qty + ilosc
        
        supabase.table('magazyn').update({
            "ilosc": new_total_qty,
            "cena": cena
        }).eq("id", item_id).execute()
        
        add_log(f"🔄 Zaktualizowano '{nazwa}': ilość {old_qty}->{new_total_qty}, cena: {cena} PLN")
        st.success(f"Produkt '{nazwa}' już istniał. Zwiększono ilość do {new_total_qty}.")
        
    else:
        data = {
            "nazwa": nazwa, 
            "ilosc": ilosc, 
            "cena": cena,
            "kategoria_id": int(kategoria_id)
        }
        supabase.table('magazyn').insert(data).execute()
        add_log(f"➕ Przyjęto nowy towar: {nazwa} ({ilosc} szt., {cena} PLN), kat: {kategoria_nazwa}")
        st.success(f"Dodano nowy produkt: {nazwa}")

def update_item_details(item_id, old_qty, new_qty, old_price, new_price, item_name):
    supabase.table('magazyn').update({
        "ilosc": new_qty,
        "cena": new_price
    }).eq("id", item_id).execute()
    
    add_log(f"✏️ Edycja '{item_name}': Ilość {old_qty}->{new_qty}, Cena {old_price}->{new_price}")

def delete_item(item_id, item_name):
    supabase.table('magazyn').delete().eq("id", item_id).execute()
    add_log(f"🗑️ Usunięto trwale towar: {item_name}")

# --- MENU APLIKACJI ---
menu = ["Stan Magazynowy", "Przyjęcie Towaru (Dodaj)", "Wydanie/Edycja", "Historia Operacji", "Remanent (Raport)"]
choice = st.sidebar.selectbox("Menu", menu)

# --- WIDOK 1: STAN MAGAZYNOWY (Z AGREGACJĄ I FILTRACJĄ ZER) ---
if choice == "Stan Magazynowy":
    st.subheader("Aktualny stan magazynu")
    df = get_inventory_merged()
    
    if not df.empty and 'ilosc' in df.columns:
        
        # 1. Agregacja (sumowanie duplikatów)
        if 'kategoria_nazwa' in df.columns:
            df_view = df.grou
