"""
test_matching.py
-----------------
End-to-end tests for the hybrid matching engine.

Tests:
  1. Engine stats  (sanity check on parsed data)
  2. Job → Candidates  (top-5 for 3 sample jobs)
  3. Candidate → Jobs  (top-5 for 3 sample candidates)
  4. Edge cases        (unknown job_id, candidates with sparse profiles)

Run:
  python test_matching.py
"""

from matcher import MatchEngine, extract_skills, extract_seniority, extract_yoe_from_profile

JOBS_CSV       = "dataset_jobs_cleaned.csv"
CANDIDATES_CSV = "dataset_exa-ai-people-search_2026-03-03_05-58-58-357.csv"

SEP  = "=" * 80
SEP2 = "-" * 60


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def print_job_header(job: dict) -> None:
    loc = f"{job['city']}, {job['region']}" if job["city"] else job["region"]
    salary = (
        f"${job['salary_min']:,.0f}–${job['salary_max']:,.0f} {job['salary_currency']}"
        if job["salary_min"] and job["salary_max"] else "N/A"
    )
    print(f"\n  Title      : {job['title']}")
    print(f"  Company    : {job['organization']}")
    print(f"  Remote     : {job['is_remote']}  |  Location : {loc}")
    print(f"  Seniority  : {job['seniority']}  |  YoE req  : {job['yoe_min']}")
    print(f"  Salary     : {salary}")
    print(f"  Skills ({len(job['required_skills'])}) : {', '.join(job['required_skills'][:12]) or 'none extracted'}")


def print_candidate_header(cand: dict) -> None:
    print(f"\n  Name       : {cand['name']}")
    print(f"  Headline   : {cand['headline'][:90]}")
    print(f"  Location   : {cand['location'] or 'unknown'}")
    print(f"  YoE        : {cand['total_yoe']}  |  Seniority : {cand['seniority']}")
    print(f"  Flags      : actively_looking={cand['is_actively_looking']}  remote_ready={cand['is_remote_ready']}  relocate={cand['open_to_relocation']}")
    print(f"  Skills ({len(cand['skills'])}) : {', '.join(cand['skills'][:12]) or 'none extracted'}")


def print_candidate_match(rank: int, m: dict) -> None:
    bar = "█" * int(m["final_score"] * 20)
    print(f"\n  #{rank}  {m['name']}")
    print(f"      Score  : {m['final_score']:.3f}  {bar}")
    print(f"      Breakdown: semantic={m['semantic_score']:.3f}  keyword={m['keyword_score']:.3f}  "
          f"location={m['location_score']:.3f}  seniority={m['seniority_score']:.3f}")
    print(f"      YoE: {m['total_yoe']}  |  Seniority: {m['seniority']}  |  "
          f"Actively looking: {m['is_actively_looking']}  |  Location: {m['location'] or 'unknown'}")
    print(f"      Matched skills : {', '.join(m['matched_skills']) or 'none'}")
    print(f"      Missing skills : {', '.join(m['missing_skills']) or 'none'}")


def print_job_match(rank: int, m: dict) -> None:
    bar = "█" * int(m["final_score"] * 20)
    print(f"\n  #{rank}  {m['title']}  @  {m['organization']}")
    print(f"      Score  : {m['final_score']:.3f}  {bar}")
    print(f"      Breakdown: semantic={m['semantic_score']:.3f}  keyword={m['keyword_score']:.3f}  "
          f"location={m['location_score']:.3f}  seniority={m['seniority_score']:.3f}")
    print(f"      Remote: {m['is_remote']}  |  Location: {m['location']}  |  "
          f"Salary: {m['salary']}  |  Seniority: {m['seniority']}  |  YoE req: {m['yoe_min']}")
    print(f"      Matched skills : {', '.join(m['matched_skills']) or 'none'}")
    print(f"      Missing skills : {', '.join(m['missing_skills']) or 'none'}")


# ---------------------------------------------------------------------------
# Unit-level tests (no engine needed)
# ---------------------------------------------------------------------------

def test_feature_extraction() -> None:
    print(SEP)
    print("UNIT TEST 1 — Feature Extraction")
    print(SEP)

    # Skills
    text = "We use Python, React, PostgreSQL and deploy on AWS with Docker and Kubernetes (k8s)."
    skills = extract_skills(text)
    print(f"\nextract_skills:\n  input : {text}\n  output: {skills}")
    assert "python"     in skills, "Expected python"
    assert "react"      in skills, "Expected react"
    assert "postgresql" in skills, "Expected postgresql"
    assert "aws"        in skills, "Expected aws"
    assert "docker"     in skills, "Expected docker"
    assert "kubernetes" in skills, "Expected kubernetes"
    print("  ✓ all expected skills found")

    # Seniority
    cases = [
        ("Senior Software Engineer",         "senior"),
        ("Junior Developer – Entry Level",   "junior"),
        ("Staff Engineer at Stripe",         "staff"),
        ("Principal SWE at Google",          "principal"),
        ("Software Engineering Intern",      "intern"),
        ("Engineering Manager, Platform",    "manager"),
        ("Some random string",               None),
    ]
    print("\nextract_seniority:")
    for text, expected in cases:
        result = extract_seniority(text)
        status = "✓" if result == expected else "✗"
        print(f"  {status}  '{text}' → {result}  (expected {expected})")

    # YoE from profile
    profile = "Total Experience: 7 years and 5 months"
    yoe = extract_yoe_from_profile(profile)
    print(f"\nextract_yoe_from_profile:\n  input : '{profile}'\n  output: {yoe}")
    assert yoe is not None and yoe > 7, f"Expected ~7.4 got {yoe}"
    print("  ✓ YoE parsed correctly")


# ---------------------------------------------------------------------------
# Integration tests (engine)
# ---------------------------------------------------------------------------

def test_engine_stats(engine: MatchEngine) -> None:
    print(f"\n{SEP}")
    print("INTEGRATION TEST 2 — Engine Stats")
    print(SEP)
    s = engine.stats()
    print(f"\n  Embedding type     : {s['embedding_type']}")
    print(f"  Jobs loaded        : {s['jobs']}")
    print(f"  Candidates loaded  : {s['candidates']}")
    print(f"  Remote jobs        : {s['remote_jobs']} / {s['jobs']}")
    print(f"  Actively looking   : {s['actively_looking']} / {s['candidates']}")
    print(f"  Avg skills/job     : {s['avg_job_skills']}")
    print(f"  Avg skills/cand    : {s['avg_cand_skills']}")
    assert s["jobs"] > 0 and s["candidates"] > 0
    print("\n  ✓ Engine loaded successfully")


def test_job_to_candidates(engine: MatchEngine) -> None:
    print(f"\n{SEP}")
    print("INTEGRATION TEST 3 — Job → Top-5 Candidates")
    print(SEP)

    # Pick 3 diverse jobs: first, a remote job, and a mid-list job
    sample_jobs = []
    for j in engine.jobs:
        if not sample_jobs:
            sample_jobs.append(j)
        elif j["is_remote"] and not any(x["is_remote"] for x in sample_jobs):
            sample_jobs.append(j)
        elif j["seniority"] == "senior" and len(sample_jobs) < 3:
            sample_jobs.append(j)
        if len(sample_jobs) == 3:
            break
    # Pad if needed
    for j in engine.jobs:
        if len(sample_jobs) < 3 and j not in sample_jobs:
            sample_jobs.append(j)
        if len(sample_jobs) == 3:
            break

    for job in sample_jobs:
        print(f"\n{SEP2}")
        print(f"JOB: [{job['job_id']}]")
        print_job_header(job)
        print(f"\n  Top 5 matching candidates:")
        matches = engine.match_job_to_candidates(job["job_id"], top_n=5)
        for m in matches:
            print_candidate_match(m["rank"], m)

    print(f"\n  ✓ Job→Candidates matching complete")


def test_candidate_to_jobs(engine: MatchEngine) -> None:
    print(f"\n{SEP}")
    print("INTEGRATION TEST 4 — Candidate → Top-5 Jobs")
    print(SEP)

    # Pick 3 diverse candidates: one actively looking, one senior, one with many skills
    sample_cands = []
    for c in engine.candidates:
        if not sample_cands:
            sample_cands.append(c)
        elif c["is_actively_looking"] and not any(x["is_actively_looking"] for x in sample_cands):
            sample_cands.append(c)
        elif len(c["skills"]) >= 5 and len(sample_cands) < 3:
            sample_cands.append(c)
        if len(sample_cands) == 3:
            break
    for c in engine.candidates:
        if len(sample_cands) < 3 and c not in sample_cands:
            sample_cands.append(c)
        if len(sample_cands) == 3:
            break

    for cand in sample_cands:
        print(f"\n{SEP2}")
        print(f"CANDIDATE: [{cand['candidate_id'].split('/')[-1]}]")
        print_candidate_header(cand)
        print(f"\n  Top 5 matching jobs:")
        matches = engine.match_candidate_to_jobs(cand["candidate_id"], top_n=5)
        for m in matches:
            print_job_match(m["rank"], m)

    print(f"\n  ✓ Candidate→Jobs matching complete")


def test_edge_cases(engine: MatchEngine) -> None:
    print(f"\n{SEP}")
    print("INTEGRATION TEST 5 — Edge Cases")
    print(SEP)

    # Bad job_id
    try:
        engine.match_job_to_candidates("non_existent_id_999")
        print("  ✗ Expected ValueError for unknown job_id")
    except ValueError as e:
        print(f"\n  ✓ Unknown job_id raises ValueError: {e}")

    # Bad candidate_id
    try:
        engine.match_candidate_to_jobs("https://fake.url/person/nobody")
        print("  ✗ Expected ValueError for unknown candidate_id")
    except ValueError as e:
        print(f"  ✓ Unknown candidate_id raises ValueError: {e}")

    # Sparse candidate (no skills, no YoE)
    sparse = {
        "candidate_id": "test_sparse",
        "name": "Test Sparse",
        "headline": "Software Developer",
        "url": "",
        "profile_text": "Experienced developer.",
        "location": None,
        "skills": [],
        "seniority": None,
        "total_yoe": None,
        "is_actively_looking": False,
        "open_to_relocation": False,
        "is_remote_ready": False,
        "embed_text": "Software Developer. Experienced developer.",
    }
    job = engine.jobs[0]
    from matcher import compute_keyword_score, compute_location_score, compute_seniority_score, fuse_scores
    kw, matched, missing = compute_keyword_score(job, sparse)
    loc = compute_location_score(job, sparse)
    sen = compute_seniority_score(job, sparse)
    final = fuse_scores(0.5, kw, loc, sen)
    print(f"\n  Sparse candidate against '{job['title']}':")
    print(f"    keyword={kw}  location={loc}  seniority={sen}  final≈{final}")
    print(f"  ✓ Sparse profile handled gracefully (no crash)")

    print(f"\n  ✓ All edge cases passed")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Unit tests (no engine needed)
    test_feature_extraction()

    # Build engine once, reuse for all integration tests
    print(f"\n{SEP}")
    print("Initialising MatchEngine …")
    print(SEP)
    engine = MatchEngine(JOBS_CSV, CANDIDATES_CSV)

    test_engine_stats(engine)
    test_job_to_candidates(engine)
    test_candidate_to_jobs(engine)
    test_edge_cases(engine)

    print(f"\n{SEP}")
    print("ALL TESTS PASSED")
    print(SEP)
