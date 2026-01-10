import streamlit as st
from supabase import create_client, Client
import pandas as pd
import datetime

# --- KONFIGURACJA STRONY ---
st.set_page_config(page_title="Magazyn w Chmurze", layout="centered")
st.title("📦 System WMS - Logistyka")

# --- POŁĄCZENIE Z BAZĄ DANYCH ---
try:
    # Upewnij się, że w Secrets na Streamlit masz wpisane SUPABASE_URL i SUPABASE_KEY
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    supabase: Client = create_client(url, key)
except Exception as e:
    st.error("Nie udało się połączyć z bazą danych. Sprawdź sekrety w ustawieniach Streamlit!")
    st.stop()

# --- FUNKCJE POMOCNICZE ---

def get_inventory():
    """Pobiera aktualny stan z tabeli 'magazyn'"""
    # ZMIANA: Tabela nazywa się teraz 'magazyn'
    response = supabase.table('magazyn').select("*").execute()
    return pd.DataFrame(response.data)

def add_item(nazwa, ilosc, kategoria):
    """Dodaje nowy produkt"""
    # ZMIANA: Używamy polskich nazw kolumn: nazwa, ilosc, kategoria
    data = {"nazwa": nazwa, "ilosc": ilosc, "kategoria": kategoria}
    supabase.table('magazyn').insert(data).execute()

def update_quantity(item_id, new_quantity):
    """Aktualizuje ilość"""
    # ZMIANA: Aktualizujemy kolumnę 'ilosc'
    supabase.table('magazyn').update({"ilosc": new_quantity}).eq("id", item_id).execute()

def delete_item(item_id):
    """Usuwa produkt"""
    supabase.table('magazyn').delete().eq("id", item_id).execute()

# --- MENU APLIKACJI ---
menu = ["Stan Magazynowy", "Przyjęcie Towaru (Dodaj)", "Wydanie/Edycja", "Remanent (Raport)"]
choice = st.sidebar.selectbox("Menu", menu)

# --- WIDOK 1: STAN MAGAZYNOWY ---
if choice == "Stan Magazynowy":
    st.subheader("Aktualny stan magazynu")
    df = get_inventory()
    
    if not df.empty:
        # ZMIANA: Sortowanie po kolumnie 'nazwa'
        if 'nazwa' in df.columns:
            df = df.sort_values(by='nazwa')
            # Wyświetlanie konkretnych kolumn
            st.dataframe(df[['nazwa', 'kategoria', 'ilosc']], use_container_width=True)
            
            # Statystyki
            st.metric("Łączna ilość produktów", df['ilosc'].sum())
        else:
            st.error("Błąd: Nie znaleziono kolumny 'nazwa' w bazie danych.")
            st.write("Dostępne kolumny:", df.columns.tolist())
    else:
        st.info("Magazyn jest pusty.")

# --- WIDOK 2: PRZYJĘCIE TOWARU ---
elif choice == "Przyjęcie Towaru (Dodaj)":
    st.subheader("Dodaj nowy produkt do bazy")
    
    with st.form("add_form"):
        # ZMIANA: Zmienne dostosowane do polskich nazw
        name_input = st.text_input("Nazwa produktu")
        cat_input = st.selectbox("Kategoria", ["Elektronika", "Spożywcze", "Chemia", "Inne", "Części Zamienne"])
        qty_input = st.number_input("Ilość początkowa", min_value=1, step=1)
        
        submitted = st.form_submit_button("Dodaj do magazynu")
        
        if submitted:
            if name_input:
                add_item(name_input, qty_input, cat_input)
                st.success(f"Dodano {name_input} ({qty_input} szt.) do magazynu!")
            else:
                st.warning("Podaj nazwę produktu.")

# --- WIDOK 3: WYDANIE / EDYCJA ---
elif choice == "Wydanie/Edycja":
    st.subheader("Zarządzaj towarem")
    df = get_inventory()
    
    if not df.empty and 'nazwa' in df.columns:
        item_to_edit = st.selectbox("Wybierz produkt", df['nazwa'].unique())
        
        # Pobierz dane wybranego produktu
        current_item = df[df['nazwa'] == item_to_edit].iloc[0]
        current_id = int(current_item['id'])
        current_qty = int(current_item['ilosc']) # ZMIANA: kolumna ilosc
        
        st.write(f"Produkt: **{item_to_edit}**")
        st.write(f"Aktualna ilość: **{current_qty}**")
        
        col1, col2 = st.columns(2)
        
        with col1:
            new_qty = st.number_input("Nowa ilość", min_value=0, value=current_qty, step=1)
            if st.button("Zaktualizuj ilość"):
                update_quantity(current_id, new_qty)
                st.success("Zaktualizowano!")
                st.rerun()
        
        with col2:
            st.write("---")
            if st.button("🗑️ Usuń produkt z bazy"):
                delete_item(current_id)
                st.error("Produkt usunięty!")
                st.rerun()
    else:
        st.info("Brak produktów do edycji lub błąd nazw kolumn.")

# --- WIDOK 4: REMANENT ---
elif choice == "Remanent (Raport)":
    st.subheader("Przeprowadź Remanent")
    st.write("Pobierz aktualny stan magazynowy do pliku CSV.")
    
    df = get_inventory()
    
    if not df.empty:
        df['data_remanentu'] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Wyświetlamy podgląd
        st.dataframe(df)
        
        csv = df.to_csv(index=False).encode('utf-8')
        
        st.download_button(
            label="📥 Pobierz Protokół Remanentu (CSV)",
            data=csv,
            file_name='remanent_magazyn.csv',
            mime='text/csv',
        )
    else:
        st.info("Brak danych do remanentu.")
