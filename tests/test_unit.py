import json
import os

from app.chunking import chunk_text
from app.fusion import rrf
from app.search import to_or_query
from eval.metrics import hit_rank, mrr, recall_at_k

ROOT = os.path.dirname(os.path.dirname(__file__))


def test_chunk_small_text_single_chunk():
    assert chunk_text("hello world\n\nsecond paragraph", size=50, overlap=5) == ["hello world second paragraph"]


def test_chunk_overlap_and_size_bounds():
    text = " ".join(f"w{i}" for i in range(1000))
    chunks = chunk_text(text, size=100, overlap=20)
    assert all(len(c.split()) <= 100 for c in chunks)
    for a, b in zip(chunks, chunks[1:]):
        assert a.split()[-20:] == b.split()[:20]  # consecutive chunks share the overlap


def test_chunk_covers_every_word():
    words = [f"w{i}" for i in range(777)]
    chunks = chunk_text("\n\n".join(" ".join(words[i:i + 50]) for i in range(0, 777, 50)), size=120, overlap=30)
    seen = {w for c in chunks for w in c.split()}
    assert seen == set(words)


def test_chunk_no_tail_made_only_of_overlap():
    text = " ".join(f"w{i}" for i in range(200))
    chunks = chunk_text(text, size=100, overlap=20)
    assert chunks[-1].split()[-1] == "w199"
    assert len(chunks) == 3 or len(chunks) == 2


def test_chunk_rejects_bad_params():
    try:
        chunk_text("x", size=10, overlap=10)
        assert False
    except ValueError:
        pass


def test_rrf_prefers_items_ranked_by_both_lists():
    fused = rrf([[1, 2, 3], [3, 4, 1]])
    ids = [i for i, _ in fused]
    assert ids[0] == 1 and set(ids) == {1, 2, 3, 4}
    assert ids.index(3) < ids.index(4)


def test_rrf_handles_empty_lists():
    assert rrf([[], []]) == []
    assert [i for i, _ in rrf([[5, 6], []])] == [5, 6]


def test_to_or_query():
    assert to_or_query("How much does the Team plan cost?") == "how | much | does | the | team | plan | cost"
    assert to_or_query("a? !") == ""


def test_metrics():
    ranks = [1, 3, None, 2]
    assert recall_at_k(ranks, 1) == 0.25
    assert recall_at_k(ranks, 3) == 0.75
    assert abs(mrr(ranks) - (1 + 1 / 3 + 0 + 1 / 2) / 4) < 1e-9
    assert hit_rank(["abc  DEF", "xyz"], "def") == 1


def test_golden_evidence_exists_in_sample_doc():
    doc = open(os.path.join(ROOT, "eval/docs/nimbus_handbook.md")).read()
    for item in json.load(open(os.path.join(ROOT, "eval/golden.json"))):
        assert hit_rank([doc], item["evidence"]) == 1, item

def test_parse_file_preserves_utf8_unicode_and_empty_content(tmp_path):
    from app.ingest import parse_file

    for filename, content in (("unicode.txt", "Café 日本語 😀\n"), ("empty.md", "")):
        document = tmp_path / filename
        document.write_text(content, encoding="utf-8")
        assert parse_file(str(document)) == content

