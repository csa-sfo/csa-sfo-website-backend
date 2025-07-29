
import requests
import html2text
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
import logging
import time
def get_urls():
    urls = [
        "https://csasfo.netlify.app/",
        "https://csasfo.netlify.app/about",
        "https://csasfo.netlify.app/events",
        "https://csasfo.netlify.app/archive",
        "https://csasfo.netlify.app/get-involved",
        "https://csasfo.netlify.app/contact",
        "https://csasfo.netlify.app/sponsorship",



    ]
    return urls 



# Scrape URL and convert to markdown
async def scrapped_website_content(url):
    try:
        # Set up Selenium WebDriver
        options = Options()
        options.add_argument("--headless")  # Run without opening a browser window
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
        driver.get(url)
        time.sleep(5)  # Wait for JavaScript to load (adjust as needed)
        page_source = driver.page_source
        driver.quit()
        soup = BeautifulSoup(page_source, "html.parser")
        for elem in soup(["nav", "footer"]):
            elem.decompose()
        h = html2text.HTML2Text()
        h.ignore_links = True
        markdown_content = h.handle(str(soup))
        logging.info(f"Scraped {len(markdown_content)} characters from {url}")
        return markdown_content
    except requests.RequestException as e:
        logging.error(f"Failed to scrape {url}: {e}")
        return ""
