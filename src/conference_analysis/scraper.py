"""
Web scraper for General Conference talks.

Scrapes talks from churchofjesuschrist.org and stores them in a structured format.
Based on the original R implementation.
"""

from datetime import datetime, date
from dateutil.relativedelta import relativedelta
import requests
from bs4 import BeautifulSoup
import pandas as pd
from typing import List, Dict, Optional
from tqdm import tqdm
import time
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ConferenceScraper:
    """Scraper for General Conference talks."""

    BASE_URL = "https://www.churchofjesuschrist.org"
    CONFERENCE_URL_TEMPLATE = BASE_URL + "/study/general-conference/{year}/{month:02d}?lang=eng"

    def __init__(self, cache_file: Optional[str] = None):
        """
        Initialize the scraper.

        Args:
            cache_file: Optional path to cache file (CSV) for storing talks
        """
        self.cache_file = cache_file
        self.talks_df = None

        if cache_file:
            try:
                self.talks_df = pd.read_csv(cache_file)
                self.talks_df['date'] = pd.to_datetime(self.talks_df['date'])
                logger.info(f"Loaded {len(self.talks_df)} talks from cache")
            except FileNotFoundError:
                logger.info("No cache file found, starting fresh")
                self.talks_df = pd.DataFrame()

    def get_conference_urls(self, start_date: date, end_date: Optional[date] = None) -> List[str]:
        """
        Generate conference URLs for all conferences between start and end dates.

        Conferences happen in April and October each year.

        Args:
            start_date: Starting date
            end_date: Ending date (defaults to today)

        Returns:
            List of conference URLs
        """
        if end_date is None:
            end_date = date.today()

        urls = []
        current = start_date

        while current <= end_date:
            # Conferences are in April (month 4) and October (month 10)
            for month in [4, 10]:
                conf_date = date(current.year, month, 1)
                if start_date <= conf_date <= end_date:
                    url = self.CONFERENCE_URL_TEMPLATE.format(
                        year=conf_date.year,
                        month=conf_date.month
                    )
                    urls.append(url)

            current = date(current.year + 1, 1, 1)

        return urls

    def get_talk_metadata(self, talk_element) -> Optional[Dict]:
        """
        Extract metadata from a talk element.

        Args:
            talk_element: BeautifulSoup element containing talk info

        Returns:
            Dictionary with title, speaker, and href
        """
        try:
            # Find the link element
            link = talk_element.find('a', class_='item-U_5Ca')
            if not link:
                return None

            # Get title
            title_span = link.find('span')
            title = title_span.get_text(strip=True) if title_span else None

            # Get speaker
            speaker_elem = link.find(class_='subtitle-LKtQp')
            speaker = speaker_elem.get_text(strip=True) if speaker_elem else None

            # Get href
            href = link.get('href')
            if href:
                href = self.BASE_URL + href

            # Extract date from URL (format: /study/general-conference/YYYY/MM/...)
            date_str = None
            if href:
                parts = href.split('/')
                try:
                    year_idx = parts.index('general-conference') + 1
                    year = int(parts[year_idx])
                    month = int(parts[year_idx + 1])
                    date_str = f"{year}-{month:02d}-01"
                except (ValueError, IndexError):
                    pass

            return {
                'title': title,
                'speaker': speaker,
                'href': href,
                'date': date_str
            }
        except Exception as e:
            logger.warning(f"Error extracting talk metadata: {e}")
            return None

    def get_talk_text(self, url: str) -> Optional[str]:
        """
        Fetch the full text of a talk.

        Args:
            url: URL of the talk

        Returns:
            Full text of the talk
        """
        try:
            logger.debug(f"Fetching talk: {url}")
            response = requests.get(url, timeout=10)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, 'lxml')

            # Find all paragraphs in the body
            paragraphs = soup.select('.body-block p')
            text = '\n\n'.join(p.get_text(strip=True) for p in paragraphs)

            return text
        except Exception as e:
            logger.error(f"Error fetching talk text from {url}: {e}")
            return None

    def scrape_conference(self, url: str) -> List[Dict]:
        """
        Scrape all talks from a single conference.

        Args:
            url: Conference URL

        Returns:
            List of talk dictionaries
        """
        try:
            logger.info(f"Scraping conference: {url}")
            response = requests.get(url, timeout=10)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, 'lxml')

            # Find all talk elements using XPath equivalent
            # Original R: talks <- conference %>% html_nodes(xpath = "//li[a[@class='item-U_5Ca']]")
            talk_elements = soup.find_all('li')

            talks = []
            for elem in talk_elements:
                if elem.find('a', class_='item-U_5Ca'):
                    metadata = self.get_talk_metadata(elem)
                    if metadata:
                        talks.append(metadata)

            logger.info(f"Found {len(talks)} talks")
            return talks

        except Exception as e:
            logger.error(f"Error scraping conference {url}: {e}")
            return []

    def scrape_all(
        self,
        start_date: date = date(1971, 4, 1),
        end_date: Optional[date] = None,
        fetch_text: bool = True,
        delay: float = 1.0
    ) -> pd.DataFrame:
        """
        Scrape all conferences in the date range.

        Args:
            start_date: Start date for scraping
            end_date: End date for scraping (defaults to today)
            fetch_text: Whether to fetch full text of talks
            delay: Delay between requests (seconds)

        Returns:
            DataFrame with all talks
        """
        urls = self.get_conference_urls(start_date, end_date)

        all_talks = []
        for url in tqdm(urls, desc="Scraping conferences"):
            talks = self.scrape_conference(url)
            all_talks.extend(talks)
            time.sleep(delay)  # Be respectful to the server

        df = pd.DataFrame(all_talks)

        if fetch_text and len(df) > 0:
            logger.info("Fetching full text for talks...")
            texts = []
            for href in tqdm(df['href'], desc="Fetching talk texts"):
                text = self.get_talk_text(href)
                texts.append(text)
                time.sleep(delay)

            df['text'] = texts
            # Filter out talks without text
            df = df[df['text'].notna() & (df['text'] != '')]

        df['date'] = pd.to_datetime(df['date'])

        if self.cache_file:
            df.to_csv(self.cache_file, index=False)
            logger.info(f"Saved {len(df)} talks to {self.cache_file}")

        self.talks_df = df
        return df

    def update_cache(self, delay: float = 1.0) -> pd.DataFrame:
        """
        Update the cache with new talks since last scrape.

        Args:
            delay: Delay between requests (seconds)

        Returns:
            Updated DataFrame with all talks
        """
        if self.talks_df is None or len(self.talks_df) == 0:
            return self.scrape_all(delay=delay)

        # Find the latest date we have
        latest_date = self.talks_df['date'].max().date()

        # Scrape from the next conference after latest_date
        next_date = latest_date + relativedelta(months=1)

        logger.info(f"Updating cache from {next_date} to today")
        new_talks = self.scrape_all(start_date=next_date, delay=delay)

        if len(new_talks) > 0:
            self.talks_df = pd.concat([self.talks_df, new_talks], ignore_index=True)
            self.talks_df = self.talks_df.drop_duplicates(subset=['href'])

            if self.cache_file:
                self.talks_df.to_csv(self.cache_file, index=False)
                logger.info(f"Added {len(new_talks)} new talks to cache")

        return self.talks_df


if __name__ == "__main__":
    # Example usage
    scraper = ConferenceScraper(cache_file="data/raw/talks.csv")

    # Update cache with new talks
    talks = scraper.update_cache()

    print(f"\nTotal talks: {len(talks)}")
    print(f"Date range: {talks['date'].min()} to {talks['date'].max()}")
    print(f"\nSample talks:")
    print(talks[['date', 'speaker', 'title']].head(10))
