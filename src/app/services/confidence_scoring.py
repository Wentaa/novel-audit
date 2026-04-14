from typing import Dict, Any, List, Tuple, Optional
import math
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class ConfidenceScorer:
    """Advanced confidence scoring system for audit decisions"""

    def __init__(self):
        # Scoring weights for different factors
        self.weights = {
            "rule_clarity": 0.25,      # How clear the rule violation is
            "keyword_confidence": 0.20, # Confidence from keyword matching
            "context_analysis": 0.20,   # Contextual understanding
            "violation_severity": 0.15, # Severity of detected violations
            "content_ambiguity": 0.10,  # How ambiguous the content is
            "historical_consistency": 0.10  # Consistency with past decisions
        }

        # Confidence thresholds
        self.thresholds = {
            "very_high": 0.95,
            "high": 0.85,
            "medium_high": 0.75,
            "medium": 0.65,
            "medium_low": 0.55,
            "low": 0.45,
            "very_low": 0.35
        }

    def calculate_comprehensive_confidence(
        self,
        judgment_result: Dict[str, Any],
        content_analysis: Dict[str, Any],
        processing_context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Calculate comprehensive confidence score based on multiple factors

        Args:
            judgment_result: Initial judgment from Agent3
            content_analysis: Content analysis results
            processing_context: Additional processing context

        Returns:
            Detailed confidence analysis
        """
        try:
            logger.info("Calculating comprehensive confidence score...")

            # Extract base confidence from initial judgment
            base_confidence = judgment_result.get("confidence_score", 0.5)
            judgment = judgment_result.get("judgment", "uncertain")
            violations = judgment_result.get("violation_details", [])
            keywords = judgment_result.get("keyword_matches", [])

            # Calculate individual confidence factors
            factors = self._calculate_confidence_factors(
                judgment_result, content_analysis, processing_context or {}
            )

            # Calculate weighted confidence score
            weighted_confidence = self._calculate_weighted_confidence(factors)

            # Adjust based on judgment consistency
            consistency_adjusted = self._apply_consistency_adjustment(
                weighted_confidence, judgment, violations
            )

            # Calculate confidence bounds and uncertainty
            confidence_bounds = self._calculate_confidence_bounds(
                consistency_adjusted, factors
            )

            # Determine confidence level and recommendations
            confidence_level = self._determine_confidence_level(consistency_adjusted)
            recommendations = self._generate_confidence_recommendations(
                consistency_adjusted, confidence_level, factors
            )

            return {
                "final_confidence_score": consistency_adjusted,
                "base_confidence": base_confidence,
                "confidence_level": confidence_level,
                "confidence_factors": factors,
                "confidence_bounds": confidence_bounds,
                "uncertainty_metrics": self._calculate_uncertainty_metrics(factors),
                "recommendations": recommendations,
                "scoring_metadata": {
                    "scorer_version": "v1.0.0",
                    "timestamp": datetime.now().isoformat(),
                    "weights_used": self.weights,
                    "factors_count": len(factors)
                }
            }

        except Exception as e:
            logger.error(f"Confidence scoring failed: {e}")
            return self._get_fallback_confidence_result(base_confidence)

    def _calculate_confidence_factors(
        self,
        judgment_result: Dict[str, Any],
        content_analysis: Dict[str, Any],
        processing_context: Dict[str, Any]
    ) -> Dict[str, float]:
        """Calculate individual confidence factors"""

        factors = {}

        try:
            # Rule clarity factor
            factors["rule_clarity"] = self._calculate_rule_clarity_confidence(
                judgment_result.get("violation_details", [])
            )

            # Keyword confidence factor
            factors["keyword_confidence"] = self._calculate_keyword_confidence(
                judgment_result.get("keyword_matches", [])
            )

            # Context analysis factor
            factors["context_analysis"] = self._calculate_context_confidence(
                content_analysis, judgment_result.get("reasoning", "")
            )

            # Violation severity factor
            factors["violation_severity"] = self._calculate_severity_confidence(
                judgment_result.get("violation_details", [])
            )

            # Content ambiguity factor
            factors["content_ambiguity"] = self._calculate_ambiguity_confidence(
                content_analysis
            )

            # Historical consistency factor (placeholder for now)
            factors["historical_consistency"] = 0.7  # Will be enhanced with actual data

        except Exception as e:
            logger.error(f"Error calculating confidence factors: {e}")
            # Return default factors
            factors = {key: 0.5 for key in self.weights.keys()}

        return factors

    def _calculate_rule_clarity_confidence(self, violations: List[Dict[str, Any]]) -> float:
        """Calculate confidence based on rule clarity"""
        if not violations:
            return 0.8  # No violations is clear

        clarity_scores = []
        for violation in violations:
            evidence = violation.get("evidence", "")
            description = violation.get("description", "")

            # Score based on evidence specificity
            if evidence and len(evidence) > 20:
                clarity_scores.append(0.9)
            elif evidence:
                clarity_scores.append(0.7)
            else:
                clarity_scores.append(0.4)

            # Boost score if description is detailed
            if description and len(description) > 50:
                clarity_scores[-1] = min(1.0, clarity_scores[-1] + 0.1)

        return sum(clarity_scores) / len(clarity_scores) if clarity_scores else 0.5

    def _calculate_keyword_confidence(self, keywords: List[Dict[str, Any]]) -> float:
        """Calculate confidence based on keyword matching"""
        if not keywords:
            return 0.6  # No keywords might be good or concerning

        total_confidence = 0
        for keyword_match in keywords:
            risk_level = keyword_match.get("risk_level", "low")
            context = keyword_match.get("context", "")

            # Base confidence by risk level
            risk_confidence = {"low": 0.6, "medium": 0.8, "high": 0.95}.get(risk_level, 0.5)

            # Adjust for context quality
            if len(context) > 30:
                risk_confidence = min(1.0, risk_confidence + 0.05)

            total_confidence += risk_confidence

        return min(1.0, total_confidence / len(keywords))

    def _calculate_context_confidence(
        self,
        content_analysis: Dict[str, Any],
        reasoning: str
    ) -> float:
        """Calculate confidence based on context analysis"""
        base_confidence = 0.5

        # Adjust based on genre detection confidence
        genre = content_analysis.get("genre_detected", "unknown")
        if genre != "unknown":
            base_confidence += 0.1

        # Adjust based on tone analysis
        tone = content_analysis.get("tone", "neutral")
        if tone in ["positive", "neutral"]:
            base_confidence += 0.05

        # Adjust based on reasoning quality
        if reasoning and len(reasoning) > 100:
            base_confidence += 0.2
        elif reasoning and len(reasoning) > 50:
            base_confidence += 0.1

        return min(1.0, base_confidence)

    def _calculate_severity_confidence(self, violations: List[Dict[str, Any]]) -> float:
        """Calculate confidence based on violation severity"""
        if not violations:
            return 0.8  # High confidence when no violations

        severity_weights = {"minor": 0.6, "major": 0.8, "critical": 0.95}
        total_confidence = 0

        for violation in violations:
            severity = violation.get("severity", "minor")
            confidence = severity_weights.get(severity, 0.5)
            total_confidence += confidence

        return min(1.0, total_confidence / len(violations))

    def _calculate_ambiguity_confidence(self, content_analysis: Dict[str, Any]) -> float:
        """Calculate confidence based on content ambiguity (inverse relationship)"""
        # Start with medium confidence
        confidence = 0.6

        # Factors that reduce ambiguity (increase confidence)
        content_length = content_analysis.get("content_length", 0)
        if content_length > 1000:
            confidence += 0.1
        elif content_length < 200:
            confidence -= 0.1

        # Target audience clarity
        target_audience = content_analysis.get("target_audience", "unknown")
        if target_audience != "unknown":
            confidence += 0.1

        # Tone clarity
        tone = content_analysis.get("tone", "neutral")
        if tone != "neutral":
            confidence += 0.05

        return max(0.0, min(1.0, confidence))

    def _calculate_weighted_confidence(self, factors: Dict[str, float]) -> float:
        """Calculate weighted confidence score"""
        weighted_sum = 0
        total_weight = 0

        for factor_name, weight in self.weights.items():
            if factor_name in factors:
                weighted_sum += factors[factor_name] * weight
                total_weight += weight

        return weighted_sum / total_weight if total_weight > 0 else 0.5

    def _apply_consistency_adjustment(
        self,
        base_confidence: float,
        judgment: str,
        violations: List[Dict[str, Any]]
    ) -> float:
        """Apply consistency adjustments based on judgment logic"""
        adjusted_confidence = base_confidence

        # Logical consistency checks
        if judgment == "approved" and violations:
            # Approval with violations should reduce confidence
            violation_count = len(violations)
            critical_violations = sum(1 for v in violations if v.get("severity") == "critical")

            if critical_violations > 0:
                adjusted_confidence *= 0.5  # Significant reduction
            else:
                adjusted_confidence *= max(0.7, 1.0 - 0.1 * violation_count)

        elif judgment == "rejected" and not violations:
            # Rejection without violations should reduce confidence
            adjusted_confidence *= 0.6

        return max(0.0, min(1.0, adjusted_confidence))

    def _calculate_confidence_bounds(
        self,
        confidence_score: float,
        factors: Dict[str, float]
    ) -> Dict[str, float]:
        """Calculate confidence bounds and uncertainty range"""
        # Calculate variance in factors
        factor_values = list(factors.values())
        mean_factor = sum(factor_values) / len(factor_values)
        variance = sum((x - mean_factor) ** 2 for x in factor_values) / len(factor_values)
        std_dev = math.sqrt(variance)

        # Calculate bounds based on standard deviation
        uncertainty = std_dev * 0.5  # Scaling factor
        lower_bound = max(0.0, confidence_score - uncertainty)
        upper_bound = min(1.0, confidence_score + uncertainty)

        return {
            "lower_bound": lower_bound,
            "upper_bound": upper_bound,
            "uncertainty_range": uncertainty,
            "confidence_interval": upper_bound - lower_bound
        }

    def _calculate_uncertainty_metrics(self, factors: Dict[str, float]) -> Dict[str, float]:
        """Calculate various uncertainty metrics"""
        factor_values = list(factors.values())

        if not factor_values:
            return {"entropy": 1.0, "variance": 1.0, "disagreement": 1.0}

        # Calculate entropy-like measure
        normalized_factors = [max(0.01, min(0.99, f)) for f in factor_values]
        entropy = -sum(f * math.log(f) + (1-f) * math.log(1-f) for f in normalized_factors) / len(normalized_factors)

        # Calculate variance
        mean_factor = sum(factor_values) / len(factor_values)
        variance = sum((x - mean_factor) ** 2 for x in factor_values) / len(factor_values)

        # Calculate disagreement (range)
        disagreement = max(factor_values) - min(factor_values)

        return {
            "entropy": entropy,
            "variance": variance,
            "disagreement": disagreement
        }

    def _determine_confidence_level(self, confidence_score: float) -> str:
        """Determine qualitative confidence level"""
        for level, threshold in sorted(self.thresholds.items(), key=lambda x: x[1], reverse=True):
            if confidence_score >= threshold:
                return level
        return "very_low"

    def _generate_confidence_recommendations(
        self,
        confidence_score: float,
        confidence_level: str,
        factors: Dict[str, float]
    ) -> List[str]:
        """Generate recommendations based on confidence analysis"""
        recommendations = []

        if confidence_score < 0.5:
            recommendations.append("Consider human review due to low confidence")

        if confidence_level in ["very_low", "low"]:
            recommendations.append("Escalate to higher-level processing")

        # Factor-specific recommendations
        low_factors = [name for name, score in factors.items() if score < 0.5]
        if "rule_clarity" in low_factors:
            recommendations.append("Rule matching may be ambiguous - consider additional analysis")

        if "keyword_confidence" in low_factors:
            recommendations.append("Keyword matching has low confidence - review context")

        if "content_ambiguity" in low_factors:
            recommendations.append("Content is ambiguous - may benefit from expert review")

        if not recommendations:
            if confidence_score > 0.9:
                recommendations.append("High confidence - suitable for automated processing")
            else:
                recommendations.append("Moderate confidence - standard processing appropriate")

        return recommendations

    def _get_fallback_confidence_result(self, base_confidence: float) -> Dict[str, Any]:
        """Get fallback confidence result when scoring fails"""
        return {
            "final_confidence_score": max(0.0, min(1.0, base_confidence)),
            "confidence_level": "unknown",
            "confidence_factors": {},
            "confidence_bounds": {"lower_bound": 0.0, "upper_bound": 1.0},
            "uncertainty_metrics": {"entropy": 1.0, "variance": 1.0},
            "recommendations": ["Manual review recommended due to scoring error"],
            "scoring_metadata": {
                "error": "Confidence scoring failed",
                "fallback_used": True
            }
        }

    def compare_confidence_scores(
        self,
        scores: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Compare multiple confidence scores and provide analysis"""
        if not scores:
            return {"error": "No scores provided"}

        confidence_values = [s.get("final_confidence_score", 0.5) for s in scores]

        return {
            "mean_confidence": sum(confidence_values) / len(confidence_values),
            "max_confidence": max(confidence_values),
            "min_confidence": min(confidence_values),
            "confidence_range": max(confidence_values) - min(confidence_values),
            "scores_count": len(scores),
            "agreement_level": "high" if max(confidence_values) - min(confidence_values) < 0.2 else "low"
        }


# Global confidence scorer instance
confidence_scorer = ConfidenceScorer()