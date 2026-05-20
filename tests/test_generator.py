import pytest

from src.config import AppConfig
from src.generator import UsernameGenerator
from src.models import CharMode


@pytest.fixture
def config():
    c = AppConfig()
    c.max_candidates = 100
    c.fallback_wordlist_path = "data/fallback_words.txt"
    return c


@pytest.fixture
def generator(config):
    return UsernameGenerator(config)


class TestGenerateRandom:
    def test_correct_length(self, generator):
        results = generator.generate_random(5, CharMode.LETTERS, 10)
        assert all(len(r) == 5 for r in results)

    def test_letters_only(self, generator):
        results = generator.generate_random(6, CharMode.LETTERS, 20)
        for r in results:
            assert r.isalpha()
            assert r.islower()

    def test_numbers_only(self, generator):
        results = generator.generate_random(4, CharMode.NUMBERS, 20)
        for r in results:
            assert r.isdigit()

    def test_alphanumeric(self, generator):
        results = generator.generate_random(8, CharMode.ALPHANUMERIC, 50)
        assert len(results) > 0
        for r in results:
            assert r.isalnum()

    def test_custom_chars(self, generator):
        results = generator.generate_random(3, CharMode.CUSTOM, 10, custom_chars="abc")
        for r in results:
            assert all(c in "abc" for c in r)

    def test_respects_count(self, generator):
        results = generator.generate_random(5, CharMode.LETTERS, 10)
        assert len(results) <= 10

    def test_max_candidates_limit(self, config):
        config.max_candidates = 5
        gen = UsernameGenerator(config)
        results = gen.generate_random(5, CharMode.LETTERS, 100)
        assert len(results) <= 5

    def test_no_duplicates(self, generator):
        results = generator.generate_random(3, CharMode.LETTERS, 50)
        assert len(results) == len(set(results))


class TestDeduplicate:
    def test_removes_duplicates(self, generator):
        result = generator.deduplicate(["abc", "def", "abc", "ghi", "def"])
        assert result == ["abc", "def", "ghi"]

    def test_preserves_order(self, generator):
        result = generator.deduplicate(["zzz", "aaa", "mmm"])
        assert result == ["zzz", "aaa", "mmm"]

    def test_empty_list(self, generator):
        assert generator.deduplicate([]) == []


class TestFilterValid:
    def test_removes_invalid(self, generator):
        candidates = ["valid1", "INVALID", "good.name", ".bad", "ok99"]
        result = generator.filter_valid(candidates)
        assert "valid1" in result
        assert "good.name" in result
        assert "ok99" in result
        assert "INVALID" not in result
        assert ".bad" not in result


@pytest.mark.asyncio
class TestDictionary:
    async def test_loads_fallback(self, generator):
        words = await generator.load_wordlist()
        assert len(words) > 0

    async def test_filters_by_length(self, generator):
        candidates = await generator.generate_dictionary(3, 6, 50)
        for c in candidates:
            assert 3 <= len(c) <= 6
