# Matching Algorithm — Research & Findings

> **Last updated:** 2026-03-08  
> **Scope:** Analyse raw datasets, define entities, plan hybrid (keyword + semantic) matching backend

---

## 1. Datasets Overview

| Property | Jobs | Candidates (People) |
|---|---|---|
| **File** | `dataset_jobs_cleaned.csv` | `dataset_exa-ai-people-search_…csv` |
| **Rows** | 100 | 100 |
| **Columns** | 95 (after dropping 159 `ai_*` cols) | 9 |
| **Source** | Career-site job listing API | Exa.ai LinkedIn people search |
| **Duplicate rows** | 0 | 0 |

---

## 2. Jobs Dataset — Field Analysis

### 2.1 Identity & Core Fields

| Column | Fill | Unique | Notes |
|---|---|---|---|
| `id` | 100% | 100 | Numeric string, primary key |
| `title` | 100% | 84 | 16 collisions → same title across orgs |
| `organization` | 100% | 74 | |
| `url` | 100% | 100 | ATS links (greenhouse, paylocity, adp, …) |
| `source` | 100% | 14 | ATS platform name |
| `source_domain` | 100% | 29 | |
| `date_posted` | ~100% | — | ISO 8601 |
| `date_created` | ~100% | — | ISO 8601 |

### 2.2 Location Fields

| Column | Fill | Notes |
|---|---|---|
| `remote_derived` | **100%** | `True`=34, `False`=66 |
| `countries_derived/0` | **100%** | 99 US, 1 Germany |
| `regions_derived/0` | 85% | US state |
| `cities_derived/0` | 80% | City name |
| `lats_derived/0`, `lngs_derived/0` | ~100% | Geocoordinates available |
| `location_type` | **13%** | Almost always `"Place"` — low value |
| `location_requirements_raw/0/name` | 13% | Sparse, not reliable |

**Key insight:** `remote_derived` (boolean) + `cities_derived/0` + `regions_derived/0` + coordinates are the reliable location signals. 1/3 of jobs are remote.

### 2.3 Salary Fields

| Column | Fill | Notes |
|---|---|---|
| `salary_raw/value/minValue` | ~60% | Raw schema.org salary |
| `salary_raw/value/maxValue` | ~60% | Raw schema.org salary |
| `salary_raw/currency` | ~60% | Predominantly USD |
| `salary_raw/value/unitText` | ~60% | `YEAR`, `HOUR`, etc. |

**Key insight:** ~40% of jobs have no salary data. Salary matching must degrade gracefully (skip if missing).

### 2.4 Employment Type

| Column | Fill | Notes |
|---|---|---|
| `employment_type/0` | 50% | **Inconsistent values** |

**Raw values:** `FULL_TIME`, `Full Time`, `Full Time Regular`, `Full time`, `Full-time`, `RFT`  
→ **Must normalize** to a canonical set: `full_time`, `part_time`, `contract`, `internship`

### 2.5 Description Text (Primary Matching Signal)

| Column | Count | min chars | p50 chars | p90 chars | max chars |
|---|---|---|---|---|---|
| `description_text` | 100 | 1,514 | **5,751** | 8,550 | 13,519 |
| `description_html` | 100 | — | — | — | — |

**Key insight:** All 100 jobs have rich `description_text`. Median ~5.7k chars. This is the primary signal for semantic and keyword matching. The HTML version can be used to extract structured lists (bullets = requirements/responsibilities).

### 2.6 LinkedIn Organization Fields (Bonus Signal)

Columns available: `linkedin_org_industry`, `linkedin_org_size`, `linkedin_org_type`, `linkedin_org_employees`, `linkedin_org_description`, `linkedin_org_specialties`, `linkedin_org_headquarters`

→ Useful for **company culture / preference matching** (e.g., candidate prefers startup vs enterprise), but not available for all orgs.

---

## 3. Candidates Dataset — Field Analysis

### 3.1 Schema (All 9 Columns)

| Column | Fill | Unique | Notes |
|---|---|---|---|
| `id` | 100% | 100 | Exa library URL (LinkedIn URL as key) |
| `url` | 100% | 100 | LinkedIn profile URL |
| `author` | 99% | 98 | Candidate full name |
| `title` | 100% | 99 | **LinkedIn headline** (rich signal) |
| `publishedDate` | 91% | 91 | Profile indexed date (Jun 2024 – Jan 2026) |
| `image` | 100% | 100 | Profile photo URL |
| `text` | 100% | — | Full scraped profile (capped at 10k chars) |
| `highlights` | — | — | Exa-computed relevant excerpts |
| `highlightScores` | — | — | Relevance scores per highlight |

### 3.2 Primary Text Signal

| Column | Count | min chars | p50 chars | p90 chars | max chars |
|---|---|---|---|---|---|
| `text` | 100 | 226 | **5,804** | 10,000 | 10,000 |

**Key insight:** The `text` field is the **full LinkedIn profile** in Markdown-like format. It contains:
- Name, headline (role + status like "Actively looking")
- Work history (company, role, dates, description)
- Education, certifications
- Skills section (though often sparse)
- Activity / posts

The 10,000-char cap means some profiles are truncated. Important to note.

### 3.3 LinkedIn Headline (`title` field) — Parsed Signals

Actual values from data:
```
"Uday Ram | Senior Software Engineer | Actively looking for new opportunities"
"Shreyas Chaudhary | Looking for SWE/SDE roles | Software Engineer | Full Stack Developer | Python, Java, TypeScript | Open to Relocation"
"Ken Link | Senior Software Engineer at Open Systems International"
"Brennan Stuewe | Software Engineer | Configuration Management"
"Brandon Holman | Remote-Ready | CET-Aligned ..."
"Surekha Kumari | MSCE University of Texas at Dallas"
```

**Extractable from headline alone:**
- Job-seeking status (`Actively looking`, `Open to Relocation`)
- Current/desired role title
- Key skills inline (Python, Java, TypeScript)
- Remote preference (`Remote-Ready`)

### 3.4 Full `text` Profile Structure

Each profile follows a consistent Markdown structure:
```
# Name
<headline>
<location>

## About
Total Experience: X years Y months

## Experience
### <Role> at <Company> (Current)
<date range> | <description>

## Education
### <Degree> at <University>

## Licenses & Certifications
## Skills
## Activity
```

**Extractable via parsing:**
- Total YoE (years of experience)
- Current role + company
- Past roles + companies + durations
- Education degree + school
- Certifications
- Location (city, state, country)
- Skill keywords (if Skills section populated)

---

## 4. Gap Analysis

| Signal Needed | Jobs Has | Candidates Has | Gap |
|---|---|---|---|
| Required skills | Only in `description_text` (unstructured) | Only in `text` (unstructured) | Must extract via NLP |
| Experience level | Only in `description_text` | `title` + `text` | Must extract |
| Years of experience required | Only in `description_text` | "Total Experience" in `text` | Must parse/extract |
| Seniority level | Only in `title` + `description_text` | LinkedIn `title` headline | Normalize to enum |
| Tech stack | Only in `description_text` | Buried in `text` | NLP extraction |
| Location preference | `remote_derived` + coordinates | `text` mentions location | Profile lacks explicit preference field |
| Salary expectation | `salary_raw` on jobs (60% fill) | **Not present** | Candidate salary expectations are missing |
| Employment type | `employment_type/0` (50% fill, noisy) | Not present | Partial |
| Work authorization | Sometimes in `description_text` | Not present | Major gap for US-only roles |
| Education requirement | Only in `description_text` | Parsed from `text` | Must extract from jobs side |

---

## 5. Proposed Entity Model

```
┌─────────────────────────────────────────────┐
│  Job                                         │
│  - job_id (str)                              │
│  - title (str)                               │
│  - organization (str)                        │
│  - description_text (str)                    │
│  - required_skills: list[str]  ← extracted  │
│  - nice_to_have_skills: list[str] ← extracted│
│  - seniority_level (enum)      ← extracted  │
│  - years_experience_min (int)  ← extracted  │
│  - employment_type (enum)      ← normalized │
│  - is_remote (bool)                          │
│  - location: {city, region, country, lat, lng}│
│  - salary: {min, max, currency, unit}        │
│  - tech_stack: list[str]       ← extracted  │
│  - description_embedding (vec) ← computed   │
└─────────────────────────────────────────────┘

┌─────────────────────────────────────────────┐
│  Candidate                                   │
│  - candidate_id (str)  ← LinkedIn URL       │
│  - name (str)          ← author             │
│  - headline (str)      ← title              │
│  - location (str)      ← parsed from text   │
│  - is_actively_looking (bool) ← headline    │
│  - open_to_relocation (bool)  ← headline    │
│  - is_remote_ready (bool)     ← headline    │
│  - total_yoe (float)          ← parsed      │
│  - current_role (str)         ← parsed      │
│  - current_company (str)      ← parsed      │
│  - skills: list[str]          ← extracted   │
│  - tech_stack: list[str]      ← extracted   │
│  - seniority_level (enum)     ← inferred    │
│  - certifications: list[str]  ← parsed      │
│  - education: list[dict]      ← parsed      │
│  - profile_embedding (vec)    ← computed    │
└─────────────────────────────────────────────┘

┌─────────────────────────────────────────────┐
│  Match                                       │
│  - job_id                                    │
│  - candidate_id                              │
│  - semantic_score (float 0–1)                │
│  - keyword_score (float 0–1)                 │
│  - location_score (float 0–1)                │
│  - seniority_score (float 0–1)               │
│  - salary_score (float 0–1)                  │
│  - final_score (float 0–1)  ← weighted sum  │
│  - matched_skills: list[str]                 │
│  - missing_skills: list[str]                 │
│  - explanation (str)        ← for UI        │
└─────────────────────────────────────────────┘
```

---

## 6. Matching Architecture — Backend Design

### 6.1 Overview

```
Candidates ──► [Parser + Feature Extractor] ──► Candidate Store
Jobs       ──► [Parser + Feature Extractor] ──► Job Store
                         │
               [Hybrid Matching Engine]
                    │            │
          [Keyword Layer]  [Semantic Layer]
                    │            │
              [Score Merger + Ranker]
                         │
                   [Result API]
```

### 6.2 Stage 1 — Feature Extraction

#### Jobs (`description_text`)

Use a combination of:
1. **Regex / dictionary-based skill extraction** (fast, deterministic)
   - Maintain a curated tech skills dictionary (Python, React, PostgreSQL, …)
   - Pattern match against `description_text`
   - Separate "Required" vs "Preferred" sections by detecting header keywords

2. **spaCy NER + noun-chunk extraction**
   - Detect years-of-experience mentions: `r"(\d+)\+?\s*years?\s+of\s+experience"`
   - Detect education requirements: `r"(Bachelor|Master|PhD|BS|MS)"`
   - Detect seniority: scan title + first paragraph

3. **LLM-based structured extraction (optional, high quality)**
   - Call GPT-4o-mini / Claude Haiku with a structured JSON schema
   - Extract: `required_skills`, `nice_to_have_skills`, `seniority`, `yoe_min`, `employment_type`
   - Cost: ~$0.002/job at gpt-4o-mini prices → feasible for 10k jobs

#### Candidates (`text` profile)

1. **Regex parsing of the structured Markdown sections**
   - `## Experience` → parse roles, companies, durations → compute total YoE
   - `## Education` → degree, school
   - `## Licenses & Certifications` → list
   - `## Skills` → keyword list (often sparse)

2. **Headline parsing** (`title` field)
   - Detect "Actively looking", "Open to Relocation", "Remote-Ready"
   - Extract inline skill tags separated by `|`
   - Extract current role + seniority from first segment

3. **Skill extraction from full `text`**
   - Same tech dictionary approach as jobs
   - Context matters: skill mentioned in recent job = stronger signal

### 6.3 Stage 2 — Keyword Matching Layer

**Method: TF-IDF + Jaccard / Set Overlap**

```
keyword_score = |job_skills ∩ candidate_skills| / |job_skills|
```

- Weighted: required skills weighted 2x, nice-to-have 1x
- Normalization: lowercase, stem/lemmatize, handle aliases (JS ↔ JavaScript, k8s ↔ Kubernetes)
- Output: `{score: float, matched: list, missing: list}`

**Tooling:** `scikit-learn` TF-IDF or custom set-overlap (lighter weight)

### 6.4 Stage 3 — Semantic Similarity Layer

**Method: Dense vector embeddings + cosine similarity**

```
semantic_score = cosine_similarity(embed(job_description), embed(candidate_profile))
```

**Recommended models** (in order of quality/cost tradeoff):

| Model | Latency | Quality | Cost |
|---|---|---|---|
| `all-MiniLM-L6-v2` (sentence-transformers) | <5ms | Good | Free, local |
| `text-embedding-3-small` (OpenAI) | ~100ms | Great | ~$0.02/1M tokens |
| `text-embedding-3-large` (OpenAI) | ~200ms | Best | ~$0.13/1M tokens |

**Input construction:**
- Job: `"{title} at {organization}. {description_text[:2000]}"` (truncate to avoid token limits)
- Candidate: `"{headline}. {text[:2000]}"` (focus on recent experience + skills)

**Chunking strategy** (for long texts):
- Split description into `[requirements_section, responsibilities_section]`
- Embed each chunk separately
- Final job embedding = mean-pool of chunk embeddings

**Vector store:** For MVP, in-memory numpy arrays are fine for 100–10k records. At scale, use **pgvector** (PostgreSQL extension) or **Qdrant** / **Weaviate**.

### 6.5 Stage 4 — Structured Signal Scoring

Beyond text, score on hard/soft filters:

| Signal | Score Logic |
|---|---|
| **Location** | `1.0` if remote OR same city; `0.7` if same state; `0.3` cross-country; requires candidate location extraction |
| **Seniority** | `1.0` if match; `0.5` if ±1 level; `0.0` if >1 level off |
| **YoE** | `1.0` if candidate YoE ≥ required; linear decay below |
| **Employment type** | `1.0` if match; `0.5` if unknown |
| **Salary** | `1.0` if candidate expectation within range; not available yet → skip |

### 6.6 Stage 5 — Score Fusion

```python
final_score = (
    w1 * semantic_score +
    w2 * keyword_score +
    w3 * location_score +
    w4 * seniority_score
)

# Recommended starting weights:
w1 = 0.40  # semantic
w2 = 0.35  # keyword (skills overlap)
w3 = 0.15  # location
w4 = 0.10  # seniority / YoE
```

Weights should be **tunable** and eventually **learned** (regression over human-labeled match data).

---

## 7. Recommended Tech Stack

| Layer | Tool | Reason |
|---|---|---|
| **Data parsing** | Python + `pandas` + `re` | Already in use |
| **Skill extraction** | `spaCy` + custom skills dict | Fast, deterministic |
| **Embeddings** | `sentence-transformers` (local) or OpenAI API | Start local, scale with OpenAI |
| **Vector store** | `pgvector` on PostgreSQL | Simple, no extra infra; upgrade to Qdrant at scale |
| **Keyword match** | Custom set-overlap or `sklearn` TF-IDF | Lightweight |
| **API layer** | FastAPI | Async, typed, fast |
| **Storage** | PostgreSQL | Structured + vector in one place |
| **Caching** | Redis | Cache embeddings + top-N results |

---

## 8. Data Pipeline (Recommended Flow)

```
1. Ingest raw CSVs
      │
2. Clean & normalize
   ├── Normalize employment_type → enum
   ├── Deduplicate jobs by url
   ├── Parse candidate headline → flags + skills
   └── Parse candidate text → YoE, roles, education
      │
3. Feature extraction
   ├── Extract skills/tech from job description_text
   ├── Extract skills/tech from candidate text
   └── Normalize skill aliases
      │
4. Embedding generation
   ├── Embed job description (chunked)
   └── Embed candidate profile (chunked)
      │
5. Store in DB
   ├── jobs table (structured + embedding vector)
   └── candidates table (structured + embedding vector)
      │
6. Match API
   ├── GET /match/job/{job_id}  → ranked candidates
   └── GET /match/candidate/{candidate_id} → ranked jobs
```

---

## 9. Immediate Next Steps

| Priority | Task | Why |
|---|---|---|
| **P0** | Build `parse_candidate_text()` — extract YoE, roles, skills, location from `text` | Candidates have zero structured fields beyond headline |
| **P0** | Build `extract_job_skills()` — skill/tech extraction from `description_text` | Jobs side has no structured skills post ai_* removal |
| **P1** | Normalize `employment_type` across jobs | 50% null + 6 variant strings for same concept |
| **P1** | Compute embeddings for all 100 jobs + 100 candidates | Needed for semantic scoring |
| **P1** | Implement keyword score (set overlap, aliased) | Fast, interpretable baseline |
| **P2** | Build score fusion + ranking API | Ties it all together |
| **P2** | Collect candidate location from `text` | Needed for location scoring |
| **P3** | Add salary expectation to candidate profile | Biggest data gap |
| **P3** | Label 50–100 ground-truth matches | Needed to tune weights |

---

## 10. Key Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Candidate profiles truncated at 10k chars (Exa limit) | Prioritize parsing early sections (headline, experience); store truncation flag |
| No candidate salary expectations | Initially skip salary scoring; add intake form or LinkedIn salary insights later |
| Employment type 50% missing on jobs | Default to `full_time`; confirm from description_text |
| Skill alias explosion (JS vs JavaScript) | Maintain a curated alias map; use a standard skills taxonomy (e.g., ESCO, LinkedIn skills) |
| Semantic embeddings miss hard requirements (e.g., "US Citizenship required") | Always run keyword hard-filter layer first; flag citizenship/clearance requirements separately |
| 100 records is a small sample | Architecture must scale; use indexed vectors + paginated batch processing from day 1 |
