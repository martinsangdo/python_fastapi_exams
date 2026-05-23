"""
app/utils/dsa.py

DSA implementations used throughout the platform — Module 1.

Demonstrates:
  - Hash map   → O(1) question lookup cache
  - Min-heap   → O(log n) leaderboard top-N extraction
  - Prefix tree (Trie) → O(m) exam title autocomplete
  - Binary search → O(log n) sorted package lookup
"""
import heapq
from collections import defaultdict
from typing import Any, Optional


# ─── Hash Map: O(1) Question Lookup ──────────────────────────────────────────
class QuestionCache:
    """
    In-memory hash map for O(1) question lookup within a package.
    Used during answer submission to avoid DB round-trips.
    TTL-eviction handled by Redis (see core/cache.py).
    """
    def __init__(self):
        self._store: dict[str, dict] = {}

    def put(self, question_id: str, question: dict):
        self._store[question_id] = question

    def get(self, question_id: str) -> Optional[dict]:
        return self._store.get(question_id)

    def bulk_load(self, questions: list[dict]):
        for q in questions:
            self._store[str(q["_id"])] = q

    def size(self) -> int:
        return len(self._store)


# ─── Max-Heap: Top-N Leaderboard in O(n log k) ───────────────────────────────
class Leaderboard:
    """
    Maintains top-k scores using a min-heap of size k.
    Insertion: O(log k), Extract top-k: O(k log k).

    Better than sorting all records: O(n) vs O(n log n).
    """
    def __init__(self, k: int = 10):
        self.k = k
        self._heap: list[tuple] = []   # (score, username, metadata)

    def add(self, score: float, username: str, meta: dict = None):
        entry = (score, username, meta or {})
        if len(self._heap) < self.k:
            heapq.heappush(self._heap, entry)
        elif score > self._heap[0][0]:   # beats the current minimum
            heapq.heapreplace(self._heap, entry)

    def top_k(self) -> list[dict]:
        """Return top-k entries sorted descending."""
        sorted_entries = sorted(self._heap, key=lambda x: x[0], reverse=True)
        return [
            {"rank": i + 1, "score": e[0], "username": e[1], **e[2]}
            for i, e in enumerate(sorted_entries)
        ]


# ─── Trie: Exam Title Autocomplete in O(m) ───────────────────────────────────
class TrieNode:
    def __init__(self):
        self.children: dict[str, "TrieNode"] = {}
        self.is_end = False
        self.exam_ids: list[str] = []


class ExamTrie:
    """
    Prefix tree for fast exam title autocomplete.
    Insert: O(m), Search: O(m) where m = query length.
    """
    def __init__(self):
        self.root = TrieNode()

    def insert(self, title: str, exam_id: str):
        node = self.root
        for ch in title.lower():
            if ch not in node.children:
                node.children[ch] = TrieNode()
            node = node.children[ch]
            node.exam_ids.append(exam_id)
        node.is_end = True

    def search(self, prefix: str) -> list[str]:
        """Return exam_ids whose title starts with prefix."""
        node = self.root
        for ch in prefix.lower():
            if ch not in node.children:
                return []
            node = node.children[ch]
        return list(set(node.exam_ids))[:20]


# ─── Binary Search: Sorted Package Lookup O(log n) ───────────────────────────
def find_package_by_order(packages: list[dict], order: int) -> Optional[dict]:
    """
    Binary search on packages sorted by 'order' field.
    O(log n) vs O(n) linear scan.
    """
    lo, hi = 0, len(packages) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        mid_order = packages[mid]["order"]
        if mid_order == order:
            return packages[mid]
        elif mid_order < order:
            lo = mid + 1
        else:
            hi = mid - 1
    return None


# ─── Score Calculation ────────────────────────────────────────────────────────
def calculate_score(correct: int, total: int) -> float:
    """Returns percentage score rounded to 2 decimals."""
    if total == 0:
        return 0.0
    return round((correct / total) * 100, 2)


# ─── Tag Frequency Counter: Hash Map ─────────────────────────────────────────
def count_tag_frequencies(questions: list[dict]) -> dict[str, int]:
    """
    Count how many questions belong to each tag.
    Uses defaultdict (hash map) for O(n) counting.
    Useful for analytics: which topics are most tested?
    """
    freq: dict[str, int] = defaultdict(int)
    for q in questions:
        for tag in q.get("tags", []):
            freq[tag] += 1
    return dict(sorted(freq.items(), key=lambda x: x[1], reverse=True))
