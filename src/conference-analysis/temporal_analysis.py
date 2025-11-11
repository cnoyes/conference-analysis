"""
Temporal analysis of General Conference talks.

Analyzes how word usage, phrases, and topics change over time.
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Tuple, Optional
from collections import Counter, defaultdict
import re
from sklearn.feature_extraction.text import TfidfVectorizer, CountVectorizer
from sklearn.decomposition import LatentDirichletAllocation
import matplotlib.pyplot as plt
import seaborn as sns
from wordcloud import WordCloud
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TemporalAnalyzer:
    """Analyze temporal trends in conference talks."""

    def __init__(self, talks_df: pd.DataFrame):
        """
        Initialize analyzer with talks data.

        Args:
            talks_df: DataFrame with columns: date, speaker, title, text
        """
        self.talks_df = talks_df.copy()
        self.talks_df['year'] = pd.to_datetime(self.talks_df['date']).dt.year
        self.talks_df['decade'] = (self.talks_df['year'] // 10) * 10

    def word_frequency_over_time(
        self,
        words: List[str],
        time_grouping: str = 'year',
        normalize: bool = True
    ) -> pd.DataFrame:
        """
        Calculate frequency of specific words over time.

        Args:
            words: List of words to track
            time_grouping: How to group time ('year', 'decade', 'conference')
            normalize: Whether to normalize by total word count

        Returns:
            DataFrame with word frequencies over time
        """
        results = []

        for period, group in self.talks_df.groupby(time_grouping):
            # Combine all text for this period
            combined_text = ' '.join(group['text'].astype(str))
            combined_text = combined_text.lower()

            # Count total words if normalizing
            if normalize:
                total_words = len(combined_text.split())
            else:
                total_words = 1

            # Count each word
            for word in words:
                # Use word boundaries to match whole words
                pattern = r'\b' + re.escape(word.lower()) + r'\b'
                count = len(re.findall(pattern, combined_text))
                freq = (count / total_words) * 1000 if normalize else count  # Per 1000 words

                results.append({
                    time_grouping: period,
                    'word': word,
                    'frequency': freq,
                    'count': count
                })

        return pd.DataFrame(results)

    def phrase_frequency_over_time(
        self,
        phrases: List[str],
        time_grouping: str = 'year',
        normalize: bool = True
    ) -> pd.DataFrame:
        """
        Calculate frequency of specific phrases over time.

        Args:
            phrases: List of phrases to track
            time_grouping: How to group time ('year', 'decade', 'conference')
            normalize: Whether to normalize by total word count

        Returns:
            DataFrame with phrase frequencies over time
        """
        results = []

        for period, group in self.talks_df.groupby(time_grouping):
            combined_text = ' '.join(group['text'].astype(str))
            combined_text = combined_text.lower()

            if normalize:
                total_words = len(combined_text.split())
            else:
                total_words = 1

            for phrase in phrases:
                # Case-insensitive phrase matching
                pattern = re.escape(phrase.lower())
                count = len(re.findall(pattern, combined_text))
                freq = (count / total_words) * 1000 if normalize else count

                results.append({
                    time_grouping: period,
                    'phrase': phrase,
                    'frequency': freq,
                    'count': count
                })

        return pd.DataFrame(results)

    def plot_word_trends(
        self,
        words: List[str],
        time_grouping: str = 'year',
        normalize: bool = True,
        interactive: bool = True
    ):
        """
        Plot word frequency trends over time.

        Args:
            words: List of words to track
            time_grouping: How to group time
            normalize: Whether to normalize frequencies
            interactive: Whether to use plotly (True) or matplotlib (False)
        """
        freq_df = self.word_frequency_over_time(words, time_grouping, normalize)

        if interactive:
            fig = px.line(
                freq_df,
                x=time_grouping,
                y='frequency',
                color='word',
                title=f"Word Frequency Over Time ({time_grouping.capitalize()})",
                labels={'frequency': 'Frequency (per 1000 words)' if normalize else 'Count'}
            )
            fig.update_layout(hovermode='x unified')
            return fig
        else:
            plt.figure(figsize=(12, 6))
            for word in words:
                word_data = freq_df[freq_df['word'] == word]
                plt.plot(word_data[time_grouping], word_data['frequency'], label=word, marker='o')

            plt.xlabel(time_grouping.capitalize())
            plt.ylabel('Frequency (per 1000 words)' if normalize else 'Count')
            plt.title(f'Word Frequency Over Time')
            plt.legend()
            plt.grid(True, alpha=0.3)
            plt.tight_layout()
            return plt.gcf()

    def plot_phrase_trends(
        self,
        phrases: List[str],
        time_grouping: str = 'year',
        normalize: bool = True,
        interactive: bool = True
    ):
        """
        Plot phrase frequency trends over time.

        Args:
            phrases: List of phrases to track
            time_grouping: How to group time
            normalize: Whether to normalize frequencies
            interactive: Whether to use plotly (True) or matplotlib (False)
        """
        freq_df = self.phrase_frequency_over_time(phrases, time_grouping, normalize)

        if interactive:
            fig = px.line(
                freq_df,
                x=time_grouping,
                y='frequency',
                color='phrase',
                title=f"Phrase Frequency Over Time ({time_grouping.capitalize()})",
                labels={'frequency': 'Frequency (per 1000 words)' if normalize else 'Count'}
            )
            fig.update_layout(hovermode='x unified')
            return fig
        else:
            plt.figure(figsize=(12, 6))
            for phrase in phrases:
                phrase_data = freq_df[freq_df['phrase'] == phrase]
                plt.plot(phrase_data[time_grouping], phrase_data['frequency'], label=phrase, marker='o')

            plt.xlabel(time_grouping.capitalize())
            plt.ylabel('Frequency (per 1000 words)' if normalize else 'Count')
            plt.title(f'Phrase Frequency Over Time')
            plt.legend()
            plt.grid(True, alpha=0.3)
            plt.tight_layout()
            return plt.gcf()

    def top_words_by_period(
        self,
        time_grouping: str = 'decade',
        top_n: int = 20,
        min_word_length: int = 4,
        stopwords: Optional[set] = None
    ) -> Dict[str, Counter]:
        """
        Find top words for each time period.

        Args:
            time_grouping: How to group time
            top_n: Number of top words to return
            min_word_length: Minimum word length to consider
            stopwords: Set of words to exclude

        Returns:
            Dictionary mapping period to Counter of top words
        """
        if stopwords is None:
            from nltk.corpus import stopwords as nltk_stopwords
            import nltk
            try:
                stopwords = set(nltk_stopwords.words('english'))
            except LookupError:
                nltk.download('stopwords')
                stopwords = set(nltk_stopwords.words('english'))

        # Add common religious words that might dominate
        stopwords.update(['god', 'jesus', 'christ', 'lord', 'father', 'spirit'])

        results = {}

        for period, group in self.talks_df.groupby(time_grouping):
            combined_text = ' '.join(group['text'].astype(str)).lower()

            # Extract words
            words = re.findall(r'\b[a-z]+\b', combined_text)

            # Filter words
            words = [
                w for w in words
                if len(w) >= min_word_length and w not in stopwords
            ]

            # Count and get top N
            counter = Counter(words)
            results[period] = counter.most_common(top_n)

        return results

    def wordcloud_by_period(
        self,
        period_value,
        time_grouping: str = 'decade',
        width: int = 800,
        height: int = 400,
        stopwords: Optional[set] = None
    ):
        """
        Generate word cloud for a specific time period.

        Args:
            period_value: Value of the period (e.g., 2010 for decade)
            time_grouping: Type of time grouping
            width: Width of wordcloud
            height: Height of wordcloud
            stopwords: Set of words to exclude

        Returns:
            WordCloud object
        """
        if stopwords is None:
            from nltk.corpus import stopwords as nltk_stopwords
            import nltk
            try:
                stopwords = set(nltk_stopwords.words('english'))
            except LookupError:
                nltk.download('stopwords')
                stopwords = set(nltk_stopwords.words('english'))

        # Get text for this period
        period_data = self.talks_df[self.talks_df[time_grouping] == period_value]
        combined_text = ' '.join(period_data['text'].astype(str))

        # Generate wordcloud
        wordcloud = WordCloud(
            width=width,
            height=height,
            background_color='white',
            stopwords=stopwords,
            max_words=200,
            relative_scaling=0.5,
            min_font_size=10
        ).generate(combined_text)

        return wordcloud

    def compare_periods(
        self,
        period1,
        period2,
        time_grouping: str = 'decade',
        top_n: int = 20
    ) -> Tuple[List[str], List[str], List[str]]:
        """
        Compare word usage between two time periods.

        Args:
            period1: First period to compare
            period2: Second period to compare
            time_grouping: Type of time grouping
            top_n: Number of top words to analyze

        Returns:
            Tuple of (unique_to_period1, unique_to_period2, common_to_both)
        """
        top_words = self.top_words_by_period(time_grouping, top_n=top_n)

        words1 = set(word for word, count in top_words.get(period1, []))
        words2 = set(word for word, count in top_words.get(period2, []))

        unique1 = list(words1 - words2)
        unique2 = list(words2 - words1)
        common = list(words1 & words2)

        return unique1, unique2, common

    def speaker_evolution(
        self,
        speaker_name: str,
        words: List[str],
        time_grouping: str = 'year',
        normalize: bool = True
    ) -> pd.DataFrame:
        """
        Track word usage for a specific speaker over time.

        Args:
            speaker_name: Name of speaker to analyze
            words: Words to track
            time_grouping: How to group time
            normalize: Whether to normalize by total words

        Returns:
            DataFrame with speaker's word usage over time
        """
        speaker_talks = self.talks_df[self.talks_df['speaker'] == speaker_name]

        results = []
        for period, group in speaker_talks.groupby(time_grouping):
            combined_text = ' '.join(group['text'].astype(str)).lower()

            if normalize:
                total_words = len(combined_text.split())
            else:
                total_words = 1

            for word in words:
                pattern = r'\b' + re.escape(word.lower()) + r'\b'
                count = len(re.findall(pattern, combined_text))
                freq = (count / total_words) * 1000 if normalize else count

                results.append({
                    time_grouping: period,
                    'word': word,
                    'frequency': freq,
                    'count': count,
                    'speaker': speaker_name
                })

        return pd.DataFrame(results)


if __name__ == "__main__":
    # Example usage
    import pandas as pd

    # Load sample data (you'll need to run scraper first)
    talks = pd.read_csv("data/raw/talks.csv")

    analyzer = TemporalAnalyzer(talks)

    # Track specific words over time
    words_to_track = ['faith', 'hope', 'charity', 'love', 'service']
    freq_df = analyzer.word_frequency_over_time(words_to_track, time_grouping='decade')
    print(freq_df)

    # Plot trends
    fig = analyzer.plot_word_trends(words_to_track, time_grouping='decade')
    fig.show()

    # Compare decades
    unique_70s, unique_2020s, common = analyzer.compare_periods(1970, 2020, time_grouping='decade')
    print(f"\nUnique to 1970s: {unique_70s[:10]}")
    print(f"Unique to 2020s: {unique_2020s[:10]}")
    print(f"Common: {common[:10]}")
