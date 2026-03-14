"""
tests/test_phase9_learning.py

Unit tests for Phase 9 — LearningBrain and CrossSessionMemory.
Uses temporary file paths so tests don't touch production stores.
"""
import sys
import os
import json
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from mini_assistant.phase9.learning_brain import LearningBrain
from mini_assistant.phase9.cross_session_memory import CrossSessionMemory


# ── LearningBrain ─────────────────────────────────────────────────────────────

class TestLearningBrain:
    def setup_method(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        self.tmp.close()
        self.brain = LearningBrain(store_path=Path(self.tmp.name))

    def teardown_method(self):
        os.unlink(self.tmp.name)

    def test_record_and_retrieve_lesson(self):
        lesson = self.brain.record_reflection(
            lesson="Always validate user input before passing to the model.",
            intent="coding",
            quality_score=0.85,
        )
        assert lesson is not None
        assert lesson.intent == "coding"
        lessons = self.brain.get_lessons(intent="coding")
        assert any(l.id == lesson.id for l in lessons)

    def test_short_lesson_ignored(self):
        result = self.brain.record_reflection(lesson="ok", intent="chat")
        assert result is None

    def test_dedup_reinforces_existing(self):
        text = "Use streaming responses for long generations to avoid timeouts."
        l1 = self.brain.record_reflection(text, "chat", 0.8)
        l2 = self.brain.record_reflection(text, "chat", 0.8)
        assert l1 is not None
        # Second call should reinforce, not create a new lesson
        assert l1.id == l2.id
        assert l2.times_helped == 1

    def test_usefulness_score(self):
        lesson = self.brain.record_reflection("Plan before coding.", "coding", 0.9)
        assert lesson is not None
        self.brain.mark_lesson_helped(lesson.id)
        self.brain.mark_lesson_helped(lesson.id)
        self.brain.mark_lesson_hurt(lesson.id)
        # 2 helped / 3 total = 0.666...
        assert abs(lesson.usefulness - 2/3) < 0.01

    def test_delete_lesson(self):
        lesson = self.brain.record_reflection("Lesson to delete.", "chat", 0.8)
        assert lesson is not None
        ok = self.brain.delete_lesson(lesson.id)
        assert ok
        lessons = self.brain.get_lessons()
        assert not any(l.id == lesson.id for l in lessons)

    def test_get_patterns_shape(self):
        self.brain.record_reflection("Test lesson.", "coding", 0.75)
        patterns = self.brain.get_patterns()
        assert "patterns" in patterns
        assert "lessons_total" in patterns
        assert "top_lessons" in patterns

    def test_lessons_as_context_empty(self):
        result = self.brain.lessons_as_context(intent="nonexistent")
        assert result == ""

    def test_lessons_as_context_with_data(self):
        self.brain.record_reflection("Always add error handling to async functions.", "coding", 0.9)
        ctx = self.brain.lessons_as_context(intent="coding", top_k=1)
        assert "LEARNED LESSONS" in ctx
        assert "error handling" in ctx

    def test_persistence_roundtrip(self):
        self.brain.record_reflection("This should persist to disk.", "chat", 0.8)
        # Create a new instance pointing at same file
        brain2 = LearningBrain(store_path=Path(self.tmp.name))
        lessons = brain2.get_lessons()
        assert any("persist" in l.text for l in lessons)

    def test_similarity_high(self):
        sim = LearningBrain._similarity("hello world", "hello world")
        assert sim == 1.0

    def test_similarity_low(self):
        sim = LearningBrain._similarity("hello world", "completely different")
        assert sim < 0.3


# ── CrossSessionMemory ────────────────────────────────────────────────────────

class TestCrossSessionMemory:
    def setup_method(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        self.tmp.close()
        self.mem = CrossSessionMemory(store_path=Path(self.tmp.name))

    def teardown_method(self):
        os.unlink(self.tmp.name)

    def test_store_and_retrieve(self):
        fact = self.mem.store("language", "Python", category="tech_stack", confidence=0.95)
        assert fact.key == "language"
        all_facts = self.mem.get_all()
        assert any(f.id == fact.id for f in all_facts)

    def test_reinforcement(self):
        f1 = self.mem.store("framework", "FastAPI", confidence=0.80)
        f2 = self.mem.store("framework", "FastAPI", confidence=0.90)
        # Should reinforce, not create duplicate
        all_facts = self.mem.get_all()
        framework_facts = [f for f in all_facts if f.key.lower() == "framework"]
        assert len(framework_facts) == 1
        assert framework_facts[0].reinforced_count == 1

    def test_delete(self):
        fact = self.mem.store("db", "PostgreSQL", confidence=0.85)
        ok = self.mem.delete(fact.id)
        assert ok
        assert fact.id not in {f.id for f in self.mem.get_all()}

    def test_clear(self):
        self.mem.store("k1", "v1")
        self.mem.store("k2", "v2")
        count = self.mem.clear()
        assert count == 2
        assert self.mem.get_all() == []

    def test_search(self):
        self.mem.store("preferred_language", "Python", category="user_pref")
        self.mem.store("preferred_editor", "VSCode", category="user_pref")
        results = self.mem.search("python")
        assert len(results) >= 1
        assert any("Python" in f.value for f in results)

    def test_as_context_string(self):
        self.mem.store("language", "Python")
        ctx = self.mem.as_context_string(top_k=5)
        assert "LONG-TERM MEMORY" in ctx
        assert "Python" in ctx

    def test_as_context_string_empty(self):
        assert self.mem.as_context_string() == ""

    def test_persistence_roundtrip(self):
        self.mem.store("persist_key", "persist_value", confidence=0.9)
        mem2 = CrossSessionMemory(store_path=Path(self.tmp.name))
        facts = mem2.get_all()
        assert any(f.key == "persist_key" for f in facts)

    def test_stats_shape(self):
        self.mem.store("k", "v", category="tech_stack")
        stats = self.mem.stats()
        assert "total" in stats
        assert "by_category" in stats
        assert stats["by_category"].get("tech_stack", 0) >= 1
