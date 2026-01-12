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
            df_view = df.groupby(['nazwa', 'kategoria_nazwa'], as_index=False).agg({
                'ilosc': 'sum',
                'cena': 'mean'
            })
            df_view = df_view.rename(columns={'kategoria_nazwa': 'Kategoria'})
        else:
            df_view = df.groupby(['nazwa'], as_index=False).agg({'ilosc': 'sum', 'cena': 'mean'})

        # 2. FILTRACJA - Wyrzucamy 0 i mniej
        df_view = df_view[df_view['ilosc'] > 0]

        if not df_view.empty:
            # Obliczanie wartości
            df_view['Wartość Całkowita'] = df_view['ilosc'] * df_view['cena']
            
            # === ALERT ===
            MINIMUM_LOGISTYCZNE = 5
            low_stock = df_view[df_view['ilosc'] < MINIMUM_LOGISTYCZNE]
            
            if not low_stock.empty:
                st.error(f"🚨 ALERT! Niskie stany magazynowe ({len(low_stock)} prod.):")
                for index, row in low_stock.iterrows():
                    st.warning(f"⚠️ **{row['nazwa']}**: zostało {row['ilosc']} szt.")
                st.divider()

            # Wyświetlanie tabeli
            st.dataframe(
                df_view[['nazwa', 'Kategoria', 'ilosc', 'cena', 'Wartość Całkowita']].style.format({
                    'cena': '{:.2f} PLN',
                    'Wartość Całkowita': '{:.2f} PLN'
                }), 
                use_container_width=True
            )
            
            # KPI
            total_qty = df_view['ilosc'].sum()
            total_value = df_view['Wartość Całkowita'].sum()
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Suma produktów (szt.)", int(total_qty))
            c2.metric("Liczba pozycji (SKU)", len(df_view))
            c3.metric("Wartość magazynu", f"{total_value:,.2f} PLN")
        else:
            st.info("Magazyn pusty (brak produktów o ilości > 0).")
            
    else:
        st.info("Brak danych w bazie.")

# --- WIDOK 2: PRZYJĘCIE TOWARU ---
elif choice == "Przyjęcie Towaru (Dodaj)":
    st.subheader("Przyjęcie (Inteligentne dodawanie)")
    st.info("Jeśli dodasz produkt o nazwie, która już istnieje, system zsumuje ilości!")
    
    df_cats = get_categories()
    
    if df_cats.empty:
        st.error("Brak kategorii w bazie!")
    else:
        with st.form("add_form_smart"):
            col_a, col_b = st.columns(2)
            with col_a:
                name = st.text_input("Nazwa produktu")
                cat_dict = dict(zip(df_cats['nazwa'], df_cats['id']))
                selected_cat_name = st.selectbox("Wybierz kategorię", list(cat_dict.keys()))
            
            with col_b:
                qty = st.number_input("Ilość", min_value=1, step=1)
                price = st.number_input("Cena jedn. (PLN)", min_value=0.0, step=0.01, format="%.2f")
            
            if st.form_submit_button("Zatwierdź przyjęcie"):
                if name:
                    selected_cat_id = cat_dict[selected_cat_name]
                    add_or_update_item(name, qty, price, selected_cat_id, selected_cat_name)
                    st.rerun()
                else:
                    st.warning("Wpisz nazwę.")

# --- WIDOK 3: WYDANIE / EDYCJA ---
elif choice == "Wydanie/Edycja":
    st.subheader("Edycja Stanów i Cen")
    df = get_inventory_merged()
    
    if not df.empty and 'nazwa' in df.columns:
        sorted_names = sorted(df['nazwa'].unique())
        item_to_edit = st.selectbox("Wybierz produkt do edycji", sorted_names)
        
        # Pobieramy pierwszy napotkany wiersz
        row = df[df['nazwa'] == item_to_edit].iloc[0]
        
        curr_id = int(row['id'])
        curr_qty = int(row['ilosc'])
        curr_price = float(row['cena']) if pd.notnull(row['cena']) else 0.0
        
        st.write(f"Produkt: **{item_to_edit}**")
        
        c1, c2 = st.columns(2)
        with c1:
            new_qty = st.number_input("Ilość", value=curr_qty, min_value=0)
        with c2:
            new_price = st.number_input("Cena (PLN)", value=curr_price, min_value=0.0, step=0.01)
        
        col1, col2 = st.columns(2)
        if col1.button("Zapisz zmiany"):
            update_item_details(curr_id, curr_qty, new_qty, curr_price, new_price, item_to_edit)
            st.success("Zapisano!")
            st.rerun()
            
        if col2.button("Usuń trwale"):
            delete_item(curr_id, item_to_edit)
            st.error("Usunięto!")
            st.rerun()
    else:
        st.info("Brak produktów do edycji.")

# --- WIDOK 4: HISTORIA ---
elif choice == "Historia Operacji":
    st.subheader("🕵️ Dziennik Zdarzeń")
    try:
        response = supabase.table('historia').select("*").order("created_at", desc=True).execute()
        df_hist = pd.DataFrame(response.data)
        if not df_hist.empty:
            df_hist['created_at'] = pd.to_datetime(df_hist['created_at']).dt.strftime('%Y-%m-%d %H:%M:%S')
            df_hist = df_hist.rename(columns={'created_at': 'Czas', 'opis': 'Zdarzenie'})
            st.dataframe(df_hist[['Czas', 'Zdarzenie']], use_container_width=True)
        else:
            st.info("Brak historii.")
    except Exception as e:
        st.error(f"Błąd: {e}")

# --- WIDOK 5: REMANENT ---
elif choice == "Remanent (Raport)":
    st.subheader("Raport Remanentowy")
    st.write("Podgląd stanu magazynowego na dzień dzisiejszy.")
    df = get_inventory_merged()
    if not df.empty:
        if 'cena' not in df.columns: df['cena'] = 0.0
        df['Wartosc'] = df['ilosc'] * df['cena']
        
        if 'kategoria_nazwa' in df.columns:
            df['Kategoria'] = df['kategoria_nazwa']
            export_df = df[['nazwa', 'Kategoria', 'ilosc', 'cena', 'Wartosc']]
        else:
            export_df = df
            
        export_df['data_spisu'] = datetime.datetime.now().strftime("%Y-%m-%d")
        
        st.dataframe(export_df, use_container_width=True)
    else:
        st.info("Brak danych w magazynie.")
