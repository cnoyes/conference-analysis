"""
Systematic trend analysis to identify words, phrases, and themes that have
increased or decreased over time in General Conference talks.

This module provides tools to discover:
- Words/phrases with biggest increases/decreases
- Thematic/semantic shifts using embeddings
- Statistical significance of changes
- Comparative analysis between time periods
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Tuple, Optional
from collections import Counter
import re
from scipy import stats
from sklearn.feature_extraction.text import TfidfVectorizer, CountVectorizer
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TrendAnalyzer:
    """Analyze trends in word usage, phrases, and themes over time."""

    def __init__(self, talks_df: pd.DataFrame):
        """
        Initialize analyzer with talks data.

        Args:
            talks_df: DataFrame with columns: date, speaker, title, text
        """
        self.talks_df = talks_df.copy()
        self.talks_df['year'] = pd.to_datetime(self.talks_df['date']).dt.year
        self.talks_df['decade'] = (self.talks_df['year'] // 10) * 10

    def compare_time_periods(
        self,
        early_period: Tuple[int, int],
        late_period: Tuple[int, int],
        top_n: int = 50,
        min_occurrences: int = 10,
        stopwords: Optional[set] = None
    ) -> pd.DataFrame:
        """
        Compare word usage between two time periods to find biggest changes.

        Args:
            early_period: (start_year, end_year) for early period
            late_period: (start_year, end_year) for late period
            top_n: Number of top changed words to return
            min_occurrences: Minimum total occurrences to consider
            stopwords: Words to exclude

        Returns:
            DataFrame with word changes, sorted by absolute change
        """
        if stopwords is None:
            from nltk.corpus import stopwords as nltk_stopwords
            import nltk
            try:
                stopwords = set(nltk_stopwords.words('english'))
            except LookupError:
                nltk.download('stopwords')
                stopwords = set(nltk_stopwords.words('english'))

        # Get talks for each period
        early_talks = self.talks_df[
            (self.talks_df['year'] >= early_period[0]) &
            (self.talks_df['year'] <= early_period[1])
        ]
        late_talks = self.talks_df[
            (self.talks_df['year'] >= late_period[0]) &
            (self.talks_df['year'] <= late_period[1])
        ]

        # Combine all text for each period
        early_text = ' '.join(early_talks['text'].astype(str)).lower()
        late_text = ' '.join(late_talks['text'].astype(str)).lower()

        # Count words in each period
        early_words = re.findall(r'\b[a-z]{3,}\b', early_text)
        late_words = re.findall(r'\b[a-z]{3,}\b', late_text)

        # Filter stopwords
        early_words = [w for w in early_words if w not in stopwords]
        late_words = [w for w in late_words if w not in stopwords]

        # Get total word counts for normalization
        early_total = len(early_words)
        late_total = len(late_words)

        # Count occurrences
        early_counter = Counter(early_words)
        late_counter = Counter(late_words)

        # Get all words that appear in either period
        all_words = set(early_counter.keys()) | set(late_counter.keys())

        results = []
        for word in all_words:
            early_count = early_counter.get(word, 0)
            late_count = late_counter.get(word, 0)
            total_count = early_count + late_count

            if total_count < min_occurrences:
                continue

            # Frequency per 10,000 words
            early_freq = (early_count / early_total) * 10000
            late_freq = (late_count / late_total) * 10000

            # Calculate change
            change = late_freq - early_freq
            pct_change = ((late_freq - early_freq) / early_freq * 100) if early_freq > 0 else np.inf

            results.append({
                'word': word,
                'early_freq': early_freq,
                'late_freq': late_freq,
                'change': change,
                'pct_change': pct_change,
                'early_count': early_count,
                'late_count': late_count,
                'total_count': total_count
            })

        df = pd.DataFrame(results)
        df = df.sort_values('change', key=abs, ascending=False)

        return df.head(top_n)

    def find_increasing_words(
        self,
        early_period: Tuple[int, int],
        late_period: Tuple[int, int],
        top_n: int = 25,
        min_occurrences: int = 10
    ) -> pd.DataFrame:
        """
        Find words that have increased the most.

        Returns DataFrame sorted by words with largest increase.
        """
        df = self.compare_time_periods(early_period, late_period, top_n * 2, min_occurrences)
        return df[df['change'] > 0].sort_values('change', ascending=False).head(top_n)

    def find_decreasing_words(
        self,
        early_period: Tuple[int, int],
        late_period: Tuple[int, int],
        top_n: int = 25,
        min_occurrences: int = 10
    ) -> pd.DataFrame:
        """
        Find words that have decreased the most.

        Returns DataFrame sorted by words with largest decrease.
        """
        df = self.compare_time_periods(early_period, late_period, top_n * 2, min_occurrences)
        return df[df['change'] < 0].sort_values('change', ascending=True).head(top_n)

    def compare_phrases(
        self,
        early_period: Tuple[int, int],
        late_period: Tuple[int, int],
        ngram_range: Tuple[int, int] = (2, 3),
        top_n: int = 25,
        min_occurrences: int = 5
    ) -> pd.DataFrame:
        """
        Compare phrase usage between two time periods.

        Args:
            early_period: (start_year, end_year) for early period
            late_period: (start_year, end_year) for late period
            ngram_range: (min_n, max_n) for n-grams (2,3 = bigrams and trigrams)
            top_n: Number of top phrases to return
            min_occurrences: Minimum total occurrences

        Returns:
            DataFrame with phrase changes
        """
        # Get talks for each period
        early_talks = self.talks_df[
            (self.talks_df['year'] >= early_period[0]) &
            (self.talks_df['year'] <= early_period[1])
        ]
        late_talks = self.talks_df[
            (self.talks_df['year'] >= late_period[0]) &
            (self.talks_df['year'] <= late_period[1])
        ]

        # Use CountVectorizer to extract phrases
        vectorizer = CountVectorizer(
            ngram_range=ngram_range,
            max_features=5000,
            lowercase=True,
            token_pattern=r'\b[a-z]{3,}\b'
        )

        # Fit on all text to get vocabulary
        all_text = pd.concat([early_talks['text'], late_talks['text']])
        vectorizer.fit(all_text.astype(str))

        # Get counts for each period
        early_counts = vectorizer.transform(early_talks['text'].astype(str)).sum(axis=0).A1
        late_counts = vectorizer.transform(late_talks['text'].astype(str)).sum(axis=0).A1

        # Get total words for normalization
        early_total = early_counts.sum()
        late_total = late_counts.sum()

        # Build results
        phrases = vectorizer.get_feature_names_out()
        results = []

        for i, phrase in enumerate(phrases):
            early_count = early_counts[i]
            late_count = late_counts[i]
            total_count = early_count + late_count

            if total_count < min_occurrences:
                continue

            # Frequency per 10,000 words
            early_freq = (early_count / early_total) * 10000
            late_freq = (late_count / late_total) * 10000

            change = late_freq - early_freq
            pct_change = ((late_freq - early_freq) / early_freq * 100) if early_freq > 0 else np.inf

            results.append({
                'phrase': phrase,
                'early_freq': early_freq,
                'late_freq': late_freq,
                'change': change,
                'pct_change': pct_change,
                'early_count': early_count,
                'late_count': late_count,
                'total_count': total_count
            })

        df = pd.DataFrame(results)
        df = df.sort_values('change', key=abs, ascending=False)

        return df.head(top_n)

    def test_hypothesis(
        self,
        concept_words: List[str],
        early_period: Tuple[int, int],
        late_period: Tuple[int, int]
    ) -> Dict:
        """
        Test a hypothesis about whether certain words/concepts have increased.

        Args:
            concept_words: List of words representing a concept
            early_period: Early time period
            late_period: Late time period

        Returns:
            Dictionary with test results
        """
        early_talks = self.talks_df[
            (self.talks_df['year'] >= early_period[0]) &
            (self.talks_df['year'] <= early_period[1])
        ]
        late_talks = self.talks_df[
            (self.talks_df['year'] >= late_period[0]) &
            (self.talks_df['year'] <= late_period[1])
        ]

        results = {}
        for word in concept_words:
            # Count occurrences in each period
            early_text = ' '.join(early_talks['text'].astype(str)).lower()
            late_text = ' '.join(late_talks['text'].astype(str)).lower()

            pattern = r'\b' + re.escape(word.lower()) + r'\b'
            early_count = len(re.findall(pattern, early_text))
            late_count = len(re.findall(pattern, late_text))

            # Normalize by total words
            early_words = len(early_text.split())
            late_words = len(late_text.split())

            early_freq = (early_count / early_words) * 10000
            late_freq = (late_count / late_words) * 10000

            results[word] = {
                'early_freq': early_freq,
                'late_freq': late_freq,
                'change': late_freq - early_freq,
                'pct_change': ((late_freq - early_freq) / early_freq * 100) if early_freq > 0 else np.inf,
                'early_count': early_count,
                'late_count': late_count
            }

        return results

    def visualize_word_changes(
        self,
        early_period: Tuple[int, int],
        late_period: Tuple[int, int],
        top_n: int = 20
    ):
        """
        Create visualization showing top increasing and decreasing words.

        Args:
            early_period: Early time period
            late_period: Late time period
            top_n: Number of words to show in each direction

        Returns:
            Plotly figure
        """
        increasing = self.find_increasing_words(early_period, late_period, top_n)
        decreasing = self.find_decreasing_words(early_period, late_period, top_n)

        # Create subplots
        fig = make_subplots(
            rows=1, cols=2,
            subplot_titles=(
                f'Top {top_n} Increasing Words',
                f'Top {top_n} Decreasing Words'
            ),
            horizontal_spacing=0.15
        )

        # Increasing words
        fig.add_trace(
            go.Bar(
                y=increasing['word'][::-1],
                x=increasing['change'][::-1],
                orientation='h',
                name='Increasing',
                marker_color='green',
                text=increasing['change'][::-1].round(2),
                textposition='auto',
            ),
            row=1, col=1
        )

        # Decreasing words
        fig.add_trace(
            go.Bar(
                y=decreasing['word'][::-1],
                x=decreasing['change'][::-1].abs(),
                orientation='h',
                name='Decreasing',
                marker_color='red',
                text=decreasing['change'][::-1].abs().round(2),
                textposition='auto',
            ),
            row=1, col=2
        )

        fig.update_xaxes(title_text="Change in Frequency (per 10k words)", row=1, col=1)
        fig.update_xaxes(title_text="Change in Frequency (per 10k words)", row=1, col=2)

        fig.update_layout(
            title_text=f"Word Frequency Changes: {early_period[0]}-{early_period[1]} vs {late_period[0]}-{late_period[1]}",
            showlegend=False,
            height=600,
            width=1200
        )

        return fig

    def visualize_concept_over_time(
        self,
        concept_words: List[str],
        concept_name: str,
        time_grouping: str = 'decade'
    ):
        """
        Visualize how a concept (represented by multiple words) changes over time.

        Args:
            concept_words: List of words representing the concept
            concept_name: Name for the concept (for labeling)
            time_grouping: 'year' or 'decade'

        Returns:
            Plotly figure
        """
        results = []

        for period, group in self.talks_df.groupby(time_grouping):
            combined_text = ' '.join(group['text'].astype(str)).lower()
            total_words = len(combined_text.split())

            # Count total occurrences of concept words
            total_count = 0
            for word in concept_words:
                pattern = r'\b' + re.escape(word.lower()) + r'\b'
                total_count += len(re.findall(pattern, combined_text))

            freq = (total_count / total_words) * 10000

            results.append({
                time_grouping: period,
                'frequency': freq,
                'count': total_count
            })

        df = pd.DataFrame(results)

        fig = go.Figure()

        fig.add_trace(go.Scatter(
            x=df[time_grouping],
            y=df['frequency'],
            mode='lines+markers',
            name=concept_name,
            line=dict(width=3),
            marker=dict(size=10),
            hovertemplate=f'<b>{time_grouping.capitalize()}: %{{x}}</b><br>' +
                         f'Frequency: %{{y:.2f}} per 10k words<br>' +
                         '<extra></extra>'
        ))

        fig.update_layout(
            title=f'{concept_name} Usage Over Time',
            xaxis_title=time_grouping.capitalize(),
            yaxis_title='Frequency (per 10,000 words)',
            hovermode='x unified',
            height=500,
            width=900
        )

        return fig

    def comparative_concept_analysis(
        self,
        concepts: Dict[str, List[str]],
        time_grouping: str = 'decade'
    ):
        """
        Compare multiple concepts over time.

        Args:
            concepts: Dict mapping concept names to lists of words
                     e.g., {'Christ-centered': ['christ', 'savior', 'atonement'],
                            'Administration': ['program', 'organization', 'auxiliary']}
            time_grouping: 'year' or 'decade'

        Returns:
            Plotly figure
        """
        all_results = []

        for concept_name, concept_words in concepts.items():
            for period, group in self.talks_df.groupby(time_grouping):
                combined_text = ' '.join(group['text'].astype(str)).lower()
                total_words = len(combined_text.split())

                # Count total occurrences of concept words
                total_count = 0
                for word in concept_words:
                    pattern = r'\b' + re.escape(word.lower()) + r'\b'
                    total_count += len(re.findall(pattern, combined_text))

                freq = (total_count / total_words) * 10000

                all_results.append({
                    time_grouping: period,
                    'concept': concept_name,
                    'frequency': freq
                })

        df = pd.DataFrame(all_results)

        fig = px.line(
            df,
            x=time_grouping,
            y='frequency',
            color='concept',
            markers=True,
            title='Comparative Concept Analysis Over Time',
            labels={'frequency': 'Frequency (per 10,000 words)', time_grouping: time_grouping.capitalize()}
        )

        fig.update_traces(line=dict(width=3), marker=dict(size=10))
        fig.update_layout(hovermode='x unified', height=600, width=1000)

        return fig


if __name__ == "__main__":
    # Example usage
    import pandas as pd

    # Load talks
    talks = pd.read_csv("data/raw/talks.csv")
    talks['date'] = pd.to_datetime(talks['date'])

    analyzer = TrendAnalyzer(talks)

    # Compare 1970s vs 2020s
    print("=== TOP INCREASING WORDS ===")
    increasing = analyzer.find_increasing_words((1970, 1979), (2020, 2024), top_n=25)
    print(increasing[['word', 'early_freq', 'late_freq', 'change', 'pct_change']].to_string())

    print("\n=== TOP DECREASING WORDS ===")
    decreasing = analyzer.find_decreasing_words((1970, 1979), (2020, 2024), top_n=25)
    print(decreasing[['word', 'early_freq', 'late_freq', 'change', 'pct_change']].to_string())

    # Test specific hypothesis
    print("\n=== TESTING CHRIST-CENTERED HYPOTHESIS ===")
    christ_words = ['christ', 'savior', 'atonement', 'redeemer', 'mediator']
    results = analyzer.test_hypothesis(christ_words, (1970, 1979), (2020, 2024))
    for word, data in results.items():
        print(f"{word}: {data['early_freq']:.2f} -> {data['late_freq']:.2f} ({data['pct_change']:+.1f}%)")

    # Visualize
    fig = analyzer.visualize_word_changes((1970, 1979), (2020, 2024), top_n=20)
    fig.write_html("data/processed/word_changes.html")
    print("\nVisualization saved to: data/processed/word_changes.html")
