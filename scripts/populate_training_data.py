"""
Script to populate ChromaDB with comprehensive training case data
Generates realistic Chinese novel content scenarios for RAG enhancement
"""
import asyncio
import json
import sys
import os
from datetime import datetime

# Add src to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from app.utils.case_data_generator import case_data_generator
from app.storage.vector_store import vector_store
from app.config import get_settings
import logging

logger = logging.getLogger(__name__)

class TrainingDataPopulator:
    """Populates vector database with comprehensive training data"""

    def __init__(self):
        self.settings = get_settings()

    async def populate_comprehensive_dataset(self) -> dict:
        """
        Populate ChromaDB with comprehensive training dataset
        """
        try:
            logger.info("Starting comprehensive training data population...")

            results = {}

            # 1. Generate standard training cases (approved/rejected mix)
            logger.info("Generating standard training cases...")
            standard_summary = await case_data_generator.populate_vector_database(case_count=200)
            results['standard_cases'] = standard_summary

            # 2. Generate edge cases for boundary testing
            logger.info("Generating edge cases...")
            edge_cases = await case_data_generator.create_edge_cases()
            if edge_cases:
                edge_case_ids = await vector_store.add_training_cases(edge_cases)
                results['edge_cases'] = {
                    'status': 'success',
                    'cases_added': len(edge_case_ids),
                    'case_ids': edge_case_ids
                }
            else:
                results['edge_cases'] = {'status': 'failed', 'error': 'No edge cases generated'}

            # 3. Generate genre-specific training sets
            logger.info("Generating genre-specific cases...")
            genre_results = await self._populate_genre_specific_cases()
            results['genre_specific'] = genre_results

            # 4. Generate confidence threshold test cases
            logger.info("Generating confidence threshold test cases...")
            threshold_cases = await self._generate_threshold_test_cases()
            threshold_ids = await vector_store.add_training_cases(threshold_cases)
            results['threshold_tests'] = {
                'cases_added': len(threshold_ids),
                'high_confidence_cases': sum(1 for case in threshold_cases if case['metadata'].get('confidence', 0) > 0.8),
                'low_confidence_cases': sum(1 for case in threshold_cases if case['metadata'].get('confidence', 0) < 0.3),
                'case_ids': threshold_ids
            }

            # 5. Generate multi-modal analysis test cases
            logger.info("Generating multi-modal analysis test cases...")
            multimodal_cases = await self._generate_multimodal_test_cases()
            multimodal_ids = await vector_store.add_training_cases(multimodal_cases)
            results['multimodal_tests'] = {
                'cases_added': len(multimodal_ids),
                'legal_cases': sum(1 for case in multimodal_cases if 'legal' in case['metadata'].get('analysis_required', [])),
                'social_cases': sum(1 for case in multimodal_cases if 'social' in case['metadata'].get('analysis_required', [])),
                'case_ids': multimodal_ids
            }

            # Generate final summary
            total_cases = sum([
                results['standard_cases'].get('total_cases_added', 0),
                results['edge_cases'].get('cases_added', 0),
                results['genre_specific'].get('total_added', 0),
                results['threshold_tests'].get('cases_added', 0),
                results['multimodal_tests'].get('cases_added', 0)
            ])

            final_summary = {
                'status': 'success',
                'total_cases_populated': total_cases,
                'population_breakdown': results,
                'database_stats': await self._get_database_stats(),
                'population_timestamp': datetime.now().isoformat()
            }

            logger.info(f"✅ Successfully populated {total_cases} training cases")
            return final_summary

        except Exception as e:
            logger.error(f"Training data population failed: {e}")
            return {
                'status': 'error',
                'error': str(e),
                'population_timestamp': datetime.now().isoformat()
            }

    async def _populate_genre_specific_cases(self) -> dict:
        """Generate genre-specific training cases"""
        genre_results = {}
        genres = ['romance', 'action', 'fantasy', 'historical']

        total_added = 0

        for genre in genres:
            try:
                # Generate genre-specific cases
                cases = await self._generate_genre_cases(genre, count=30)
                case_ids = await vector_store.add_training_cases(cases)

                genre_results[genre] = {
                    'cases_added': len(case_ids),
                    'approved_cases': sum(1 for case in cases if case['result'] == 'approved'),
                    'rejected_cases': sum(1 for case in cases if case['result'] == 'rejected'),
                    'case_ids_sample': case_ids[:3]
                }
                total_added += len(case_ids)

            except Exception as e:
                genre_results[genre] = {'error': str(e)}

        genre_results['total_added'] = total_added
        return genre_results

    async def _generate_genre_cases(self, genre: str, count: int = 30) -> list:
        """Generate cases specific to a genre"""
        cases = []

        # Genre-specific content templates
        genre_content = {
            'romance': [
                "月光下的约会让两颗心越靠越近，他们的爱情如春日暖阳般美好。",
                "分别在即，他们相拥而泣，承诺无论天涯海角都要相守一生。",
                "初遇时的心动，让她明白这就是命中注定的那个人。"
            ],
            'action': [
                "刀光剑影中，英雄挥洒汗水，为正义而战的身影格外英勇。",
                "拳脚相交，每一招都展现着武者的风采和坚定信念。",
                "在危机时刻，他们团结一心，共同面对强大的敌人。"
            ],
            'fantasy': [
                "魔法的光芒照亮黑暗，古老的咒语唤醒沉睡的力量。",
                "精灵的箭矢穿云而过，准确命中目标，展现超凡技艺。",
                "神兽的出现让整个世界为之震撼，传说变为现实。"
            ],
            'historical': [
                "朝堂之上，忠臣进谏，为国家社稷献言献策。",
                "江南才子挥毫泼墨，诗词歌赋传颂千古。",
                "边疆将士戍守国门，保卫家园的英雄气概令人敬仰。"
            ]
        }

        content_templates = genre_content.get(genre, genre_content['romance'])

        for i in range(count):
            content = content_templates[i % len(content_templates)]

            # Vary approval/rejection ratio
            is_approved = i < count * 0.8  # 80% approved

            case = {
                'content': content,
                'result': 'approved' if is_approved else 'rejected',
                'reason': f'符合{genre}类型作品标准' if is_approved else f'{genre}类型中存在不当内容',
                'metadata': {
                    'genre': genre,
                    'target_audience': 'general',
                    'tone': 'positive' if is_approved else 'negative',
                    'confidence': round(0.7 + (i % 3) * 0.1, 2),
                    'content_length': len(content),
                    'created_at': datetime.now().isoformat(),
                    'case_type': f'{genre}_specific',
                    'violation_severity': 'none' if is_approved else 'minor'
                }
            }
            cases.append(case)

        return cases

    async def _generate_threshold_test_cases(self) -> list:
        """Generate cases specifically for testing confidence thresholds"""
        threshold_cases = []

        # High confidence cases (>0.8)
        high_confidence_cases = [
            {
                'content': '这是一个温暖的家庭故事，充满爱与希望。',
                'result': 'approved',
                'reason': '内容积极正面，符合平台价值观',
                'confidence': 0.92
            },
            {
                'content': '血腥暴力的打斗场面，肢体分离，场面极其残忍。',
                'result': 'rejected',
                'reason': '包含极端暴力内容，严重违规',
                'confidence': 0.95
            }
        ]

        # Low confidence cases (<0.3)
        low_confidence_cases = [
            {
                'content': '这个情节的处理方式存在一些争议性，需要仔细考虑。',
                'result': 'approved',
                'reason': '虽有争议但整体可接受',
                'confidence': 0.25
            },
            {
                'content': '涉及复杂社会议题的故事情节，需要多角度分析。',
                'result': 'rejected',
                'reason': '内容复杂，存在潜在风险',
                'confidence': 0.28
            }
        ]

        # Medium confidence cases (0.3-0.8)
        medium_confidence_cases = [
            {
                'content': '轻微的武打描述，但整体健康向上。',
                'result': 'approved',
                'reason': '动作描述适度，主题积极',
                'confidence': 0.65
            },
            {
                'content': '涉及敏感话题但处理谨慎的情节。',
                'result': 'rejected',
                'reason': '谨慎起见，建议修改',
                'confidence': 0.45
            }
        ]

        all_cases = high_confidence_cases + low_confidence_cases + medium_confidence_cases

        for i, case_data in enumerate(all_cases):
            case = {
                'content': case_data['content'],
                'result': case_data['result'],
                'reason': case_data['reason'],
                'metadata': {
                    'genre': 'mixed',
                    'target_audience': 'general',
                    'tone': 'test_case',
                    'confidence': case_data['confidence'],
                    'content_length': len(case_data['content']),
                    'created_at': datetime.now().isoformat(),
                    'case_type': 'threshold_test',
                    'confidence_category': 'high' if case_data['confidence'] > 0.8 else 'low' if case_data['confidence'] < 0.3 else 'medium'
                }
            }
            threshold_cases.append(case)

        return threshold_cases

    async def _generate_multimodal_test_cases(self) -> list:
        """Generate cases that require multi-modal analysis"""
        multimodal_cases = []

        # Legal perspective required
        legal_cases = [
            {
                'content': '故事涉及知识产权纠纷和商业竞争，需要法律角度分析。',
                'analysis_required': ['legal'],
                'complexity': 'legal_issues'
            },
            {
                'content': '情节中包含合同纠纷和权益保护相关内容。',
                'analysis_required': ['legal'],
                'complexity': 'contract_issues'
            }
        ]

        # Social perspective required
        social_cases = [
            {
                'content': '描述社会阶层差异和不同群体间的文化冲突。',
                'analysis_required': ['social'],
                'complexity': 'social_sensitivity'
            },
            {
                'content': '涉及教育公平和社会流动性话题的故事情节。',
                'analysis_required': ['social'],
                'complexity': 'social_issues'
            }
        ]

        # Multiple perspectives required
        complex_cases = [
            {
                'content': '政府政策改革背景下的商业伦理问题探讨。',
                'analysis_required': ['legal', 'social', 'platform_risk'],
                'complexity': 'multi_domain'
            },
            {
                'content': '涉及用户隐私保护和平台责任的现代商业故事。',
                'analysis_required': ['legal', 'ux', 'platform_risk'],
                'complexity': 'platform_governance'
            }
        ]

        all_cases = legal_cases + social_cases + complex_cases

        for i, case_data in enumerate(all_cases):
            case = {
                'content': case_data['content'],
                'result': 'approved',  # Most are borderline cases
                'reason': '需要多角度专业分析确认',
                'metadata': {
                    'genre': 'contemporary',
                    'target_audience': 'mature',
                    'tone': 'complex',
                    'confidence': 0.45,  # Medium-low confidence to trigger analysis
                    'content_length': len(case_data['content']),
                    'created_at': datetime.now().isoformat(),
                    'case_type': 'multimodal_test',
                    'analysis_required': case_data['analysis_required'],
                    'complexity_type': case_data['complexity']
                }
            }
            multimodal_cases.append(case)

        return multimodal_cases

    async def _get_database_stats(self) -> dict:
        """Get comprehensive database statistics"""
        try:
            # This would be implemented based on ChromaDB's API
            # For now, return placeholder stats
            return {
                'total_documents': 'N/A - requires ChromaDB query',
                'collections': 'training_cases',
                'last_updated': datetime.now().isoformat(),
                'note': 'Detailed stats require ChromaDB connection'
            }
        except Exception as e:
            return {'error': str(e)}

    async def validate_population_quality(self) -> dict:
        """Validate quality of populated training data"""
        try:
            logger.info("Validating training data quality...")

            # Generate sample cases for validation
            sample_cases = await case_data_generator.generate_training_cases(count=50)

            # Run quality validation
            validation_report = await case_data_generator.validate_case_quality(sample_cases)

            # Add additional quality metrics
            quality_metrics = {
                'content_diversity': len(set(case['content'] for case in sample_cases)),
                'genre_coverage': len(set(case.get('metadata', {}).get('genre') for case in sample_cases)),
                'confidence_range': {
                    'min': min(case.get('metadata', {}).get('confidence', 0) for case in sample_cases),
                    'max': max(case.get('metadata', {}).get('confidence', 0) for case in sample_cases)
                },
                'approval_ratio': sum(1 for case in sample_cases if case.get('result') == 'approved') / len(sample_cases)
            }

            validation_report['quality_metrics'] = quality_metrics
            validation_report['validation_timestamp'] = datetime.now().isoformat()

            logger.info("✅ Training data quality validation completed")
            return validation_report

        except Exception as e:
            logger.error(f"Quality validation failed: {e}")
            return {'error': str(e)}


# CLI runner
async def main():
    """Main population script"""
    logging.basicConfig(level=logging.INFO)

    print("🗄️  Starting ChromaDB Training Data Population...")
    print("=" * 60)

    populator = TrainingDataPopulator()

    # Populate training data
    population_summary = await populator.populate_comprehensive_dataset()

    print("\n📊 POPULATION SUMMARY")
    print("=" * 60)
    print(json.dumps(population_summary, indent=2, ensure_ascii=False))

    # Validate data quality
    print("\n🔍 VALIDATING DATA QUALITY...")
    validation_report = await populator.validate_population_quality()

    print("\n📈 QUALITY VALIDATION")
    print("=" * 60)
    print(json.dumps(validation_report, indent=2, ensure_ascii=False))

    if population_summary.get('status') == 'success':
        print(f"\n✅ Successfully populated {population_summary.get('total_cases_populated', 0)} training cases!")
        print("🚀 ChromaDB is ready for RAG-enhanced auditing!")
    else:
        print("\n❌ Population failed - check logs for details")

    return population_summary


if __name__ == "__main__":
    asyncio.run(main())