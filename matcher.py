"""
Hybrid Job-Candidate Matching Engine
--------------------------------------
Combines:
  - Keyword matching  : skill-set overlap with alias normalisation
  - Semantic matching : dense embeddings via sentence-transformers
                        (TF-IDF cosine fallback if ST not available)
  - Structured signals: location, seniority, years-of-experience

Score fusion (weighted sum, tunable via WEIGHTS):
  final = 0.40*semantic + 0.35*keyword + 0.15*location + 0.10*seniority
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Skills dictionary  (canonical → list of aliases)
# ---------------------------------------------------------------------------
SKILLS_ALIASES: Dict[str, List[str]] = {
    "javascript":      ["javascript", "js", "ecmascript"],
    "typescript":      ["typescript", "ts"],
    "python":          ["python"],
    "java":            ["java"],
    "cpp":             ["c++", "cpp"],
    "csharp":          ["c#", "csharp"],
    "golang":          ["golang", r"\bgo\b"],
    "rust":            ["rust"],
    "ruby":            ["ruby", "ruby on rails", "rails"],
    "php":             ["php"],
    "swift":           ["swift"],
    "kotlin":          ["kotlin"],
    "scala":           ["scala"],
    "react":           ["react", "reactjs", r"react\.js"],
    "angular":         ["angular", "angularjs"],
    "vue":             [r"vue\.js", "vuejs", r"\bvue\b"],
    "nextjs":          [r"next\.js", "nextjs"],
    "nodejs":          [r"node\.js", "nodejs"],
    "django":          ["django"],
    "fastapi":         ["fastapi"],
    "flask":           ["flask"],
    "spring":          [r"spring boot", r"\bspring\b"],
    "postgresql":      ["postgresql", "postgres"],
    "mysql":           ["mysql"],
    "sqlite":          ["sqlite"],
    "mongodb":         ["mongodb", r"\bmongo\b"],
    "redis":           ["redis"],
    "elasticsearch":   ["elasticsearch", "opensearch"],
    "kafka":           ["kafka"],
    "rabbitmq":        ["rabbitmq"],
    "docker":          ["docker"],
    "kubernetes":      ["kubernetes", r"\bk8s\b"],
    "aws":             [r"\baws\b", "amazon web services"],
    "gcp":             [r"\bgcp\b", "google cloud"],
    "azure":           [r"\bazure\b", "microsoft azure"],
    "terraform":       ["terraform"],
    "git":             [r"\bgit\b", "github", "gitlab"],
    "graphql":         ["graphql"],
    "rest":            ["restful", "rest api"],
    "grpc":            ["grpc"],
    "pytorch":         ["pytorch"],
    "tensorflow":      ["tensorflow"],
    "scikit_learn":    ["scikit-learn", "sklearn"],
    "spark":           [r"apache spark", r"\bspark\b", "pyspark"],
    "airflow":         ["airflow"],
    "dbt":             [r"\bdbt\b"],
    "snowflake":       ["snowflake"],
    "databricks":      ["databricks"],
    "machine_learning":["machine learning"],
    "deep_learning":   ["deep learning"],
    "nlp":             [r"\bnlp\b", "natural language processing"],
    "linux":           ["linux", "unix"],
    "microservices":   ["microservices"],
    "cicd":            [r"ci/cd", "cicd", "continuous integration"],
    "agile":           ["agile", "scrum"],
    "sql":             [r"\bsql\b", r"\bt-sql\b", r"\bpl/sql\b"],
    "selenium":        ["selenium"],
    "junit":           ["junit"],
    "cypress":         ["cypress"],
    "jenkins":         ["jenkins"],
    "ansible":         ["ansible"],
    "embedded":        ["embedded systems", "embedded linux"],
    "ruby_on_rails":   ["ruby on rails"],
    "c_lang":          [r"\bc language\b", r"embedded c\b", r"c programming"],
}

# Build compiled regex patterns per canonical skill
_SKILL_PATTERNS: Dict[str, re.Pattern] = {}
for _canonical, _aliases in SKILLS_ALIASES.items():
    parts = [a if a.startswith(r"\b") or a.startswith("(") else re.escape(a)
             for a in _aliases]
    combined = "|".join(f"(?:{p})" for p in parts)
    _SKILL_PATTERNS[_canonical] = re.compile(combined, re.IGNORECASE)


# ---------------------------------------------------------------------------
# Seniority
# ---------------------------------------------------------------------------
SENIORITY_ORDER = ["intern", "junior", "mid", "senior", "staff", "lead", "principal", "manager", "director"]

_SENIORITY_PATTERNS: Dict[str, re.Pattern] = {
    "intern":    re.compile(r"\b(intern|internship|co.?op)\b", re.I),
    "junior":    re.compile(r"\b(junior|jr\.?|entry[\s-]?level|associate engineer)\b", re.I),
    "mid":       re.compile(r"\b(mid[\s-]?level|mid[\s-]?senior|engineer ii|sde ii|swe ii)\b", re.I),
    "senior":    re.compile(r"\b(senior|sr\.?)\b", re.I),
    "staff":     re.compile(r"\bstaff (engineer|software|swe)\b", re.I),
    "lead":      re.compile(r"\b(tech lead|lead engineer|lead developer)\b", re.I),
    "principal": re.compile(r"\bprincipal (engineer|software|swe|developer)\b", re.I),
    "manager":   re.compile(r"\b(engineering manager|\bem\b|people manager)\b", re.I),
    "director":  re.compile(r"\b(director of engineering|engineering director)\b", re.I),
}

# Score fusion weights (must sum to 1.0)
WEIGHTS = {"semantic": 0.40, "keyword": 0.35, "location": 0.15, "seniority": 0.10}


# ---------------------------------------------------------------------------
# Feature extraction helpers
# ---------------------------------------------------------------------------

def extract_skills(text: str) -> List[str]:
    """Return sorted list of canonical skill names found in text."""
    if not text:
        return []
    found = [canonical for canonical, pat in _SKILL_PATTERNS.items() if pat.search(text)]
    return sorted(found)


def extract_seniority(text: str) -> Optional[str]:
    """Return the highest seniority level detected in text, or None."""
    if not text:
        return None
    for level in reversed(SENIORITY_ORDER):   # most senior first → most relevant
        if _SENIORITY_PATTERNS[level].search(text):
            return level
    return None


def extract_yoe_required(description: str) -> Optional[int]:
    """Parse minimum years-of-experience required from a job description."""
    if not description:
        return None
    patterns = [
        r"(\d+)\+?\s*years?\s+of\s+(?:relevant\s+)?(?:professional\s+)?(?:software\s+)?experience",
        r"(\d+)\+?\s*years?\s+(?:of\s+)?(?:related\s+)?(?:work\s+)?experience",
        r"minimum\s+(?:of\s+)?(\d+)\+?\s*years?",
        r"at\s+least\s+(\d+)\+?\s*years?",
    ]
    values = []
    for p in patterns:
        for m in re.finditer(p, description, re.I):
            values.append(int(m.group(1)))
    return min(values) if values else None


def extract_yoe_from_profile(text: str) -> Optional[float]:
    """Parse total years of experience from a LinkedIn profile."""
    if not text:
        return None
    m = re.search(r"Total\s+Experience:\s*(\d+)\s+years?(?:\s+and\s+(\d+)\s+months?)?", text, re.I)
    if m:
        return round(int(m.group(1)) + (int(m.group(2)) if m.group(2) else 0) / 12, 1)
    m2 = re.search(r"(\d+)\+?\s*years?\s+(?:of\s+)?experience", text, re.I)
    if m2:
        return float(m2.group(1))
    return None


def extract_location_from_profile(text: str) -> Optional[str]:
    """Extract candidate location from the LinkedIn profile text."""
    if not text:
        return None
    for line in text.strip().split("\n")[:12]:
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("*"):
            continue
        if re.search(r"\b(United States|US|USA|UK|Canada|Germany|India)\b", line) and len(line) < 80:
            return line
        if re.match(r"^[A-Z][a-zA-Z\s\-]+,\s*[A-Z][a-zA-Z\s\-]+(,\s*.+)?$", line) and len(line) < 60:
            return line
    return None


def parse_headline_flags(title: str) -> Dict[str, bool]:
    t = title.lower() if title else ""
    return {
        "is_actively_looking": any(k in t for k in ["actively looking", "open to work", "seeking", "looking for"]),
        "open_to_relocation":  any(k in t for k in ["open to relocation", "willing to relocate", "open to relocate"]),
        "is_remote_ready":     any(k in t for k in ["remote-ready", "remote ready", "remote first", r"\bremote\b"]),
    }


def _normalize_employment_type(raw: str) -> str:
    r = raw.lower().strip()
    if any(k in r for k in ["full", "ft", "rft"]):  return "full_time"
    if any(k in r for k in ["part", "pt"]):          return "part_time"
    if "contract" in r:                               return "contract"
    if "intern" in r:                                 return "internship"
    return "unknown"


def _safe_float(v) -> Optional[float]:
    try:
        f = float(v)
        return None if f != f else f   # NaN != NaN → return None
    except:
        return None


# ---------------------------------------------------------------------------
# Parsers: row → structured dict
# ---------------------------------------------------------------------------

def parse_job(row: pd.Series) -> Dict:
    desc  = str(row.get("description_text") or "")
    title = str(row.get("title") or "")
    return {
        "job_id":          str(row.get("id") or ""),
        "title":           title,
        "organization":    str(row.get("organization") or ""),
        "url":             str(row.get("url") or ""),
        "description":     desc,
        "is_remote":       str(row.get("remote_derived") or "").lower() in ("true", "1"),
        "city":            str(row.get("cities_derived/0") or ""),
        "region":          str(row.get("regions_derived/0") or ""),
        "country":         str(row.get("countries_derived/0") or ""),
        "employment_type": _normalize_employment_type(str(row.get("employment_type/0") or "")),
        "salary_min":      _safe_float(row.get("salary_raw/value/minValue")),
        "salary_max":      _safe_float(row.get("salary_raw/value/maxValue")),
        "salary_currency": str(row.get("salary_raw/currency") or "USD"),
        "required_skills": extract_skills(desc),
        "seniority":       extract_seniority(title + " " + desc[:1000]),
        "yoe_min":         extract_yoe_required(desc),
        # Text fed into the embedding model
        "embed_text":      f"{title} at {row.get('organization', '')}.\n{desc[:2500]}",
    }


def parse_candidate(row: pd.Series) -> Dict:
    text  = str(row.get("text") or "")
    title = str(row.get("title") or "")
    flags = parse_headline_flags(title)
    return {
        "candidate_id":       str(row.get("id") or ""),
        "name":               str(row.get("author") or ""),
        "headline":           title,
        "url":                str(row.get("url") or ""),
        "profile_text":       text,
        "location":           extract_location_from_profile(text),
        "skills":             extract_skills(text),
        "seniority":          extract_seniority(title + "\n" + text[:600]),
        "total_yoe":          extract_yoe_from_profile(text),
        "is_actively_looking":flags["is_actively_looking"],
        "open_to_relocation": flags["open_to_relocation"],
        "is_remote_ready":    flags["is_remote_ready"],
        # Text fed into the embedding model
        "embed_text":         f"{title}.\n{text[:2500]}",
    }


# ---------------------------------------------------------------------------
# Score functions
# ---------------------------------------------------------------------------

def compute_keyword_score(job: Dict, candidate: Dict) -> Tuple[float, List[str], List[str]]:
    job_skills  = set(job["required_skills"])
    cand_skills = set(candidate["skills"])
    if not job_skills:
        return 0.5, [], []
    matched = sorted(job_skills & cand_skills)
    missing = sorted(job_skills - cand_skills)
    return round(len(matched) / len(job_skills), 4), matched, missing


def compute_location_score(job: Dict, candidate: Dict) -> float:
    if job["is_remote"]:
        return 1.0
    if candidate["is_remote_ready"] or candidate["open_to_relocation"]:
        return 0.8
    loc = (candidate.get("location") or "").lower()
    if job["city"]   and job["city"].lower()   in loc: return 1.0
    if job["region"] and job["region"].lower() in loc: return 0.7
    if job["country"] and job["country"].lower() in loc: return 0.5
    return 0.5 if not loc else 0.3


def compute_seniority_score(job: Dict, candidate: Dict) -> float:
    js = job.get("seniority")
    cs = candidate.get("seniority")
    if not js or not cs:
        return 0.5
    ji = SENIORITY_ORDER.index(js) if js in SENIORITY_ORDER else -1
    ci = SENIORITY_ORDER.index(cs) if cs in SENIORITY_ORDER else -1
    if ji < 0 or ci < 0:
        return 0.5
    diff = abs(ji - ci)
    return {0: 1.0, 1: 0.7, 2: 0.4}.get(diff, 0.1)


def fuse_scores(semantic: float, keyword: float, location: float, seniority: float) -> float:
    return round(
        WEIGHTS["semantic"]  * semantic  +
        WEIGHTS["keyword"]   * keyword   +
        WEIGHTS["location"]  * location  +
        WEIGHTS["seniority"] * seniority,
        4,
    )


# ---------------------------------------------------------------------------
# Match Engine
# ---------------------------------------------------------------------------

class MatchEngine:
    """
    Loads jobs + candidates, computes embeddings once, then provides
    fast ranked match queries in both directions.
    """

    def __init__(
        self,
        jobs_csv: str,
        candidates_csv: str,
        model_name: str = "all-MiniLM-L6-v2",
    ):
        print("Loading datasets …")
        jdf = pd.read_csv(jobs_csv, low_memory=False)
        cdf = pd.read_csv(candidates_csv, low_memory=False)

        print(f"Parsing {len(jdf)} jobs …")
        self.jobs: List[Dict] = [parse_job(row) for _, row in jdf.iterrows()]

        print(f"Parsing {len(cdf)} candidates …")
        self.candidates: List[Dict] = [parse_candidate(row) for _, row in cdf.iterrows()]

        # Fast lookup by ID
        self._job_pos:  Dict[str, int] = {j["job_id"]:       i for i, j in enumerate(self.jobs)}
        self._cand_pos: Dict[str, int] = {c["candidate_id"]: i for i, c in enumerate(self.candidates)}

        self._build_embeddings(model_name)

    # ------------------------------------------------------------------
    def _build_embeddings(self, model_name: str) -> None:
        job_texts  = [j["embed_text"] for j in self.jobs]
        cand_texts = [c["embed_text"] for c in self.candidates]

        try:
            from sentence_transformers import SentenceTransformer
            print(f"\nLoading embedding model '{model_name}' (downloads ~80 MB on first run) …")
            model = SentenceTransformer(model_name)
            print("Encoding jobs …")
            self.job_embeddings  = model.encode(job_texts,  show_progress_bar=True, batch_size=32, normalize_embeddings=True)
            print("Encoding candidates …")
            self.cand_embeddings = model.encode(cand_texts, show_progress_bar=True, batch_size=32, normalize_embeddings=True)
            self._use_tfidf = False
            print("✓ Sentence-transformer embeddings ready.\n")
        except Exception as e:
            print(f"sentence-transformers unavailable ({e}) → falling back to TF-IDF cosine similarity.\n")
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.preprocessing import normalize
            vec = TfidfVectorizer(max_features=15000, stop_words="english", ngram_range=(1, 2))
            all_vecs = normalize(vec.fit_transform(job_texts + cand_texts).toarray())
            n = len(job_texts)
            self.job_embeddings  = all_vecs[:n]
            self.cand_embeddings = all_vecs[n:]
            self._use_tfidf = True
            print("✓ TF-IDF vectors ready.\n")

    # ------------------------------------------------------------------
    def _cosine(self, query: np.ndarray, matrix: np.ndarray) -> np.ndarray:
        # Embeddings are L2-normalised → dot product == cosine similarity
        scores = matrix @ query
        # Clip to [0, 1] to avoid tiny negatives from floating point
        return np.clip(scores, 0.0, 1.0)

    # ------------------------------------------------------------------
    def match_job_to_candidates(self, job_id: str, top_n: int = 5) -> List[Dict]:
        """Return top_n candidates ranked for a given job."""
        pos = self._job_pos.get(job_id)
        if pos is None:
            raise ValueError(f"job_id '{job_id}' not found.")
        job = self.jobs[pos]
        sem_scores = self._cosine(self.job_embeddings[pos], self.cand_embeddings)

        results = []
        for i, cand in enumerate(self.candidates):
            kw_score, matched, missing = compute_keyword_score(job, cand)
            loc_score = compute_location_score(job, cand)
            sen_score = compute_seniority_score(job, cand)
            sem_score = float(sem_scores[i])
            results.append({
                "rank":              0,
                "candidate_id":      cand["candidate_id"],
                "name":              cand["name"],
                "headline":          cand["headline"],
                "final_score":       fuse_scores(sem_score, kw_score, loc_score, sen_score),
                "semantic_score":    round(sem_score, 4),
                "keyword_score":     round(kw_score, 4),
                "location_score":    round(loc_score, 4),
                "seniority_score":   round(sen_score, 4),
                "matched_skills":    matched,
                "missing_skills":    missing,
                "candidate_skills":  cand["skills"],
                "total_yoe":         cand["total_yoe"],
                "seniority":         cand["seniority"],
                "is_actively_looking": cand["is_actively_looking"],
                "location":          cand["location"],
            })

        results.sort(key=lambda x: x["final_score"], reverse=True)
        for i, r in enumerate(results[:top_n], 1):
            r["rank"] = i
        return results[:top_n]

    # ------------------------------------------------------------------
    def match_candidate_to_jobs(self, candidate_id: str, top_n: int = 5) -> List[Dict]:
        """Return top_n jobs ranked for a given candidate."""
        pos = self._cand_pos.get(candidate_id)
        if pos is None:
            raise ValueError(f"candidate_id '{candidate_id}' not found.")
        cand = self.candidates[pos]
        sem_scores = self._cosine(self.cand_embeddings[pos], self.job_embeddings)

        results = []
        for i, job in enumerate(self.jobs):
            kw_score, matched, missing = compute_keyword_score(job, cand)
            loc_score = compute_location_score(job, cand)
            sen_score = compute_seniority_score(job, cand)
            sem_score = float(sem_scores[i])
            loc_str = f"{job['city']}, {job['region']}".strip(", ")
            salary  = (
                f"${job['salary_min']:,.0f}–${job['salary_max']:,.0f} {job['salary_currency']}"
                if job["salary_min"] and job["salary_max"] else "N/A"
            )
            results.append({
                "rank":            0,
                "job_id":          job["job_id"],
                "title":           job["title"],
                "organization":    job["organization"],
                "final_score":     fuse_scores(sem_score, kw_score, loc_score, sen_score),
                "semantic_score":  round(sem_score, 4),
                "keyword_score":   round(kw_score, 4),
                "location_score":  round(loc_score, 4),
                "seniority_score": round(sen_score, 4),
                "matched_skills":  matched,
                "missing_skills":  missing,
                "is_remote":       job["is_remote"],
                "location":        loc_str,
                "salary":          salary,
                "seniority":       job["seniority"],
                "yoe_min":         job["yoe_min"],
            })

        results.sort(key=lambda x: x["final_score"], reverse=True)
        for i, r in enumerate(results[:top_n], 1):
            r["rank"] = i
        return results[:top_n]

    # ------------------------------------------------------------------
    def stats(self) -> Dict:
        """Quick dataset-level statistics."""
        remote_jobs = sum(1 for j in self.jobs if j["is_remote"])
        looking     = sum(1 for c in self.candidates if c["is_actively_looking"])
        avg_job_skills  = round(sum(len(j["required_skills"]) for j in self.jobs) / len(self.jobs), 1)
        avg_cand_skills = round(sum(len(c["skills"]) for c in self.candidates) / len(self.candidates), 1)
        return {
            "jobs":             len(self.jobs),
            "candidates":       len(self.candidates),
            "remote_jobs":      remote_jobs,
            "actively_looking": looking,
            "avg_job_skills":   avg_job_skills,
            "avg_cand_skills":  avg_cand_skills,
            "embedding_type":   "tfidf" if self._use_tfidf else "sentence-transformers",
        }
