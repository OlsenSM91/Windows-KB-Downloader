import os
import requests
import re
import sqlite3
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time

def init_db():
    conn = sqlite3.connect('updates.db')
    cur = conn.cursor()
    cur.execute('''CREATE TABLE IF NOT EXISTS updates
                   (id TEXT PRIMARY KEY, title TEXT, size TEXT, download_link TEXT)''')
    conn.commit()
    conn.close()

def search_updates(query):
    conn = sqlite3.connect('updates.db')
    cur = conn.cursor()
    cur.execute("SELECT * FROM updates WHERE title LIKE ?", ('%'+query+'%',))
    rows = cur.fetchall()

    if rows:
        updates = [{'id': row[0], 'title': row[1], 'size': row[2], 'download_link': row[3]} for row in rows]
        conn.close()
        return updates

    driver = webdriver.Chrome()
    driver.get("https://www.catalog.update.microsoft.com/Search.aspx?q=" + query)
    time.sleep(5)

    updates = []
    soup = BeautifulSoup(driver.page_source, 'html.parser')
    rows = soup.find_all('tr', attrs={'id': re.compile(r'^[a-f0-9\-]+_R\d+$')})

    for row in rows:
        update_id = row.get('id', '').split('_')[0]
        title = row.find('a', {'id': re.compile(r'.+_link')}).text.strip()
        size = row.find('span', {'id': re.compile(r'.+_size')}).text.strip()
        updates.append({'id': update_id, 'title': title, 'size': size})
        cur.execute("INSERT OR IGNORE INTO updates (id, title, size) VALUES (?, ?, ?)", (update_id, title, size))

    driver.quit()
    conn.commit()
    conn.close()
    return updates

def download_update(update_id):
    conn = sqlite3.connect('updates.db')
    cur = conn.cursor()
    cur.execute("SELECT download_link FROM updates WHERE id = ?", (update_id,))
    row = cur.fetchone()

    if row and row[0]:
        conn.close()
        return row[0]

    driver = webdriver.Chrome()
    download_link = None

    try:
        driver.get(f"https://www.catalog.update.microsoft.com/Search.aspx?q={update_id}")
        wait = WebDriverWait(driver, 10)
        download_button = wait.until(EC.element_to_be_clickable((By.ID, update_id)))
        download_button.click()

        wait.until(EC.new_window_is_opened)
        driver.switch_to.window(driver.window_handles[1])

        wait.until(EC.presence_of_element_located((By.CLASS_NAME, 'contentTextItemSpacerNoBreakLink')))
        download_links = driver.find_elements(By.CLASS_NAME, 'contentTextItemSpacerNoBreakLink')
        if download_links:
            download_link = download_links[0].get_attribute('href')

    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        driver.quit()

    if download_link:
        cur.execute("UPDATE updates SET download_link = ? WHERE id = ?", (download_link, update_id))
        conn.commit()
    conn.close()
    return download_link

def download_file(url, directory):
    if not os.path.exists(directory):
        os.makedirs(directory)

    local_filename = url.split('/')[-1]
    path = os.path.join(directory, local_filename)

    with requests.get(url, stream=True) as r:
        with open(path, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
    return local_filename

def main():
    init_db()
    queries = input("Enter KB numbers or update names (separated by commas): ").split(',')

    all_updates = []
    for query in queries:
        query = query.strip()
        updates = search_updates(query)
        all_updates.extend(updates)

    for i, update in enumerate(all_updates, 1):
        print(f"{i}. Update found: {update['title']} ({update['size']})")

    download_directory = input("Enter the directory to save the downloads: ")
    selection = input("Enter the number(s) of the updates to download (e.g., 1,3 or 'all'): ")

    if selection.lower() != 'all':
        selected_indices = [int(idx) - 1 for idx in selection.split(',') if idx.isdigit()]
    else:
        selected_indices = range(len(all_updates))

    for index in selected_indices:
        if index < len(all_updates):
            update = all_updates[index]
            print(f"Downloading: {update['title']}")
            download_link = download_update(update['id'])
            if download_link:
                filename = download_file(download_link, download_directory)
                print(f"Downloaded {filename} to {download_directory}")
            else:
                print(f"Failed to get download link for {update['title']}")
        else:
            print(f"Invalid selection: {index + 1}")

if __name__ == "__main__":
    main()
