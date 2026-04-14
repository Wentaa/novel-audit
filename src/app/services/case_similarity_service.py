from typing import Dict, Any, List, Tuple, Optional
import re
import math
from datetime import datetime
import logging

from ..services.openai_service import openai_service

logger = logging.getLogger(__name__)


class CaseSimilarityService:
    """Advanced case similarity matching algorithms for RAG enhancement"""

    def __init__(self):
        # Similarity weights for different aspects
        self.similarity_weights = {
            "semantic": 0.40,      # Vector embedding similarity
            "lexical": 0.20,       # Text-based similarity (keywords, n-grams)
            "structural": 0.15,    # Content structure similarity
            "contextual": 0.15,    # Context and genre similarity
            "outcome": 0.10        # Historical outcome patterns
        }

        # Preprocessing patterns
        self.preprocessing_patterns = {
            "punctuation": re.compile(r'[^\w\s]'),
            "whitespace": re.compile(r'\s+'),
            "numbers": re.compile(r'\d+')
        }

    async def calculate_multi_dimensional_similarity(
        self,
        query_content: str,
        candidate_cases: List[Dict[str, Any]],
        query_metadata: Dict[str, Any] = None
    ) -> List[Dict[str, Any]]:
        """
        Calculate comprehensive similarity scores using multiple dimensions

        Args:
            query_content: Content to compare against
            candidate_cases: List of candidate cases from vector search
            query_metadata: Metadata about the query content

        Returns:
            Enhanced cases with detailed similarity scores
        """
        try:
            logger.info(f"Calculating multi-dimensional similarity for {len(candidate_cases)} cases")

            enhanced_cases = []

            for case in candidate_cases:
                case_content = case.get("content", "")
                case_metadata = case.get("metadata", {})

                # Calculate different similarity dimensions
                similarities = {
                    "semantic": case.get("similarity", 0.0),  # Already calculated from vector search
                    "lexical": await self._calculate_lexical_similarity(query_content, case_content),
                    "structural": self._calculate_structural_similarity(query_content, case_content),
                    "contextual": self._calculate_contextual_similarity(query_metadata or {}, case_metadata),
                    "outcome": self._calculate_outcome_similarity(query_metadata or {}, case_metadata)
                }

                # Calculate weighted composite similarity
                composite_similarity = sum(
                    similarities[dim] * self.similarity_weights[dim]
                    for dim in similarities.keys()
                )

                # Calculate confidence in similarity assessment
                similarity_confidence = self._calculate_similarity_confidence(similarities)

                # Enhanced case with detailed similarity breakdown
                enhanced_case = case.copy()
                enhanced_case.update({
                    "similarity_breakdown": similarities,
                    "composite_similarity": composite_similarity,
                    "similarity_confidence": similarity_confidence,
                    "similarity_factors": self._identify_similarity_factors(similarities, query_content, case_content)
                })

                enhanced_cases.append(enhanced_case)

            # Sort by composite similarity
            enhanced_cases.sort(key=lambda x: x["composite_similarity"], reverse=True)

            logger.info(f"Enhanced similarity analysis completed")
            return enhanced_cases

        except Exception as e:
            logger.error(f"Multi-dimensional similarity calculation failed: {e}")
            # Return original cases with basic similarity
            return candidate_cases

    async def _calculate_lexical_similarity(self, text1: str, text2: str) -> float:
        """Calculate lexical similarity using multiple text-based metrics"""
        try:
            # Preprocess texts
            processed_text1 = self._preprocess_text(text1)
            processed_text2 = self._preprocess_text(text2)

            # Calculate different lexical similarities
            jaccard_sim = self._jaccard_similarity(processed_text1, processed_text2)
            ngram_sim = self._ngram_similarity(processed_text1, processed_text2, n=2)
            keyword_sim = await self._keyword_similarity(text1, text2)

            # Weighted combination
            lexical_similarity = (
                jaccard_sim * 0.4 +
                ngram_sim * 0.4 +
                keyword_sim * 0.2
            )

            return min(1.0, lexical_similarity)

        except Exception as e:
            logger.error(f"Lexical similarity calculation failed: {e}")
            return 0.0

    def _calculate_structural_similarity(self, text1: str, text2: str) -> float:
        """Calculate structural similarity based on content organization"""
        try:
            # Analyze text structure
            structure1 = self._analyze_text_structure(text1)
            structure2 = self._analyze_text_structure(text2)

            similarities = []

            # Length similarity
            len_sim = min(len(text1), len(text2)) / max(len(text1), len(text2)) if max(len(text1), len(text2)) > 0 else 0
            similarities.append(len_sim)

            # Paragraph count similarity
            para_sim = min(structure1["paragraphs"], structure2["paragraphs"]) / max(structure1["paragraphs"], structure2["paragraphs"]) if max(structure1["paragraphs"], structure2["paragraphs"]) > 0 else 0
            similarities.append(para_sim)

            # Sentence length distribution similarity
            sent_sim = self._compare_sentence_distributions(structure1["avg_sentence_length"], structure2["avg_sentence_length"])
            similarities.append(sent_sim)

            # Dialogue density similarity
            dialogue_sim = 1.0 - abs(structure1["dialogue_ratio"] - structure2["dialogue_ratio"])
            similarities.append(dialogue_sim)

            return sum(similarities) / len(similarities)

        except Exception as e:
            logger.error(f"Structural similarity calculation failed: {e}")
            return 0.5

    def _calculate_contextual_similarity(self, metadata1: Dict[str, Any], metadata2: Dict[str, Any]) -> float:
        """Calculate contextual similarity based on metadata"""
        try:
            similarities = []

            # Genre similarity
            genre1 = metadata1.get("genre", "unknown")
            genre2 = metadata2.get("genre", "unknown")
            genre_sim = 1.0 if genre1 == genre2 else 0.5 if genre1 != "unknown" and genre2 != "unknown" else 0.3
            similarities.append(genre_sim)

            # Target audience similarity
            audience1 = metadata1.get("target_audience", "general")
            audience2 = metadata2.get("target_audience", "general")
            audience_sim = 1.0 if audience1 == audience2 else 0.7
            similarities.append(audience_sim)

            # Content tone similarity
            tone1 = metadata1.get("tone", "neutral")
            tone2 = metadata2.get("tone", "neutral")
            tone_sim = 1.0 if tone1 == tone2 else 0.6
            similarities.append(tone_sim)

            # Time period similarity (for recency weighting)
            created1 = metadata1.get("created_at")
            created2 = metadata2.get("created_at")
            if created1 and created2:
                try:
                    date1 = datetime.fromisoformat(created1.replace('Z', '+00:00'))
                    date2 = datetime.fromisoformat(created2.replace('Z', '+00:00'))
                    days_diff = abs((date1 - date2).days)
                    time_sim = max(0.5, 1.0 - days_diff / 365)  # Decay over a year
                    similarities.append(time_sim)
                except:
                    similarities.append(0.7)  # Default if date parsing fails

            return sum(similarities) / len(similarities)

        except Exception as e:
            logger.error(f"Contextual similarity calculation failed: {e}")
            return 0.5

    def _calculate_outcome_similarity(self, metadata1: Dict[str, Any], metadata2: Dict[str, Any]) -> float:
        """Calculate outcome pattern similarity"""
        try:
            # This is primarily used to weight cases based on outcome patterns
            result1 = metadata1.get("result", "unknown")
            result2 = metadata2.get("result", "unknown")

            # Same outcomes are more similar for pattern learning
            if result1 == result2:
                base_similarity = 0.8
            else:
                base_similarity = 0.4

            # Confidence similarity
            conf1 = metadata1.get("confidence", 0.5)
            conf2 = metadata2.get("confidence", 0.5)
            conf_sim = 1.0 - abs(conf1 - conf2)

            return (base_similarity + conf_sim) / 2

        except Exception as e:
            logger.error(f"Outcome similarity calculation failed: {e}")
            return 0.5

    def _preprocess_text(self, text: str) -> str:
        """Preprocess text for lexical similarity analysis"""
        try:
            # Convert to lowercase
            processed = text.lower()

            # Remove punctuation
            processed = self.preprocessing_patterns["punctuation"].sub(' ', processed)

            # Normalize whitespace
            processed = self.preprocessing_patterns["whitespace"].sub(' ', processed)

            # Remove numbers (optional - might want to keep them for some cases)
            # processed = self.preprocessing_patterns["numbers"].sub('', processed)

            return processed.strip()

        except Exception as e:
            logger.error(f"Text preprocessing failed: {e}")
            return text.lower()

    def _jaccard_similarity(self, text1: str, text2: str) -> float:
        """Calculate Jaccard similarity between two texts"""
        try:
            words1 = set(text1.split())
            words2 = set(text2.split())

            if not words1 and not words2:
                return 1.0

            intersection = len(words1.intersection(words2))
            union = len(words1.union(words2))

            return intersection / union if union > 0 else 0.0

        except Exception as e:
            logger.error(f"Jaccard similarity calculation failed: {e}")
            return 0.0

    def _ngram_similarity(self, text1: str, text2: str, n: int = 2) -> float:
        """Calculate n-gram similarity between two texts"""
        try:
            def get_ngrams(text: str, n: int) -> set:
                words = text.split()
                return set(tuple(words[i:i+n]) for i in range(len(words)-n+1))

            ngrams1 = get_ngrams(text1, n)
            ngrams2 = get_ngrams(text2, n)

            if not ngrams1 and not ngrams2:
                return 1.0

            intersection = len(ngrams1.intersection(ngrams2))
            union = len(ngrams1.union(ngrams2))

            return intersection / union if union > 0 else 0.0

        except Exception as e:
            logger.error(f"N-gram similarity calculation failed: {e}")
            return 0.0

    async def _keyword_similarity(self, text1: str, text2: str) -> float:
        """Calculate keyword-based similarity using important terms"""
        try:
            # Extract key terms from both texts
            keywords1 = await self._extract_key_terms(text1)
            keywords2 = await self._extract_key_terms(text2)

            if not keywords1 and not keywords2:
                return 1.0

            # Calculate overlap of key terms
            common_keywords = set(keywords1).intersection(set(keywords2))
            total_keywords = set(keywords1).union(set(keywords2))

            return len(common_keywords) / len(total_keywords) if total_keywords else 0.0

        except Exception as e:
            logger.error(f"Keyword similarity calculation failed: {e}")
            return 0.0

    async def _extract_key_terms(self, text: str, max_terms: int = 10) -> List[str]:
        """Extract key terms from text using simple frequency analysis"""
        try:
            # Simple frequency-based extraction (could be enhanced with TF-IDF or LLM)
            words = self._preprocess_text(text).split()

            # Filter out common stop words
            stop_words = {"the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "of", "with", "by", "is", "was", "are", "were", "be", "been", "have", "has", "had", "do", "does", "did", "will", "would", "could", "should", "may", "might", "can", "must", "shall", "this", "that", "these", "those", "i", "you", "he", "she", "it", "we", "they", "me", "him", "her", "us", "them", "my", "your", "his", "her", "its", "our", "their"}

            # Count word frequencies
            word_freq = {}
            for word in words:
                if word not in stop_words and len(word) > 2:
                    word_freq[word] = word_freq.get(word, 0) + 1

            # Sort by frequency and return top terms
            sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
            return [word for word, freq in sorted_words[:max_terms]]

        except Exception as e:
            logger.error(f"Key term extraction failed: {e}")
            return []

    def _analyze_text_structure(self, text: str) -> Dict[str, Any]:
        """Analyze the structural characteristics of text"""
        try:
            paragraphs = text.split('\n\n')
            sentences = re.split(r'[.!?]+', text)
            sentences = [s.strip() for s in sentences if s.strip()]

            # Count dialogue (rough estimate)
            dialogue_patterns = ['"', "'", "「", "」"]
            dialogue_count = sum(text.count(pattern) for pattern in dialogue_patterns)

            structure = {
                "total_length": len(text),
                "word_count": len(text.split()),
                "paragraphs": len([p for p in paragraphs if p.strip()]),
                "sentences": len(sentences),
                "avg_sentence_length": sum(len(s.split()) for s in sentences) / len(sentences) if sentences else 0,
                "dialogue_ratio": min(1.0, dialogue_count / len(text) * 100) if text else 0
            }

            return structure

        except Exception as e:
            logger.error(f"Text structure analysis failed: {e}")
            return {
                "total_length": len(text),
                "word_count": len(text.split()),
                "paragraphs": 1,
                "sentences": 1,
                "avg_sentence_length": len(text.split()),
                "dialogue_ratio": 0.0
            }

    def _compare_sentence_distributions(self, avg1: float, avg2: float) -> float:
        """Compare sentence length distributions"""
        try:
            if avg1 == 0 and avg2 == 0:
                return 1.0

            max_avg = max(avg1, avg2)
            min_avg = min(avg1, avg2)

            return min_avg / max_avg if max_avg > 0 else 0.0

        except Exception as e:
            logger.error(f"Sentence distribution comparison failed: {e}")
            return 0.5

    def _calculate_similarity_confidence(self, similarities: Dict[str, float]) -> float:
        """Calculate confidence in the overall similarity assessment"""
        try:
            # Check agreement between different similarity measures
            sim_values = list(similarities.values())

            # Calculate variance (lower variance = higher confidence)
            mean_sim = sum(sim_values) / len(sim_values)
            variance = sum((x - mean_sim) ** 2 for x in sim_values) / len(sim_values)

            # Convert variance to confidence (inverse relationship)
            confidence = 1.0 - min(1.0, variance * 2)  # Scale variance to 0-1 range

            # Boost confidence for high overall similarity
            if mean_sim > 0.8:
                confidence = min(1.0, confidence + 0.1)

            return confidence

        except Exception as e:
            logger.error(f"Similarity confidence calculation failed: {e}")
            return 0.5

    def _identify_similarity_factors(
        self,
        similarities: Dict[str, float],
        query_content: str,
        case_content: str
    ) -> List[Dict[str, Any]]:
        """Identify key factors contributing to similarity"""
        try:
            factors = []

            # Identify strongest similarity dimensions
            for dimension, score in similarities.items():
                if score > 0.7:
                    factors.append({
                        "factor": dimension,
                        "strength": "high",
                        "score": score,
                        "description": self._get_similarity_description(dimension, score)
                    })
                elif score > 0.5:
                    factors.append({
                        "factor": dimension,
                        "strength": "medium",
                        "score": score,
                        "description": self._get_similarity_description(dimension, score)
                    })

            # Add content-specific observations
            if len(query_content) > 0 and len(case_content) > 0:
                length_ratio = min(len(query_content), len(case_content)) / max(len(query_content), len(case_content))
                if length_ratio > 0.8:
                    factors.append({
                        "factor": "content_length",
                        "strength": "high",
                        "score": length_ratio,
                        "description": "Similar content lengths suggest comparable scope"
                    })

            return factors

        except Exception as e:
            logger.error(f"Similarity factors identification failed: {e}")
            return []

    def _get_similarity_description(self, dimension: str, score: float) -> str:
        """Get human-readable description of similarity dimension"""
        descriptions = {
            "semantic": f"Strong semantic similarity ({score:.2f}) indicates similar meaning and concepts",
            "lexical": f"High lexical similarity ({score:.2f}) shows common vocabulary and phrasing",
            "structural": f"Similar structure ({score:.2f}) suggests comparable content organization",
            "contextual": f"Strong contextual match ({score:.2f}) indicates similar genre or setting",
            "outcome": f"Similar outcome patterns ({score:.2f}) suggest comparable decision factors"
        }

        return descriptions.get(dimension, f"{dimension} similarity: {score:.2f}")

    async def rank_cases_by_relevance(
        self,
        query_content: str,
        enhanced_cases: List[Dict[str, Any]],
        query_context: Dict[str, Any] = None
    ) -> List[Dict[str, Any]]:
        """
        Final ranking of cases by relevance for the specific query

        Args:
            query_content: Original query content
            enhanced_cases: Cases with similarity analysis
            query_context: Additional context about the query

        Returns:
            Cases ranked by final relevance score
        """
        try:
            logger.info(f"Ranking {len(enhanced_cases)} cases by relevance")

            for case in enhanced_cases:
                # Calculate final relevance score
                composite_sim = case.get("composite_similarity", 0.0)
                sim_confidence = case.get("similarity_confidence", 0.5)

                # Boost for high-confidence historical outcomes
                outcome_boost = 0.0
                case_confidence = case.get("metadata", {}).get("confidence", 0.5)
                if case_confidence > 0.8:
                    outcome_boost = 0.1

                # Recency boost
                recency_boost = self._calculate_recency_boost(case.get("metadata", {}))

                # Final relevance score
                final_relevance = (
                    composite_sim * 0.7 +
                    sim_confidence * 0.2 +
                    outcome_boost +
                    recency_boost
                )

                case["final_relevance_score"] = min(1.0, final_relevance)

            # Sort by final relevance
            ranked_cases = sorted(enhanced_cases, key=lambda x: x["final_relevance_score"], reverse=True)

            logger.info(f"Case ranking completed")
            return ranked_cases

        except Exception as e:
            logger.error(f"Case ranking failed: {e}")
            return enhanced_cases

    def _calculate_recency_boost(self, metadata: Dict[str, Any]) -> float:
        """Calculate boost based on case recency"""
        try:
            created_at = metadata.get("created_at")
            if not created_at:
                return 0.0

            case_date = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
            days_old = (datetime.now() - case_date.replace(tzinfo=None)).days

            # Boost recent cases (within 30 days)
            if days_old <= 7:
                return 0.05
            elif days_old <= 30:
                return 0.03
            else:
                return 0.0

        except Exception as e:
            logger.error(f"Recency boost calculation failed: {e}")
            return 0.0


# Global similarity service instance
case_similarity_service = CaseSimilarityService()