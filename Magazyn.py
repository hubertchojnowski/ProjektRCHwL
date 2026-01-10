import streamlit as st
from supabase import create_client, Client
import pandas as pd
import datetime

# --- KONFIGURACJA STRONY ---
st.set_page_config(page_title="Cloud WMS", layout="centered")
st.title("📦 Prosty System WMS (Logistyka)")

# --- POŁĄCZENIE Z BAZĄ DANYCH ---
# Pobieramy sekrety z ustawień Streamlit Cloud
try:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    supabase: Client = create_client(url, key)
except Exception as e:
    st.error("Nie udało się połączyć z bazą danych. Sprawdź sekrety!")
    st.stop()

# --- FUNKCJE POMOCNICZE ---
def get_inventory():
    """Pobiera aktualny stan magazynowy z Supabase"""
    response = supabase.table('inventory').select("*").execute()
    return pd.DataFrame(response.data)

def add_item(name, quantity, category):
    """Dodaje nowy produkt"""
    data = {"product_name": name, "quantity": quantity, "category": category}
    supabase.table('inventory').insert(data).execute()

def update_quantity(item_id, new_quantity):
    """Aktualizuje ilość"""
    supabase.table('inventory').update({"quantity": new_quantity}).eq("id", item_id).execute()

def delete_item(item_id):
    """Usuwa produkt"""
    supabase.table('inventory').delete().eq("id", item_id).execute()

# --- MENU APLIKACJI ---
menu = ["Stan Magazynowy", "Przyjęcie Towaru (Dodaj)", "Wydanie/Edycja", "Remanent (Raport)"]
choice = st.sidebar.selectbox("Menu", menu)

# --- WIDOK 1: STAN MAGAZYNOWY ---
if choice == "Stan Magazynowy":
    st.subheader("Aktualny stan magazynu")
    df = get_inventory()
    
    if not df.empty:
        # Sortowanie i wyświetlanie
        df = df.sort_values(by='product_name')
        st.dataframe(df[['product_name', 'category', 'quantity']], use_container_width=True)
        
        # Szybkie statystyki
        st.metric("Łączna ilość produktów", df['quantity'].sum())
    else:
        st.info("Magazyn jest pusty.")

# --- WIDOK 2: PRZYJĘCIE TOWARU ---
elif choice == "Przyjęcie Towaru (Dodaj)":
    st.subheader("Dodaj nowy produkt do bazy")
    
    with st.form("add_form"):
        name = st.text_input("Nazwa produktu")
        category = st.selectbox("Kategoria", ["Elektronika", "Spożywcze", "Chemia", "Inne"])
        qty = st.number_input("Ilość początkowa", min_value=1, step=1)
        
        submitted = st.form_submit_button("Dodaj do magazynu")
        
        if submitted:
            if name:
                add_item(name, qty, category)
                st.success(f"Dodano {name} ({qty} szt.) do magazynu!")
            else:
                st.warning("Podaj nazwę produktu.")

# --- WIDOK 3: WYDANIE / EDYCJA ---
elif choice == "Wydanie/Edycja":
    st.subheader("Zarządzaj towarem")
    df = get_inventory()
    
    if not df.empty:
        item_to_edit = st.selectbox("Wybierz produkt", df['product_name'].unique())
        
        # Pobierz dane wybranego produktu
        current_item = df[df['product_name'] == item_to_edit].iloc[0]
        current_id = int(current_item['id'])
        current_qty = int(current_item['quantity'])
        
        st.write(f"Aktualna ilość: **{current_qty}**")
        
        col1, col2 = st.columns(2)
        
        with col1:
            new_qty = st.number_input("Nowa ilość", min_value=0, value=current_qty, step=1)
            if st.button("Zaktualizuj ilość"):
                update_quantity(current_id, new_qty)
                st.success("Zaktualizowano!")
                st.rerun() # Odświeża stronę
        
        with col2:
            st.write("---")
            if st.button("🗑️ Usuń produkt z bazy"):
                delete_item(current_id)
                st.error("Produkt usunięty!")
                st.rerun()
    else:
        st.info("Brak produktów do edycji.")

# --- WIDOK 4: REMANENT ---
elif choice == "Remanent (Raport)":
    st.subheader("Przeprowadź Remanent")
    st.write("Pobierz aktualny stan magazynowy do pliku CSV w celu archiwizacji.")
    
    df = get_inventory()
    
    if not df.empty:
        # Dodajemy kolumnę z datą remanentu
        df['data_remanentu'] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        st.dataframe(df)
        
        csv = df.to_csv(index=False).encode('utf-8')
        
        st.download_button(
            label="📥 Pobierz Protokół Remanentu (CSV)",
            data=csv,
            file_name='remanent_wms.csv',
            mime='text/csv',
        )
    else:
        st.info("Brak danych do remanentu.")
