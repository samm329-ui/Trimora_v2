import pytest
from backend.services.llm_provider import LLMProvider
from backend.services.semantic_service import SemanticService
from backend.services.story_reasoner import StoryReasoner
from backend.services.story_detector import StoryDetector
from backend.services.story_validator import StoryValidator
from backend.services.coverage_analyzer import CoverageAnalyzer
from backend.services.blueprint_generator import BlueprintGenerator
from backend.services.embedding_service import EmbeddingService
from backend.models.semantic import SegmentAnnotations
from backend.models.story import StoryCollection
from backend.models.topic_block import TopicBlock
from backend.tests.fixtures.sample_video import make_segments


class MockLLMProvider(LLMProvider):
    def complete(self, prompt, response_format="json"):
        return {
            "annotations": [
                {"segment_id": "seg_h_0", "topic": "productivity", "subtopic": "deep work", "story_role": "hook", "intent": "question", "emotion": "curiosity", "emotion_intensity": 0.8, "importance_score": 0.9, "hook_strength": 0.95, "ending_strength": 0.0, "curiosity_score": 0.9, "information_density": 0.7, "standalone_score": 0.8, "completeness_score": 0.7, "context_dependency": "low", "key_entities": ["productivity"], "keywords": ["what", "if", "told"], "confidence_score": 0.85},
                {"segment_id": "seg_b_0", "topic": "productivity", "subtopic": "wasted time", "story_role": "body", "intent": "explain", "emotion": "neutral", "emotion_intensity": 0.4, "importance_score": 0.7, "hook_strength": 0.0, "ending_strength": 0.0, "curiosity_score": 0.3, "information_density": 0.8, "standalone_score": 0.6, "completeness_score": 0.8, "context_dependency": "medium", "key_entities": ["tasks"], "keywords": ["truth", "waste", "hours"], "confidence_score": 0.8},
                {"segment_id": "seg_b_1", "topic": "deep work", "subtopic": "focus", "story_role": "body", "intent": "explain", "emotion": "determination", "emotion_intensity": 0.6, "importance_score": 0.85, "hook_strength": 0.0, "ending_strength": 0.0, "curiosity_score": 0.4, "information_density": 0.9, "standalone_score": 0.7, "completeness_score": 0.9, "context_dependency": "low", "key_entities": ["deep work"], "keywords": ["key", "insight", "focus"], "confidence_score": 0.85},
                {"segment_id": "seg_b_2", "topic": "deep work", "subtopic": "scheduling", "story_role": "body", "intent": "explain", "emotion": "calm", "emotion_intensity": 0.3, "importance_score": 0.75, "hook_strength": 0.0, "ending_strength": 0.0, "curiosity_score": 0.2, "information_density": 0.85, "standalone_score": 0.65, "completeness_score": 0.85, "context_dependency": "medium", "key_entities": ["morning"], "keywords": ["block", "hours", "project"], "confidence_score": 0.8},
                {"segment_id": "seg_b_3", "topic": "distractions", "subtopic": "enemy", "story_role": "body", "intent": "argue", "emotion": "frustration", "emotion_intensity": 0.7, "importance_score": 0.8, "hook_strength": 0.0, "ending_strength": 0.0, "curiosity_score": 0.3, "information_density": 0.75, "standalone_score": 0.7, "completeness_score": 0.7, "context_dependency": "low", "key_entities": ["distractions"], "keywords": ["enemy", "progress"], "confidence_score": 0.82},
                {"segment_id": "seg_b_4", "topic": "focus", "subtopic": "elimination", "story_role": "body", "intent": "explain", "emotion": "calm", "emotion_intensity": 0.2, "importance_score": 0.65, "hook_strength": 0.0, "ending_strength": 0.0, "curiosity_score": 0.1, "information_density": 0.7, "standalone_score": 0.6, "completeness_score": 0.75, "context_dependency": "low", "key_entities": ["notifications"], "keywords": ["turn", "off", "close"], "confidence_score": 0.78},
                {"segment_id": "seg_e_0", "topic": "deep work", "subtopic": "conclusion", "story_role": "ending", "intent": "conclude", "emotion": "satisfaction", "emotion_intensity": 0.5, "importance_score": 0.7, "hook_strength": 0.0, "ending_strength": 0.8, "curiosity_score": 0.0, "information_density": 0.5, "standalone_score": 0.5, "completeness_score": 0.6, "context_dependency": "high", "key_entities": ["deep work"], "keywords": ["matters"], "confidence_score": 0.75},
                {"segment_id": "seg_e_1", "topic": "productivity", "subtopic": "cta", "story_role": "ending", "intent": "conclude", "emotion": "neutral", "emotion_intensity": 0.3, "importance_score": 0.5, "hook_strength": 0.0, "ending_strength": 0.6, "curiosity_score": 0.0, "information_density": 0.3, "standalone_score": 0.4, "completeness_score": 0.5, "context_dependency": "low", "key_entities": [], "keywords": ["subscribe", "tips"], "confidence_score": 0.7},
            ],
            "relationships": [],
            "stories": [
                {
                    "boundary_segments": ["seg_h_0", "seg_b_0", "seg_b_1", "seg_b_2", "seg_e_0"],
                    "story_summary": "Deep work is the key to productivity.",
                    "suggested_name": "Deep Work Matters",
                    "start_confidence": 0.85,
                    "end_confidence": 0.75,
                    "boundary_confidence": 0.8,
                    "ambiguous_segments": [],
                },
                {
                    "boundary_segments": ["seg_b_3", "seg_b_4", "seg_e_1"],
                    "story_summary": "Fight distractions to be productive.",
                    "suggested_name": "Fight Distractions",
                    "start_confidence": 0.7,
                    "end_confidence": 0.65,
                    "boundary_confidence": 0.68,
                    "ambiguous_segments": [],
                },
            ],
        }


def test_full_semantic_enrichment_pipeline():
    segments = make_segments()
    provider = MockLLMProvider()
    embedder = EmbeddingService()

    blocks = [
        TopicBlock(
            segments=segments,
            start=segments[0].start,
            end=segments[-1].end,
            original_block_index=0,
            structural_confidence=0.9,
        ),
    ]

    # Pass 1: Semantic Annotation
    semantic_svc = SemanticService(provider)
    annotations, pass1_raw = semantic_svc.annotate_segments(segments, blocks, "test transcript", "job_1")
    assert len(annotations.annotations) == 8

    # Pass 2: Story Reasoning
    reasoner = StoryReasoner(provider)
    boundaries, pass2_raw = reasoner.detect_story_boundaries(segments, annotations, blocks=blocks)
    annotations.llm_story_boundaries = boundaries
    assert len(boundaries) == 2

    # Story Candidate Formation
    detector = StoryDetector()
    candidates = detector.form_candidates(segments, annotations)
    assert len(candidates) == 2

    # Story Verification
    candidates = detector.verify_candidates(candidates, segments, annotations)

    # Story Repair
    repaired, rejected, records = detector.repair_candidates(candidates, segments, annotations)
    assert len(repaired) >= 1

    # Story Validation
    validator = StoryValidator()
    validated, all_rejected = validator.validate_stories(repaired, rejected, segments, annotations)

    # Coverage Analysis
    coverage_analyzer = CoverageAnalyzer()
    coverage = coverage_analyzer.compute_coverage(validated, all_rejected, segments)
    assert coverage.total_segments == 8

    # Blueprint Generation
    gen = BlueprintGenerator(embedder)
    blueprints, state = gen.generate_blueprints(validated, all_rejected, segments, annotations)

    # Verify outputs
    assert isinstance(annotations, SegmentAnnotations)
    assert len(boundaries) == 2
    assert len(candidates) == 2
    assert state.total_blueprints_generated >= 1
