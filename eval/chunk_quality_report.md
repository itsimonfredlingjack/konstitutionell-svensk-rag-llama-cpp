# Chunk Quality Analysis Report

**Generated:** 2026-02-03T21:25:58.545019

---

## Executive Summary

| Metric | Value |
|--------|-------|
| Total Chunks Sampled | 407 |
| Average Length | 2,531 chars |
| Metadata Completeness | 73.7% |
| Boundary Quality | 30.0% |

---

## Per-Collection Statistics

| Collection | Total Docs | Sampled | Avg Length | Too Short | Too Long | Metadata % | Boundary % |
|------------|------------|---------|------------|-----------|----------|------------|------------|
| sfs_lagtext | 2,888 | 100 | 550 | 17.0% | 0.0% | 100.0% | 18.0% |
| riksdag_documents_p1 | 230,143 | 100 | 4,951 | 0.0% | 98.0% | 0.0% | 100.0% |
| swedish_gov_docs | 304,871 | 100 | 4,033 | 0.0% | 40.0% | 100.0% | 4.0% |
| diva_research | 829,435 | 100 | 679 | 25.0% | 0.0% | 93.0% | 0.0% |
| procedural_guides | 7 | 7 | 1,254 | 0.0% | 0.0% | 100.0% | 0.0% |

---

## Length Distribution

### sfs_lagtext

- **Min:** 74 chars
- **Max:** 3,217 chars
- **Mean:** 550 chars
- **Median:** 460 chars
- **Std Dev:** 487 chars

### riksdag_documents_p1

- **Min:** 1,811 chars
- **Max:** 5,000 chars
- **Mean:** 4,951 chars
- **Median:** 5,000 chars
- **Std Dev:** 341 chars

### swedish_gov_docs

- **Min:** 300 chars
- **Max:** 8,000 chars
- **Mean:** 4,033 chars
- **Median:** 3,033 chars
- **Std Dev:** 2,938 chars

### diva_research

- **Min:** 57 chars
- **Max:** 2,887 chars
- **Mean:** 679 chars
- **Median:** 262 chars
- **Std Dev:** 785 chars

### procedural_guides

- **Min:** 975 chars
- **Max:** 1,527 chars
- **Mean:** 1,254 chars
- **Median:** 1,323 chars
- **Std Dev:** 214 chars

---

## Metadata Analysis

### sfs_lagtext

**Missing Optional Fields:**
- `rubrik`: 100 (100.0%)
- `kapitel`: 4 (4.0%)

### riksdag_documents_p1

**Missing Required Fields:**
- `titel`: 100 (100.0%)
- `beteckning`: 100 (100.0%)

**Missing Optional Fields:**
- `dok_typ`: 100 (100.0%)
- `dok_datum`: 100 (100.0%)
- `organ`: 100 (100.0%)

### swedish_gov_docs

**Missing Optional Fields:**
- `document_type`: 100 (100.0%)

### diva_research

**Missing Required Fields:**
- `title`: 7 (7.0%)

**Missing Optional Fields:**
- `abstract`: 100 (100.0%)
- `year`: 100 (100.0%)
- `author`: 100 (100.0%)
- `keywords`: 100 (100.0%)

### procedural_guides

**Missing Optional Fields:**
- `category`: 7 (100.0%)

---

## Boundary Quality Issues

| Issue Type | Count |
|------------|-------|
| boundary_starts_lowercase | 282 |
| reference_dangling_reference | 8 |
| reference_narrative_reference | 1 |

### Example Problem Chunks

**Chunk ID:** `sfs_1915_218_1_kap_1_§_5f0cb3fa_0`
- **Issue:** Contains orphaned reference (dangling_reference)
- **Snippet:** `1915:218 1 kap. Om slutande av avtal 1 §
1 § Anbud om slutande av avtal och svar...`

**Chunk ID:** `sfs_1942_740_1_kap_16_§_9b7ff75e_15`
- **Issue:** Chunk starts mid-context (starts_lowercase)
- **Snippet:** `RB 1 kap. Om allmän underrätt 16 §
16 § har upphävts genom lag (1969:244)....`

**Chunk ID:** `sfs_1942_740_4_kap_11_§_2a6b3d7f_43`
- **Issue:** Chunk starts mid-context (starts_lowercase)
- **Snippet:** `RB 4 kap. Om domare 11 §
11 §  Domare skall, innan han må tjänstgöra, avlägga de...`

**Chunk ID:** `sfs_1942_740_7_kap_1_§_313adedf_71`
- **Issue:** Chunk starts mid-context (starts_lowercase)
- **Snippet:** `RB 7 kap. Om åklagare och om jäv mot anställda vid brottsbekämpande 1 §
1 § Allm...`

**Chunk ID:** `sfs_1942_740_9_kap_9_§_ffd05568_99`
- **Issue:** Chunk starts mid-context (starts_lowercase)
- **Snippet:** `RB 9 kap. Om straff, vite och hämtning 9 §
9 § Bestämmelser i denna balk om att ...`

---

## SFS Structural Integrity

- **sfs_lagtext:** 100/100 (100.0%) chunks contain § or chapter markers

---

## Recommendations

1. **Reduce short chunks** - 42 (10.3%) chunks are under 200 chars. Consider increasing minimum chunk size or merging small adjacent chunks.
2. **Improve metadata extraction** - Only 73.7% of chunks have complete required metadata. Verify indexing pipeline preserves all fields.
3. **Adjust chunking boundaries** - 70.0% of chunks have boundary issues. Consider tuning boundary detection regex patterns.
