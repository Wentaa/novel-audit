import chromadb
from chromadb.config import Settings as ChromaSettings
from typing import List, Dict, Any, Optional
import logging
import uuid

from ..config.settings import settings
from ..services.openai_service import openai_service

logger = logging.getLogger(__name__)


class VectorStore:
    """ChromaDB vector store for audit cases and examples"""

    def __init__(self):
        self.client = None
        self.collection = None
        self.collection_name = settings.chromadb_collection_name
        self.is_connected = False

    async def initialize(self):
        """
        Initialize ChromaDB connection and collection
        """
        try:
            # Connect to ChromaDB server
            self.client = chromadb.HttpClient(
                host=settings.chromadb_host,
                port=settings.chromadb_port,
                settings=ChromaSettings(
                    allow_reset=True,
                    anonymized_telemetry=False
                )
            )

            # Get or create collection
            try:
                self.collection = self.client.get_collection(
                    name=self.collection_name
                )
                logger.info(f"Connected to existing collection: {self.collection_name}")
            except Exception:
                # Collection doesn't exist, create it
                self.collection = self.client.create_collection(
                    name=self.collection_name,
                    metadata={"description": "Audit cases and precedents for RAG enhancement"}
                )
                logger.info(f"Created new collection: {self.collection_name}")

            self.is_connected = True
            logger.info("ChromaDB initialization successful")

        except Exception as e:
            logger.error(f"ChromaDB initialization failed: {e}")
            self.is_connected = False
            raise

    async def add_case(
        self,
        content: str,
        result: str,
        reason: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Add audit case to vector store

        Args:
            content: Original content that was audited
            result: Audit result (approved/rejected)
            reason: Reasoning for the audit decision
            metadata: Additional metadata

        Returns:
            Case ID
        """
        if not self.is_connected:
            raise RuntimeError("VectorStore not initialized")

        try:
            case_id = str(uuid.uuid4())

            # Generate embedding for content
            embeddings = await openai_service.generate_embeddings([content])

            # Prepare metadata
            case_metadata = {
                "result": result,
                "reason": reason,
                "content_length": len(content),
                **(metadata or {})
            }

            # Add to collection
            self.collection.add(
                ids=[case_id],
                embeddings=embeddings,
                documents=[content],
                metadatas=[case_metadata]
            )

            logger.info(f"Added audit case: {case_id}")
            return case_id

        except Exception as e:
            logger.error(f"Failed to add case: {e}")
            raise

    async def search_similar_cases(
        self,
        query_content: str,
        n_results: int = 5,
        result_filter: Optional[str] = None,
        similarity_threshold: float = 0.0,
        genre_filter: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Search for similar audit cases with enhanced filtering

        Args:
            query_content: Content to find similar cases for
            n_results: Number of results to return
            result_filter: Filter by result type (approved/rejected)
            similarity_threshold: Minimum similarity score to include
            genre_filter: Filter by content genre

        Returns:
            List of similar cases with metadata and similarity scores
        """
        if not self.is_connected:
            raise RuntimeError("VectorStore not initialized")

        try:
            # Generate embedding for query
            query_embeddings = await openai_service.generate_embeddings([query_content])

            # Prepare filter conditions
            where_conditions = {}
            if result_filter:
                where_conditions["result"] = result_filter
            if genre_filter:
                where_conditions["genre"] = genre_filter

            # Search similar cases
            results = self.collection.query(
                query_embeddings=query_embeddings,
                n_results=min(n_results * 3, 50),  # Get more results for filtering
                where=where_conditions if where_conditions else None,
                include=["documents", "metadatas", "distances"]
            )

            # Format and filter results
            similar_cases = []
            if results["documents"] and results["documents"][0]:
                for i, doc in enumerate(results["documents"][0]):
                    similarity = 1 - results["distances"][0][i]  # Convert distance to similarity

                    # Apply similarity threshold
                    if similarity < similarity_threshold:
                        continue

                    case = {
                        "content": doc,
                        "metadata": results["metadatas"][0][i],
                        "similarity": similarity,
                        "distance": results["distances"][0][i],
                        "relevance_score": self._calculate_relevance_score(
                            similarity, results["metadatas"][0][i], query_content
                        )
                    }
                    similar_cases.append(case)

                # Sort by relevance score and limit results
                similar_cases.sort(key=lambda x: x["relevance_score"], reverse=True)
                similar_cases = similar_cases[:n_results]

            logger.info(f"Found {len(similar_cases)} similar cases")
            return similar_cases

        except Exception as e:
            logger.error(f"Failed to search similar cases: {e}")
            raise

    async def get_collection_stats(self) -> Dict[str, Any]:
        """
        Get collection statistics

        Returns:
            Dictionary with collection information
        """
        if not self.is_connected:
            return {"status": "not_connected"}

        try:
            count = self.collection.count()
            return {
                "status": "connected",
                "collection_name": self.collection_name,
                "total_cases": count
            }

        except Exception as e:
            logger.error(f"Failed to get collection stats: {e}")
            return {"status": "error", "error": str(e)}

    async def test_connection(self) -> bool:
        """
        Test ChromaDB connection

        Returns:
            True if connection successful, False otherwise
        """
        try:
            if not self.client:
                await self.initialize()

            # Simple test query
            test_embedding = await openai_service.generate_embeddings(["test"])
            self.collection.query(
                query_embeddings=test_embedding,
                n_results=1
            )

            logger.info("ChromaDB connection test successful")
            return True

        except Exception as e:
            logger.error(f"ChromaDB connection test failed: {e}")
            return False

    async def reset_collection(self):
        """
        Reset collection (delete all data)
        WARNING: This will delete all audit cases
        """
        if not self.is_connected:
            raise RuntimeError("VectorStore not initialized")

        try:
            self.client.delete_collection(name=self.collection_name)
            self.collection = self.client.create_collection(
                name=self.collection_name,
                metadata={"description": "Audit cases and precedents for RAG enhancement"}
            )
            logger.warning(f"Collection {self.collection_name} has been reset")

        except Exception as e:
            logger.error(f"Failed to reset collection: {e}")
            raise

    def _calculate_relevance_score(
        self,
        similarity: float,
        metadata: Dict[str, Any],
        query_content: str
    ) -> float:
        """
        Calculate relevance score combining similarity and metadata factors

        Args:
            similarity: Vector similarity score
            metadata: Case metadata
            query_content: Original query content

        Returns:
            Relevance score (0-1)
        """
        try:
            # Base score from similarity
            relevance = similarity * 0.7

            # Boost for content length similarity
            case_length = metadata.get("content_length", 0)
            query_length = len(query_content)
            if case_length > 0 and query_length > 0:
                length_ratio = min(case_length, query_length) / max(case_length, query_length)
                relevance += length_ratio * 0.1

            # Boost for recency (newer cases are more relevant)
            case_date = metadata.get("created_at")
            if case_date:
                try:
                    from datetime import datetime, timedelta
                    case_datetime = datetime.fromisoformat(case_date.replace('Z', '+00:00'))
                    days_old = (datetime.now() - case_datetime.replace(tzinfo=None)).days
                    recency_boost = max(0, (30 - days_old) / 30 * 0.1)  # Boost for cases < 30 days old
                    relevance += recency_boost
                except:
                    pass

            # Boost for high confidence cases
            case_confidence = metadata.get("confidence", 0.5)
            if case_confidence > 0.8:
                relevance += 0.1

            return min(1.0, relevance)

        except Exception as e:
            logger.error(f"Relevance score calculation failed: {e}")
            return similarity

    async def add_training_cases(self, training_cases: List[Dict[str, Any]]) -> List[str]:
        """
        Add multiple training cases to the vector store

        Args:
            training_cases: List of training case dictionaries

        Returns:
            List of case IDs that were added
        """
        if not self.is_connected:
            raise RuntimeError("VectorStore not initialized")

        case_ids = []

        try:
            for case in training_cases:
                case_id = await self.add_case(
                    content=case.get("content", ""),
                    result=case.get("result", "unknown"),
                    reason=case.get("reason", ""),
                    metadata=case.get("metadata", {})
                )
                case_ids.append(case_id)

            logger.info(f"Added {len(case_ids)} training cases to vector store")
            return case_ids

        except Exception as e:
            logger.error(f"Failed to add training cases: {e}")
            raise

    async def search_by_keywords(
        self,
        keywords: List[str],
        n_results: int = 10,
        result_filter: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Search for cases containing specific keywords

        Args:
            keywords: List of keywords to search for
            n_results: Number of results to return
            result_filter: Filter by result type

        Returns:
            List of cases containing the keywords
        """
        if not self.is_connected:
            raise RuntimeError("VectorStore not initialized")

        try:
            # Create keyword-based query
            keyword_query = " ".join(keywords)
            return await self.search_similar_cases(
                query_content=keyword_query,
                n_results=n_results,
                result_filter=result_filter
            )

        except Exception as e:
            logger.error(f"Keyword search failed: {e}")
            raise

    async def get_case_distribution(self) -> Dict[str, Any]:
        """
        Get distribution of cases by various categories

        Returns:
            Dictionary with case distribution statistics
        """
        if not self.is_connected:
            return {"status": "not_connected"}

        try:
            # Get all cases (limited sample for analysis)
            all_cases = self.collection.query(
                query_embeddings=None,
                n_results=1000,  # Sample size
                include=["metadatas"]
            )

            if not all_cases["metadatas"] or not all_cases["metadatas"][0]:
                return {"status": "no_cases"}

            metadatas = all_cases["metadatas"][0]

            # Analyze distribution
            result_distribution = {}
            genre_distribution = {}
            confidence_ranges = {"high": 0, "medium": 0, "low": 0}

            for metadata in metadatas:
                # Result distribution
                result = metadata.get("result", "unknown")
                result_distribution[result] = result_distribution.get(result, 0) + 1

                # Genre distribution
                genre = metadata.get("genre", "unknown")
                genre_distribution[genre] = genre_distribution.get(genre, 0) + 1

                # Confidence distribution
                confidence = metadata.get("confidence", 0.5)
                if confidence >= 0.8:
                    confidence_ranges["high"] += 1
                elif confidence >= 0.6:
                    confidence_ranges["medium"] += 1
                else:
                    confidence_ranges["low"] += 1

            return {
                "status": "success",
                "total_cases_analyzed": len(metadatas),
                "result_distribution": result_distribution,
                "genre_distribution": genre_distribution,
                "confidence_distribution": confidence_ranges,
                "analysis_timestamp": datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"Failed to get case distribution: {e}")
            return {"status": "error", "error": str(e)}


# Global vector store instance
vector_store = VectorStore()