import streamlit as st
from supabase import create_client, Client
import pandas as pd
import datetime

# --- KONFIGURACJA STRONY ---
st.set_page_config(page_title="WMS Logistyka PRO", layout="wide")
st.title("📦 System WMS - Logistyka (Z Dostawcami)")

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

def get_suppliers():
    """Nowa funkcja do pobierania dostawców"""
    response = supabase.table('dostawcy').select("*").execute()
    return pd.DataFrame(response.data)

def get_inventory_merged():
    """Pobiera stan magazynu i łączy z kategoriami ORAZ dostawcami"""
    response_magazyn = supabase.table('magazyn').select("*").execute()
    df_magazyn = pd.DataFrame(response_magazyn.data)
    
    if df_magazyn.empty:
        return pd.DataFrame()

    # Uzupełniamy braki w cenie
    if 'cena' not in df_magazyn.columns:
        df_magazyn['cena'] = 0.0

    # 1. Pobieramy słowniki
    df_kategorie = get_categories()
    df_dostawcy = get_suppliers()

    # 2. Łączymy z Kategoriami
    if not df_kategorie.empty and 'kategoria_id' in df_magazyn.columns:
        # Konwersja na int, żeby uniknąć błędów łączenia
        df_magazyn['kategoria_id'] = df_magazyn['kategoria_id'].fillna(0).astype(int)
        df_kategorie['id'] = df_kategorie['id'].astype(int)
        
        df_kategorie = df_kategorie.rename(columns={'nazwa': 'kategoria_nazwa', 'id': 'kat_id'})
        
        df_magazyn = pd.merge(
            df_magazyn, 
            df_kategorie, 
            left_on='kategoria_id', 
            right_on='kat_id', 
            how='left'
        )

    # 3. Łączymy z Dostawcami (NAPRAWIONE ŁĄCZENIE)
    if not df_dostawcy.empty and 'dostawca_id' in df_magazyn.columns:
        # Zmieniamy nazwy kolumn w dostawcach
        df_dostawcy = df_dostawcy.rename(columns={'nazwa': 'dostawca_nazwa', 'id': 'dost_id', 'nip': 'dostawca_nip'})
        
        # !!! WAŻNE !!!: Zamieniamy puste wartości (NaN) na 0 i konwertujemy na liczby całkowite
        # To naprawia błąd ValueError przy łączeniu
        df_magazyn['dostawca_id'] = df_magazyn['dostawca_id'].fillna(0).astype(int)
        df_dostawcy['dost_id'] = df_dostawcy['dost_id'].astype(int)

        df_magazyn = pd.merge(
            df_magazyn,
            df_dostawcy[['dost_id', 'dostawca_nazwa', 'dostawca_nip']], 
            left_on='dostawca_id',
            right_on='dost_id',
            how='left'
        )
    
    # Uzupełnij "Brak dostawcy" tam gdzie pusto
    if 'dostawca_nazwa' in df_magazyn.columns:
        df_magazyn['dostawca_nazwa'] = df_magazyn['dostawca_nazwa'].fillna('Brak danych')

    return df_magazyn

def add_or_update_item(nazwa, ilosc, cena, kategoria_id, kategoria_nazwa, dostawca_id, dostawca_nazwa):
    # Sprawdzamy czy towar o tej nazwie OD TEGO SAMEGO DOSTAWCY istnieje
    existing = supabase.table('magazyn').select("*").eq('nazwa', nazwa).eq('dostawca_id', dostawca_id).execute()
    
    if existing.data:
        # AKTUALIZACJA
        item_id = existing.data[0]['id']
        old_qty = existing.data[0]['ilosc']
        new_total_qty = old_qty + ilosc
        
        supabase.table('magazyn').update({
            "ilosc": new_total_qty,
            "cena": cena
        }).eq("id", item_id).execute()
        
        add_log(f"🔄 Dostawa '{nazwa}' (od {dostawca_nazwa}): ilosc {old_qty}->{new_total_qty}")
        st.success(f"Zaktualizowano stan produktu '{nazwa}' od dostawcy {dostawca_nazwa}.")
        
    else:
        # NOWY WPIS
        data = {
            "nazwa": nazwa, 
            "ilosc": ilosc, 
            "cena": cena,
            "kategoria_id": int(kategoria_id),
            "dostawca_id": int(dostawca_id)
        }
        supabase.table('magazyn').insert(data).execute()
        add_log(f"➕ Nowy towar: {nazwa} ({ilosc} szt.), Dostawca: {dostawca_nazwa}")
        st.success(f"Dodano nowy produkt: {nazwa}")

def update_item_details(item_id, new_qty, new_price, item_name):
    supabase.table('magazyn').update({
        "ilosc": new_qty,
        "cena": new_price
    }).eq("id", item_id).execute()
    add_log(f"✏️ Ręczna edycja '{item_name}': ilosc={new_qty}, cena={new_price}")

def delete_item(item_id, item_name):
    supabase.table('magazyn').delete().eq("id", item_id).execute()
    add_log(f"🗑️ Usunięto: {item_name}")

# --- MENU APLIKACJI ---
menu = ["Stan Magazynowy", "Przyjęcie Towaru (Dodaj)", "Wydanie/Edycja", "Historia Operacji", "Remanent (Raport)"]
choice = st.sidebar.selectbox("Menu", menu)

# --- WIDOK 1: STAN MAGAZYNOWY ---
if choice == "Stan Magazynowy":
    st.subheader("Aktualny stan magazynu")
    df = get_inventory_merged()
    
    if not df.empty and 'ilosc' in df.columns:
        
        # Kolumny do grupowania
        group_cols = ['nazwa']
        if 'kategoria_nazwa' in df.columns: group_cols.append('kategoria_nazwa')
        if 'dostawca_nazwa' in df.columns: group_cols.append('dostawca_nazwa')
        
        # AGREGACJA
        df_view = df.groupby(group_cols, as_index=False).agg({
            'ilosc': 'sum',
            'cena': 'mean'
        })
        
        # Rename dla czytelności
        rename_map = {'kategoria_nazwa': 'Kategoria', 'dostawca_nazwa': 'Dostawca'}
        df_view = df_view.rename(columns=rename_map)

        # FILTRACJA (usuwamy 0)
        df_view = df_view[df_view['ilosc'] > 0]

        if not df_view.empty:
            df_view['Wartość'] = df_view['ilosc'] * df_view['cena']
            
            # ALERT
            MINIMUM = 5
            low_stock = df_view[df_view['ilosc'] < MINIMUM]
            if not low_stock.empty:
                st.error(f"🚨 ALERT! Niskie stany ({len(low_stock)} poz.):")
                for i, row in low_stock.iterrows():
                    dost = row['Dostawca'] if 'Dostawca' in row else ''
                    st.warning(f"⚠️ **{row['nazwa']}** ({dost}): tylko {row['ilosc']} szt.")
                st.divider()

            # TABELA
            cols_to_show = ['nazwa', 'Kategoria', 'Dostawca', 'ilosc', 'cena', 'Wartość']
            final_cols = [c for c in cols_to_show if c in df_view.columns]
            
            st.dataframe(
                df_view[final_cols].style.format({'cena': '{:.2f} zł', 'Wartość': '{:.2f} zł'}), 
                use_container_width=True
            )
            
            # KPI
            c1, c2, c3 = st.columns(3)
            c1.metric("Ilość sztuk", int(df_view['ilosc'].sum()))
            c2.metric("Wartość magazynu", f"{df_view['Wartość'].sum():,.2f} zł")
            c3.metric("Liczba dostawców", df_view['Dostawca'].nunique() if 'Dostawca' in df_view else 0)
        else:
            st.info("Magazyn pusty (brak towarów > 0 szt).")
    else:
        st.info("Brak danych.")

# --- WIDOK 2: PRZYJĘCIE TOWARU ---
elif choice == "Przyjęcie Towaru (Dodaj)":
    st.subheader("Przyjęcie Towaru")
    
    df_cats = get_categories()
    df_supp = get_suppliers()
    
    if df_cats.empty:
        st.error("⚠️ Brak kategorii! Dodaj je w Supabase.")
    elif df_supp.empty:
        st.error("⚠️ Brak dostawców! Dodaj ich w Supabase (tabela 'dostawcy').")
    else:
        with st.form("add_form_full"):
            c1, c2 = st.columns(2)
            with c1:
                name = st.text_input("Nazwa produktu")
                
                # Słownik kategorii
                cat_dict = dict(zip(df_cats['nazwa'], df_cats['id']))
                sel_cat = st.selectbox("Kategoria", list(cat_dict.keys()))
                
                # Słownik dostawców
                supp_dict = dict(zip(df_supp['nazwa'], df_supp['id']))
                sel_supp = st.selectbox("Dostawca", list(supp_dict.keys()))
            
            with c2:
                qty = st.number_input("Ilość", min_value=1)
                price = st.number_input("Cena zakupu (zł)", min_value=0.01, step=0.01)

            if st.form_submit_button("Zatwierdź Przyjęcie"):
                if name:
                    cat_id = cat_dict[sel_cat]
                    supp_id = supp_dict[sel_supp]
                    add_or_update_item(name, qty, price, cat_id, sel_cat, supp_id, sel_supp)
                    st.rerun()
                else:
                    st.warning("Podaj nazwę towaru.")

# --- WIDOK 3: EDYCJA ---
elif choice == "Wydanie/Edycja":
    st.subheader("Edycja")
    df = get_inventory_merged()
    
    if not df.empty and 'nazwa' in df.columns:
        # Tworzymy unikalną etykietę dla listy rozwijanej
        df['label'] = df['nazwa'] + " (Dost: " + df['dostawca_nazwa'].fillna('?') + ")"
        
        sorted_labels = sorted(df['label'].unique())
        sel_label = st.selectbox("Wybierz produkt", sorted_labels)
        
        row = df[df['label'] == sel_label].iloc[0]
        
        curr_id = int(row['id'])
        curr_qty = int(row['ilosc'])
        curr_price = float(row['cena'])
        
        st.info(f"Edytujesz: **{row['nazwa']}** | Kategoria: {row.get('kategoria_nazwa','-')} | Dostawca: {row.get('dostawca_nazwa','-')}")
        
        c1, c2 = st.columns(2)
        new_qty = c1.number_input("Ilość", value=curr_qty)
        new_price = c2.number_input("Cena", value=curr_price)
        
        b1, b2 = st.columns(2)
        if b1.button("Zapisz"):
            update_item_details(curr_id, new_qty, new_price, row['nazwa'])
            st.success("Zapisano!")
            st.rerun()
        if b2.button("Usuń trwale"):
            delete_item(curr_id, row['nazwa'])
            st.rerun()
    else:
        st.info("Brak danych.")

# --- WIDOK 4: HISTORIA ---
elif choice == "Historia Operacji":
    st.subheader("🕵️ Historia")
    try:
        res = supabase.table('historia').select("*").order("created_at", desc=True).execute()
        dfh = pd.DataFrame(res.data)
        if not dfh.empty:
            dfh['created_at'] = pd.to_datetime(dfh['created_at']).dt.strftime('%Y-%m-%d %H:%M')
            st.dataframe(dfh[['created_at', 'opis']], use_container_width=True)
        else:
            st.info("Pusto.")
    except:
        st.error("Błąd historii.")

# --- WIDOK 5: REMANENT ---
elif choice == "Remanent (Raport)":
    st.subheader("Raport na dzień dzisiejszy")
    df = get_inventory_merged()
    if not df.empty:
        df['Wartosc'] = df['ilosc'] * df['cena']
        
        cols = ['nazwa', 'ilosc', 'cena', 'Wartosc']
        if 'kategoria_nazwa' in df.columns: 
            df = df.rename(columns={'kategoria_nazwa': 'Kategoria'})
            cols.insert(1, 'Kategoria')
        if 'dostawca_nazwa' in df.columns:
            df = df.rename(columns={'dostawca_nazwa': 'Dostawca'})
            cols.insert(2, 'Dostawca')
            
        # Zabezpieczenie kolumn
        final_cols = [c for c in cols if c in df.columns]
        export_df = df[final_cols]
        export_df['Data'] = datetime.datetime.now().strftime("%Y-%m-%d")
        
        st.dataframe(export_df, use_container_width=True)
    else:
        st.info("Magazyn pusty.")
