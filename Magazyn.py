import streamlit as st
from supabase import create_client, Client
import pandas as pd
import datetime

# --- KONFIGURACJA STRONY ---
st.set_page_config(page_title="Magazyn w Chmurze (Relacyjny)", layout="centered")
st.title("📦 System WMS - Logistyka")

# --- POŁĄCZENIE Z BAZĄ DANYCH ---
try:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    supabase: Client = create_client(url, key)
except Exception as e:
    st.error("Błąd połączenia z bazą. Sprawdź sekrety!")
    st.stop()

# --- FUNKCJE POMOCNICZE ---

def get_categories():
    """Pobiera słownik kategorii z tabeli 'kategorie'"""
    response = supabase.table('kategorie').select("*").execute()
    return pd.DataFrame(response.data)

def get_inventory_merged():
    """
    Pobiera stan magazynu i łączy go z tabelą kategorii,
    aby wyświetlić nazwę kategorii zamiast samego ID.
    """
    # 1. Pobierz towary
    response_magazyn = supabase.table('magazyn').select("*").execute()
    df_magazyn = pd.DataFrame(response_magazyn.data)
    
    # 2. Pobierz kategorie
    df_kategorie = get_categories()
    
    # Jeśli magazyn jest pusty, zwróć pusty DataFrame
    if df_magazyn.empty:
        return pd.DataFrame()

    # 3. Połącz tabele (MERGE / JOIN) - to jest to 'łączenie' o które pytałeś
    # Łączymy kolumnę 'kategoria_id' z magazynu z 'id' z kategorii
    if not df_kategorie.empty and 'kategoria_id' in df_magazyn.columns:
        # Zmieniamy nazwę kolumny 'nazwa' w kategoriach na 'kategoria_nazwa' żeby się nie myliło
        df_kategorie = df_kategorie.rename(columns={'nazwa': 'kategoria_nazwa', 'id': 'kat_id'})
        
        # Merge (Left Join)
        df_merged = pd.merge(
            df_magazyn, 
            df_kategorie, 
            left_on='kategoria_id', 
            right_on='kat_id', 
            how='left'
        )
        return df_merged
    
    return df_magazyn

def add_item(nazwa, ilosc, kategoria_id):
    """Dodaje produkt z relacją do ID kategorii"""
    # Zapisujemy ID kategorii, a nie jej nazwę!
    data = {
        "nazwa": nazwa, 
        "ilosc": ilosc, 
        "kategoria_id": int(kategoria_id)
    }
    supabase.table('magazyn').insert(data).execute()

def update_quantity(item_id, new_quantity):
    supabase.table('magazyn').update({"ilosc": new_quantity}).eq("id", item_id).execute()

def delete_item(item_id):
    supabase.table('magazyn').delete().eq("id", item_id).execute()

# --- MENU APLIKACJI ---
menu = ["Stan Magazynowy", "Przyjęcie Towaru (Dodaj)", "Wydanie/Edycja", "Remanent (Raport)"]
choice = st.sidebar.selectbox("Menu", menu)

# --- LOGIKA ---

if choice == "Stan Magazynowy":
    st.subheader("Aktualny stan magazynu")
    df = get_inventory_merged()
    
    if not df.empty and 'nazwa' in df.columns:
        # Wybieramy co chcemy pokazać. Teraz mamy kolumnę 'kategoria_nazwa' z połączenia
        cols_to_show = ['nazwa', 'ilosc']
        
        if 'kategoria_nazwa' in df.columns:
            cols_to_show.append('kategoria_nazwa')
            # Ładniejsza nazwa kolumny do wyświetlenia
            df = df.rename(columns={'kategoria_nazwa': 'Kategoria'})
            cols_to_show = ['nazwa', 'Kategoria', 'ilosc']
            
        st.dataframe(df[cols_to_show], use_container_width=True)
        st.metric("Suma produktów", df['ilosc'].sum())
    else:
        st.info("Magazyn pusty.")

elif choice == "Przyjęcie Towaru (Dodaj)":
    st.subheader("Przyjęcie (Relacja z tabelą Kategorie)")
    
    # Najpierw pobieramy dostępne kategorie z bazy
    df_cats = get_categories()
    
    if df_cats.empty:
        st.error("Brak kategorii w bazie! Dodaj je w Supabase w tabeli 'kategorie'.")
    else:
        with st.form("add_form_relational"):
            name = st.text_input("Nazwa produktu")
            
            # Tworzymy słownik: Nazwa Kategorii -> ID Kategorii
            # Dzięki temu użytkownik widzi nazwę, a my wysyłamy do bazy ID
            cat_dict = dict(zip(df_cats['nazwa'], df_cats['id']))
            selected_cat_name = st.selectbox("Wybierz kategorię", list(cat_dict.keys()))
            
            qty = st.number_input("Ilość", min_value=1, step=1)
            
            if st.form_submit_button("Dodaj"):
                # Pobieramy ID dla wybranej nazwy
                selected_cat_id = cat_dict[selected_cat_name]
                
                add_item(name, qty, selected_cat_id)
                st.success(f"Dodano produkt do kategorii '{selected_cat_name}' (ID={selected_cat_id})")

elif choice == "Wydanie/Edycja":
    st.subheader("Edycja Stanów")
    df = get_inventory_merged()
    
    if not df.empty and 'nazwa' in df.columns:
        item_to_edit = st.selectbox("Produkt", df['nazwa'].unique())
        
        row = df[df['nazwa'] == item_to_edit].iloc[0]
        curr_id = int(row['id'])
        curr_qty = int(row['ilosc'])
        
        st.write(f"Aktualnie: {curr_qty} szt.")
        new_qty = st.number_input("Nowa ilość", value=curr_qty)
        
        col1, col2 = st.columns(2)
        if col1.button("Zapisz zmianę"):
            update_quantity(curr_id, new_qty)
            st.success("Zapisano")
            st.rerun()
            
        if col2.button("Usuń"):
            delete_item(curr_id)
            st.rerun()

elif choice == "Remanent (Raport)":
    st.subheader("Raport Remanentowy")
    df = get_inventory_merged()
    if not df.empty:
        # Czyścimy dane do ładnego CSV (tylko nazwa, kategoria, ilość)
        if 'kategoria_nazwa' in df.columns:
            df['Kategoria'] = df['kategoria_nazwa']
            export_df = df[['nazwa', 'Kategoria', 'ilosc']]
        else:
            export_df = df
            
        export_df['data_spisu'] = datetime.datetime.now().strftime("%Y-%m-%d")
        st.dataframe(export_df)
        st.download_button("Pobierz CSV", export_df.to_csv(index=False).encode('utf-8'), "remanent.csv")
