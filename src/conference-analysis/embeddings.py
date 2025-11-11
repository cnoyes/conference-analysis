"""
Embeddings-based analysis for General Conference talks.

This module demonstrates how to use embeddings for deeper semantic understanding
beyond simple keyword matching. Embeddings capture the meaning of text in a way
that allows us to find similar concepts even when different words are used.

Key concepts:
- Embeddings: Dense vector representations of text that capture semantic meaning
- Semantic similarity: Finding texts with similar meanings (not just similar words)
- Topic clustering: Grouping talks by underlying themes
- Semantic search: Finding talks relevant to a concept, not just keywords
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Tuple, Optional
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.cluster import KMeans, DBSCAN
from sklearn.decomposition import PCA
import matplotlib.pyplot as plt
import seaborn as sns
import plotly.express as px
import plotly.graph_objects as go
from tqdm import tqdm
import logging
import pickle
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class EmbeddingsAnalyzer:
    """
    Analyze conference talks using embeddings.

    Embeddings are vector representations of text that capture semantic meaning.
    Unlike word counts or TF-IDF, embeddings understand that "car" and "automobile"
    are similar, or that "I'm happy" and "I'm joyful" convey similar sentiment.
    """

    def __init__(
        self,
        talks_df: pd.DataFrame,
        model_name: str = 'all-MiniLM-L6-v2',
        cache_dir: Optional[str] = None
    ):
        """
        Initialize the embeddings analyzer.

        Args:
            talks_df: DataFrame with talks data
            model_name: Name of sentence-transformers model to use
                       'all-MiniLM-L6-v2' is fast and good for general purpose
                       'all-mpnet-base-v2' is slower but more accurate
            cache_dir: Directory to cache embeddings
        """
        self.talks_df = talks_df.copy()
        self.model_name = model_name
        self.cache_dir = Path(cache_dir) if cache_dir else Path('data/processed')
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Loading embedding model: {model_name}")
        self.model = SentenceTransformer(model_name)

        self.embeddings = None
        self.embedding_cache_path = self.cache_dir / f'embeddings_{model_name}.pkl'

    def generate_embeddings(self, force_recompute: bool = False) -> np.ndarray:
        """
        Generate embeddings for all talks.

        This is the core step that converts text into vectors. Each talk becomes
        a point in high-dimensional space, where similar talks are close together.

        Args:
            force_recompute: If True, recompute even if cache exists

        Returns:
            Array of shape (n_talks, embedding_dim) with talk embeddings
        """
        # Try to load from cache
        if not force_recompute and self.embedding_cache_path.exists():
            logger.info(f"Loading embeddings from cache: {self.embedding_cache_path}")
            with open(self.embedding_cache_path, 'rb') as f:
                self.embeddings = pickle.load(f)
            logger.info(f"Loaded embeddings with shape: {self.embeddings.shape}")
            return self.embeddings

        # Generate embeddings
        logger.info(f"Generating embeddings for {len(self.talks_df)} talks...")
        logger.info("This may take a few minutes on first run...")

        # Combine title and text for richer embeddings
        texts = []
        for _, row in self.talks_df.iterrows():
            text = f"{row['title']}\n\n{row['text'][:1000]}"  # Use first 1000 chars
            texts.append(text)

        # Generate embeddings with progress bar
        self.embeddings = self.model.encode(
            texts,
            show_progress_bar=True,
            batch_size=32
        )

        # Cache for future use
        with open(self.embedding_cache_path, 'wb') as f:
            pickle.dump(self.embeddings, f)
        logger.info(f"Saved embeddings to cache: {self.embedding_cache_path}")

        return self.embeddings

    def semantic_search(
        self,
        query: str,
        top_k: int = 10,
        year_range: Optional[Tuple[int, int]] = None
    ) -> pd.DataFrame:
        """
        Find talks semantically similar to a query.

        This is more powerful than keyword search because it finds talks that
        discuss the same concept even if they use different words.

        Example: Searching for "overcoming adversity" will find talks about
        "enduring trials", "facing challenges", etc.

        Args:
            query: Search query (can be a sentence or concept)
            top_k: Number of results to return
            year_range: Optional (min_year, max_year) to filter results

        Returns:
            DataFrame with top matching talks and similarity scores
        """
        if self.embeddings is None:
            self.generate_embeddings()

        # Encode the query
        query_embedding = self.model.encode([query])[0]

        # Calculate similarity with all talks
        similarities = cosine_similarity(
            query_embedding.reshape(1, -1),
            self.embeddings
        )[0]

        # Add similarity scores to dataframe
        results_df = self.talks_df.copy()
        results_df['similarity'] = similarities

        # Filter by year if specified
        if year_range:
            min_year, max_year = year_range
            results_df['year'] = pd.to_datetime(results_df['date']).dt.year
            results_df = results_df[
                (results_df['year'] >= min_year) &
                (results_df['year'] <= max_year)
            ]

        # Sort by similarity and return top k
        results_df = results_df.sort_values('similarity', ascending=False).head(top_k)

        return results_df[['date', 'speaker', 'title', 'similarity', 'href']]

    def find_similar_talks(
        self,
        talk_index: int,
        top_k: int = 10,
        exclude_same_speaker: bool = False
    ) -> pd.DataFrame:
        """
        Find talks similar to a given talk.

        Useful for discovering related content or seeing how themes recur.

        Args:
            talk_index: Index of the reference talk
            top_k: Number of similar talks to return
            exclude_same_speaker: If True, exclude talks by the same speaker

        Returns:
            DataFrame with similar talks and similarity scores
        """
        if self.embeddings is None:
            self.generate_embeddings()

        # Get embedding for the reference talk
        ref_embedding = self.embeddings[talk_index].reshape(1, -1)

        # Calculate similarities
        similarities = cosine_similarity(ref_embedding, self.embeddings)[0]

        results_df = self.talks_df.copy()
        results_df['similarity'] = similarities

        # Exclude the reference talk itself
        results_df = results_df[results_df.index != talk_index]

        # Optionally exclude same speaker
        if exclude_same_speaker:
            ref_speaker = self.talks_df.iloc[talk_index]['speaker']
            results_df = results_df[results_df['speaker'] != ref_speaker]

        # Sort and return top k
        results_df = results_df.sort_values('similarity', ascending=False).head(top_k)

        return results_df[['date', 'speaker', 'title', 'similarity', 'href']]

    def cluster_talks(
        self,
        n_clusters: int = 10,
        method: str = 'kmeans'
    ) -> pd.DataFrame:
        """
        Group talks into thematic clusters.

        This discovers natural groupings of talks based on their content,
        revealing common themes across all of General Conference history.

        Args:
            n_clusters: Number of clusters to create
            method: Clustering method ('kmeans' or 'dbscan')

        Returns:
            DataFrame with cluster assignments
        """
        if self.embeddings is None:
            self.generate_embeddings()

        if method == 'kmeans':
            clusterer = KMeans(n_clusters=n_clusters, random_state=42)
        elif method == 'dbscan':
            clusterer = DBSCAN(eps=0.5, min_samples=5)
        else:
            raise ValueError(f"Unknown method: {method}")

        logger.info(f"Clustering {len(self.embeddings)} talks into {n_clusters} clusters...")
        cluster_labels = clusterer.fit_predict(self.embeddings)

        results_df = self.talks_df.copy()
        results_df['cluster'] = cluster_labels

        return results_df

    def get_cluster_summary(
        self,
        clustered_df: pd.DataFrame,
        cluster_id: int,
        top_n: int = 10
    ) -> Dict:
        """
        Get a summary of a cluster.

        Args:
            clustered_df: DataFrame with cluster assignments
            cluster_id: ID of cluster to summarize
            top_n: Number of representative talks to show

        Returns:
            Dictionary with cluster summary information
        """
        cluster_talks = clustered_df[clustered_df['cluster'] == cluster_id]

        # Get cluster center (mean of embeddings)
        cluster_indices = cluster_talks.index
        cluster_embeddings = self.embeddings[cluster_indices]
        cluster_center = cluster_embeddings.mean(axis=0).reshape(1, -1)

        # Find most central talks
        distances = cosine_similarity(cluster_center, cluster_embeddings)[0]
        central_indices = cluster_indices[np.argsort(-distances)[:top_n]]

        return {
            'cluster_id': cluster_id,
            'size': len(cluster_talks),
            'date_range': (
                cluster_talks['date'].min(),
                cluster_talks['date'].max()
            ),
            'representative_talks': self.talks_df.iloc[central_indices][
                ['date', 'speaker', 'title']
            ].to_dict('records'),
            'top_speakers': cluster_talks['speaker'].value_counts().head(5).to_dict()
        }

    def visualize_embeddings_2d(
        self,
        color_by: str = 'year',
        sample_size: Optional[int] = None,
        method: str = 'pca'
    ):
        """
        Visualize talk embeddings in 2D space.

        This helps you see how talks cluster and relate to each other.

        Args:
            color_by: Column to use for coloring points ('year', 'speaker', 'cluster')
            sample_size: Number of talks to sample (None for all)
            method: Dimensionality reduction method ('pca' or 'tsne')

        Returns:
            Plotly figure
        """
        if self.embeddings is None:
            self.generate_embeddings()

        embeddings = self.embeddings
        df = self.talks_df.copy()

        # Sample if requested
        if sample_size and sample_size < len(df):
            indices = np.random.choice(len(df), sample_size, replace=False)
            embeddings = embeddings[indices]
            df = df.iloc[indices]

        # Reduce to 2D
        logger.info(f"Reducing embeddings to 2D using {method}...")
        if method == 'pca':
            reducer = PCA(n_components=2, random_state=42)
            embeddings_2d = reducer.fit_transform(embeddings)
        elif method == 'tsne':
            from sklearn.manifold import TSNE
            reducer = TSNE(n_components=2, random_state=42)
            embeddings_2d = reducer.fit_transform(embeddings)
        else:
            raise ValueError(f"Unknown method: {method}")

        # Create visualization dataframe
        viz_df = df.copy()
        viz_df['x'] = embeddings_2d[:, 0]
        viz_df['y'] = embeddings_2d[:, 1]

        if color_by == 'year':
            viz_df['year'] = pd.to_datetime(viz_df['date']).dt.year
            color_col = 'year'
        elif color_by == 'decade':
            viz_df['decade'] = (pd.to_datetime(viz_df['date']).dt.year // 10) * 10
            color_col = 'decade'
        else:
            color_col = color_by

        # Create interactive plot
        fig = px.scatter(
            viz_df,
            x='x',
            y='y',
            color=color_col,
            hover_data=['title', 'speaker', 'date'],
            title=f'Conference Talks Embedding Space (colored by {color_by})'
        )

        fig.update_traces(marker=dict(size=5, opacity=0.6))
        fig.update_layout(
            xaxis_title=f'{method.upper()} Component 1',
            yaxis_title=f'{method.upper()} Component 2'
        )

        return fig

    def temporal_semantic_shift(
        self,
        concept: str,
        time_periods: List[Tuple[int, int]],
        top_k: int = 20
    ) -> pd.DataFrame:
        """
        Analyze how talks related to a concept change over time.

        This combines embeddings with temporal analysis to show how the discussion
        of a concept evolves across different eras.

        Args:
            concept: Concept to track (e.g., "faith", "service")
            time_periods: List of (start_year, end_year) tuples
            top_k: Number of top talks per period

        Returns:
            DataFrame with top talks for each period
        """
        results = []

        for start_year, end_year in time_periods:
            period_results = self.semantic_search(
                query=concept,
                top_k=top_k,
                year_range=(start_year, end_year)
            )
            period_results['period'] = f"{start_year}-{end_year}"
            results.append(period_results)

        return pd.concat(results, ignore_index=True)


if __name__ == "__main__":
    # Example usage demonstrating embeddings concepts

    # Load data
    talks = pd.read_csv("data/raw/talks.csv")

    # Initialize analyzer
    analyzer = EmbeddingsAnalyzer(talks, cache_dir="data/processed")

    # Generate embeddings (cached for reuse)
    analyzer.generate_embeddings()

    # Example 1: Semantic search
    print("\n=== SEMANTIC SEARCH DEMO ===")
    print("Query: 'overcoming adversity and trials'")
    results = analyzer.semantic_search("overcoming adversity and trials", top_k=5)
    print(results[['date', 'speaker', 'title', 'similarity']])

    # Example 2: Find similar talks
    print("\n=== SIMILAR TALKS DEMO ===")
    print("Finding talks similar to first talk...")
    similar = analyzer.find_similar_talks(0, top_k=5)
    print(similar[['date', 'speaker', 'title', 'similarity']])

    # Example 3: Clustering
    print("\n=== CLUSTERING DEMO ===")
    clustered = analyzer.cluster_talks(n_clusters=10)
    summary = analyzer.get_cluster_summary(clustered, cluster_id=0)
    print(f"Cluster 0: {summary['size']} talks")
    print(f"Representative talks:")
    for talk in summary['representative_talks'][:3]:
        print(f"  - {talk['title']} by {talk['speaker']}")

    # Example 4: Visualization
    print("\n=== CREATING VISUALIZATION ===")
    fig = analyzer.visualize_embeddings_2d(color_by='decade', sample_size=500)
    fig.write_html("data/processed/embeddings_visualization.html")
    print("Saved to data/processed/embeddings_visualization.html")
