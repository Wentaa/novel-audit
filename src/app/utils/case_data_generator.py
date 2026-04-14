from typing import Dict, Any, List
import json
import random
from datetime import datetime, timedelta

from ..storage.vector_store import vector_store
from ..services.rule_management_service import rule_management_service
import logging

logger = logging.getLogger(__name__)


class CaseDataGenerator:
    """Generator for training case data to populate the RAG database"""

    def __init__(self):
        self.content_templates = {
            "romance": [
                "她轻轻地推开房门，心跳如雷。月光洒在他的脸上，那张熟悉的面孔在夜色中显得格外温柔。",
                "他们在咖啡厅的角落里相遇，一杯拿铁的香气成为了这段恋情的开始。",
                "雨夜里，她接到了他的电话。那个声音穿过千里之外，温暖了她整颗心。",
                "婚礼的钟声响起，她穿着白色的婚纱，走向属于她的幸福。",
                "分别的车站，他们拥抱告别，约定着要一起走过人生的每一个春夏秋冬。"
            ],
            "action": [
                "刀光剑影中，他身形如电，在敌人的包围中杀出一条血路。",
                "拳头与拳头的碰撞，汗水与血水的交融，这是属于男人的战斗。",
                "子弹呼啸而过，他翻身躲避，同时扣动扳机，敌人应声倒下。",
                "高速追车，引擎的咆哮声回荡在夜色中，生死时刻就在转眼之间。",
                "剑气纵横，一招一式都蕴含着深厚的武学修为。"
            ],
            "fantasy": [
                "魔法阵光芒大作，古老的咒语在空中回响，召唤出了传说中的神兽。",
                "她举起法杖，口中念着咒语，火球在手掌中凝聚成型。",
                "龙族的咆哮震撼天地，巨大的翅膀遮天蔽日。",
                "精灵的弓箭百发百中，在森林中如同风中的精灵。",
                "魔王的城堡矗立在黑暗中，无数亡灵在其周围徘徊。"
            ],
            "historical": [
                "大将军策马扬鞭，率领三军征战沙场，为国家的荣耀而战。",
                "宫廷之中暗流涌动，皇位争夺战一触即发。",
                "江南水乡，才子佳人在春风中吟诗作对。",
                "边塞烽火连天，将士们守卫着祖国的边疆。",
                "朝堂之上，文臣武将为国家大事争论不休。"
            ]
        }

        self.violation_examples = {
            "violence": [
                "鲜血溅射墙壁，他的身体被肢解得面目全非，肠子流了一地。",
                "刀子一下下地刺入，每一下都带出鲜血，受害者的惨叫声回荡在房间里。",
                "他用钝器重重地砸在对方的头骨上，脑浆迸裂，血肉模糊。"
            ],
            "adult_content": [
                "她缓缓褪去衣衫，完美的身躯在月光下若隐若现，他的目光贪婪地游走在她身上。",
                "激情如火，两人纠缠在床榻之间，房间里响起阵阵喘息声。",
                "他的手在她身上游走，探索着每一寸肌肤的秘密。"
            ],
            "political": [
                "现任领导人的政策完全是错误的，他们只会给国家带来灾难。",
                "这个政府腐败无能，人民应该起来推翻他们。",
                "某某党的统治就是独裁，我们需要真正的民主。"
            ],
            "illegal": [
                "制作冰毒的详细步骤：首先准备麻黄碱，然后加入硫酸...",
                "这个诈骗手段很简单，只需要伪造身份证，然后...",
                "洗钱的最佳方式是通过多个银行账户转移资金。"
            ]
        }

        self.approval_reasons = [
            "内容符合平台规范，情节健康向上",
            "虽有轻微争议但整体积极正面",
            "创作手法成熟，内容适合目标读者",
            "符合该类型作品的标准要求",
            "内容创新且不违反任何规定"
        ]

        self.rejection_reasons = [
            "包含过度详细的暴力描述，不适合平台发布",
            "涉及成人内容，违反平台内容政策",
            "包含政治敏感内容，存在合规风险",
            "描述非法活动细节，可能产生不良影响",
            "内容格调低俗，不符合平台价值观"
        ]

    async def generate_training_cases(self, count: int = 100) -> List[Dict[str, Any]]:
        """
        Generate training cases for the RAG database

        Args:
            count: Number of cases to generate

        Returns:
            List of training case dictionaries
        """
        try:
            logger.info(f"Generating {count} training cases...")

            training_cases = []

            # Generate approved cases (70% of total)
            approved_count = int(count * 0.7)
            approved_cases = await self._generate_approved_cases(approved_count)
            training_cases.extend(approved_cases)

            # Generate rejected cases (30% of total)
            rejected_count = count - approved_count
            rejected_cases = await self._generate_rejected_cases(rejected_count)
            training_cases.extend(rejected_cases)

            # Shuffle the cases
            random.shuffle(training_cases)

            logger.info(f"Generated {len(training_cases)} training cases "
                       f"({approved_count} approved, {rejected_count} rejected)")

            return training_cases

        except Exception as e:
            logger.error(f"Training case generation failed: {e}")
            raise

    async def _generate_approved_cases(self, count: int) -> List[Dict[str, Any]]:
        """Generate approved training cases"""
        approved_cases = []

        try:
            for i in range(count):
                # Choose random genre
                genre = random.choice(list(self.content_templates.keys()))

                # Generate content
                base_content = random.choice(self.content_templates[genre])

                # Add some variation
                content = self._add_content_variation(base_content, genre)

                # Create case
                case = {
                    "content": content,
                    "result": "approved",
                    "reason": random.choice(self.approval_reasons),
                    "metadata": {
                        "genre": genre,
                        "target_audience": self._determine_target_audience(genre),
                        "tone": "positive" if random.random() > 0.3 else "neutral",
                        "confidence": round(random.uniform(0.7, 0.95), 2),
                        "content_length": len(content),
                        "created_at": self._generate_random_date().isoformat(),
                        "case_type": "training",
                        "violation_severity": "none"
                    }
                }

                approved_cases.append(case)

            return approved_cases

        except Exception as e:
            logger.error(f"Approved case generation failed: {e}")
            return []

    async def _generate_rejected_cases(self, count: int) -> List[Dict[str, Any]]:
        """Generate rejected training cases"""
        rejected_cases = []

        try:
            for i in range(count):
                # Choose violation type
                violation_type = random.choice(list(self.violation_examples.keys()))

                # Generate violating content
                violation_content = random.choice(self.violation_examples[violation_type])

                # Add context to make it more realistic
                context_genre = random.choice(list(self.content_templates.keys()))
                context_content = random.choice(self.content_templates[context_genre])

                # Combine context and violation
                content = f"{context_content} {violation_content}"

                # Determine severity
                severity = self._determine_violation_severity(violation_type)

                # Create case
                case = {
                    "content": content,
                    "result": "rejected",
                    "reason": random.choice(self.rejection_reasons),
                    "metadata": {
                        "genre": context_genre,
                        "target_audience": "adult" if violation_type == "adult_content" else "general",
                        "tone": "negative",
                        "confidence": round(random.uniform(0.8, 0.95), 2),
                        "content_length": len(content),
                        "created_at": self._generate_random_date().isoformat(),
                        "case_type": "training",
                        "violation_type": violation_type,
                        "violation_severity": severity
                    }
                }

                rejected_cases.append(case)

            return rejected_cases

        except Exception as e:
            logger.error(f"Rejected case generation failed: {e}")
            return []

    def _add_content_variation(self, base_content: str, genre: str) -> str:
        """Add variation to base content"""
        try:
            variations = [
                f"（第一章）{base_content}这是一个温暖的故事开始。",
                f"{base_content}故事就这样慢慢展开了。",
                f"在一个阳光明媚的下午，{base_content}",
                f"{base_content}这让人感到无比的宁静和美好。",
                f"时间仿佛停止了，{base_content}一切都是那么完美。"
            ]

            return random.choice(variations)

        except Exception as e:
            logger.error(f"Content variation failed: {e}")
            return base_content

    def _determine_target_audience(self, genre: str) -> str:
        """Determine target audience based on genre"""
        audience_map = {
            "romance": random.choice(["general", "mature"]),
            "action": "general",
            "fantasy": "general",
            "historical": "mature"
        }
        return audience_map.get(genre, "general")

    def _determine_violation_severity(self, violation_type: str) -> str:
        """Determine severity based on violation type"""
        severity_map = {
            "violence": random.choice(["major", "critical"]),
            "adult_content": "critical",
            "political": "critical",
            "illegal": "critical"
        }
        return severity_map.get(violation_type, "major")

    def _generate_random_date(self) -> datetime:
        """Generate random date within the last 90 days"""
        try:
            start_date = datetime.now() - timedelta(days=90)
            random_days = random.randint(0, 90)
            return start_date + timedelta(days=random_days)
        except:
            return datetime.now()

    async def populate_vector_database(self, case_count: int = 50) -> Dict[str, Any]:
        """
        Generate and populate the vector database with training cases

        Args:
            case_count: Number of cases to generate and add

        Returns:
            Summary of population results
        """
        try:
            logger.info(f"Populating vector database with {case_count} training cases...")

            # Generate training cases
            training_cases = await self.generate_training_cases(case_count)

            # Add cases to vector store
            case_ids = await vector_store.add_training_cases(training_cases)

            # Generate summary
            approved_count = sum(1 for case in training_cases if case["result"] == "approved")
            rejected_count = len(training_cases) - approved_count

            genre_distribution = {}
            for case in training_cases:
                genre = case["metadata"].get("genre", "unknown")
                genre_distribution[genre] = genre_distribution.get(genre, 0) + 1

            summary = {
                "status": "success",
                "total_cases_added": len(case_ids),
                "approved_cases": approved_count,
                "rejected_cases": rejected_count,
                "genre_distribution": genre_distribution,
                "case_ids_sample": case_ids[:5],  # Show first 5 IDs
                "population_timestamp": datetime.now().isoformat()
            }

            logger.info(f"Successfully populated vector database with {len(case_ids)} cases")
            return summary

        except Exception as e:
            logger.error(f"Vector database population failed: {e}")
            return {
                "status": "error",
                "error": str(e),
                "population_timestamp": datetime.now().isoformat()
            }

    async def create_edge_cases(self) -> List[Dict[str, Any]]:
        """
        Create challenging edge cases for testing

        Returns:
            List of edge case examples
        """
        try:
            edge_cases = [
                {
                    "content": "他们在战斗中受了轻伤，鲜血滴落在地上，但他们依然坚持战斗到最后。这是英雄的故事。",
                    "result": "approved",
                    "reason": "虽有血腥描述但程度适中，且整体正面",
                    "metadata": {
                        "genre": "action",
                        "target_audience": "general",
                        "tone": "positive",
                        "confidence": 0.65,
                        "case_type": "edge_case",
                        "challenge": "borderline_violence"
                    }
                },
                {
                    "content": "他们深情地拥抱在一起，月光下的吻是那么甜蜜，爱情让他们忘记了整个世界。",
                    "result": "approved",
                    "reason": "浪漫描述适度，符合言情类作品标准",
                    "metadata": {
                        "genre": "romance",
                        "target_audience": "general",
                        "tone": "positive",
                        "confidence": 0.75,
                        "case_type": "edge_case",
                        "challenge": "romance_boundary"
                    }
                },
                {
                    "content": "历史的车轮滚滚向前，每个朝代都有其兴衰更替，这是自然规律。",
                    "result": "approved",
                    "reason": "客观描述历史，不涉及政治立场",
                    "metadata": {
                        "genre": "historical",
                        "target_audience": "mature",
                        "tone": "neutral",
                        "confidence": 0.70,
                        "case_type": "edge_case",
                        "challenge": "historical_sensitivity"
                    }
                }
            ]

            # Add timestamps
            for case in edge_cases:
                case["metadata"]["created_at"] = datetime.now().isoformat()
                case["metadata"]["content_length"] = len(case["content"])

            return edge_cases

        except Exception as e:
            logger.error(f"Edge case creation failed: {e}")
            return []

    async def validate_case_quality(self, cases: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Validate the quality of generated cases

        Args:
            cases: List of generated cases

        Returns:
            Quality validation report
        """
        try:
            validation_report = {
                "total_cases": len(cases),
                "result_distribution": {},
                "genre_distribution": {},
                "average_content_length": 0,
                "confidence_distribution": {"high": 0, "medium": 0, "low": 0},
                "quality_issues": []
            }

            total_length = 0
            for case in cases:
                # Result distribution
                result = case.get("result", "unknown")
                validation_report["result_distribution"][result] = validation_report["result_distribution"].get(result, 0) + 1

                # Genre distribution
                genre = case.get("metadata", {}).get("genre", "unknown")
                validation_report["genre_distribution"][genre] = validation_report["genre_distribution"].get(genre, 0) + 1

                # Content length
                content_length = len(case.get("content", ""))
                total_length += content_length

                # Confidence distribution
                confidence = case.get("metadata", {}).get("confidence", 0.5)
                if confidence >= 0.8:
                    validation_report["confidence_distribution"]["high"] += 1
                elif confidence >= 0.6:
                    validation_report["confidence_distribution"]["medium"] += 1
                else:
                    validation_report["confidence_distribution"]["low"] += 1

                # Quality checks
                if content_length < 20:
                    validation_report["quality_issues"].append(f"Very short content: {content_length} chars")

                if not case.get("reason"):
                    validation_report["quality_issues"].append("Missing reason for decision")

            # Calculate average length
            validation_report["average_content_length"] = total_length / len(cases) if cases else 0

            return validation_report

        except Exception as e:
            logger.error(f"Case quality validation failed: {e}")
            return {"error": str(e)}


# Global case data generator instance
case_data_generator = CaseDataGenerator()