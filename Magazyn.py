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
    """
    Funkcja zapisująca historię operacji do tabeli 'historia'.
    Działa w tle przy dodawaniu/usuwaniu/edycji.
    """
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

def add_item(nazwa, ilosc, kategoria_id, kategoria_nazwa):
    data = {"nazwa": nazwa, "ilosc": ilosc, "kategoria_id": int(kategoria_id)}
    supabase.table('magazyn').insert(data).execute()
    # Logujemy operację
    add_log(f"➕ Przyjęto towar: {nazwa} ({ilosc} szt.), kat: {kategoria_nazwa}")

def update_quantity(item_id, old_qty, new_qty, item_name):
    supabase.table('magazyn').update({"ilosc": new_quantity}).eq("id", item_id).execute()
    # Logujemy operację
    add_log(f"✏️ Zmiana stanu '{item_name}': z {old_qty} na {new_qty}")

def delete_item(item_id, item_name):
    supabase.table('magazyn').delete().eq("id", item_id).execute()
    # Logujemy operację
    add_log(f"🗑️ Usunięto trwale towar: {item_name}")

# --- MENU APLIKACJI ---
menu = ["Stan Magazynowy", "Przyjęcie Towaru (Dodaj)", "Wydanie/Edycja", "Historia Operacji", "Remanent (Raport)"]
choice = st.sidebar.selectbox("Menu", menu)

# --- WIDOK 1: STAN MAGAZYNOWY + ALERTY ---
if choice == "Stan Magazynowy":
    st.subheader("Aktualny stan magazynu")
    df = get_inventory_merged()
    
    if not df.empty and 'ilosc' in df.columns:
        # === MODUŁ ALERTÓW (Nowość!) ===
        # Sprawdzamy, czy coś ma stan poniżej 5 sztuk
        MINIMUM_LOGISTYCZNE = 5
        low_stock = df[df['ilosc'] < MINIMUM_LOGISTYCZNE]
        
        if not low_stock.empty:
            st.error(f"🚨 ALERT! Niskie stany magazynowe ({len(low_stock)} prod.):")
            for index, row in low_stock.iterrows():
                st.warning(f"⚠️ **{row['nazwa']}**: zostało tylko {row['ilosc']} szt. (Zamów towar!)")
            st.divider()
        # ================================

        # Wyświetlanie tabeli
        cols_to_show = ['nazwa', 'ilosc']
        if 'kategoria_nazwa' in df.columns:
            df = df.rename(columns={'kategoria_nazwa': 'Kategoria'})
            cols_to_show = ['nazwa', 'Kategoria', 'ilosc']
            
        st.dataframe(df[cols_to_show], use_container_width=True)
        
        # Szybkie KPI
        c1, c2, c3 = st.columns(3)
        c1.metric("Suma produktów", df['ilosc'].sum())
        c2.metric("Liczba pozycji (SKU)", len(df))
        c3.metric("Wartość magazynu", "Brak danych cenowych")
        
    else:
        st.info("Magazyn pusty.")

# --- WIDOK 2: PRZYJĘCIE TOWARU ---
elif choice == "Przyjęcie Towaru (Dodaj)":
    st.subheader("Przyjęcie (Relacja z tabelą Kategorie)")
    df_cats = get_categories()
    
    if df_cats.empty:
        st.error("Brak kategorii w bazie!")
    else:
        with st.form("add_form_relational"):
            name = st.text_input("Nazwa produktu")
            cat_dict = dict(zip(df_cats['nazwa'], df_cats['id']))
            selected_cat_name = st.selectbox("Wybierz kategorię", list(cat_dict.keys()))
            qty = st.number_input("Ilość", min_value=1, step=1)
            
            if st.form_submit_button("Dodaj"):
                if name:
                    selected_cat_id = cat_dict[selected_cat_name]
                    add_item(name, qty, selected_cat_id, selected_cat_name)
                    st.success(f"Dodano produkt: {name}")
                else:
                    st.warning("Wpisz nazwę.")

# --- WIDOK 3: WYDANIE / EDYCJA ---
elif choice == "Wydanie/Edycja":
    st.subheader("Edycja Stanów")
    df = get_inventory_merged()
    
    if not df.empty and 'nazwa' in df.columns:
        item_to_edit = st.selectbox("Produkt", df['nazwa'].unique())
        
        row = df[df['nazwa'] == item_to_edit].iloc[0]
        curr_id = int(row['id'])
        curr_qty = int(row['ilosc'])
        
        st.write(f"Produkt: **{item_to_edit}** | Stan: **{curr_qty}**")
        new_qty = st.number_input("Nowa ilość", value=curr_qty, min_value=0)
        
        col1, col2 = st.columns(2)
        if col1.button("Zapisz zmianę"):
            update_quantity(curr_id, curr_qty, new_qty, item_to_edit)
            st.success("Zapisano")
            st.rerun()
            
        if col2.button("Usuń trwale"):
            delete_item(curr_id, item_to_edit)
            st.error("Usunięto!")
            st.rerun()

# --- WIDOK 4: HISTORIA (Nowość!) ---
elif choice == "Historia Operacji":
    st.subheader("🕵️ Dziennik Zdarzeń (Logi)")
    st.write("Pełna historia operacji wykonanych w systemie.")
    
    # Pobieramy historię sortując od najnowszych
    try:
        response = supabase.table('historia').select("*").order("created_at", desc=True).execute()
        df_hist = pd.DataFrame(response.data)
        
        if not df_hist.empty:
            # Formatujemy datę, żeby była czytelna (usuwamy "T" i strefę czasową dla czytelności)
            df_hist['created_at'] = pd.to_datetime(df_hist['created_at']).dt.strftime('%Y-%m-%d %H:%M:%S')
            
            # Zmieniamy nazwy kolumn na ładne polskie
            df_hist = df_hist.rename(columns={'created_at': 'Czas Operacji', 'opis': 'Opis Zdarzenia'})
            
            st.dataframe(df_hist[['Czas Operacji', 'Opis Zdarzenia']], use_container_width=True)
        else:
            st.info("Brak historii operacji.")
    except Exception as e:
        st.error(f"Błąd pobierania historii: {e}")

# --- WIDOK 5: REMANENT ---
elif choice == "Remanent (Raport)":
    st.subheader("Raport Remanentowy")
    df = get_inventory_merged()
    if not df.empty:
        if 'kategoria_nazwa' in df.columns:
            df['Kategoria'] = df['kategoria_nazwa']
            export_df = df[['nazwa', 'Kategoria', 'ilosc']]
        else:
            export_df = df
            
        export_df['data_spisu'] = datetime.datetime.now().strftime("%Y-%m-%d")
        st.dataframe(export_df)
        st.download_button("Pobierz CSV", export_df.to_csv(index=False).encode('utf-8'), "remanent.csv")
